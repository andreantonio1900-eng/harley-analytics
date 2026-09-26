from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import http.client
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile
import time
from typing import Callable
import unicodedata
import urllib.request
import zipfile

import duckdb
import pandas as pd


CKAN_PACKAGE_ID = "12686da0-3d71-4499-b432-d270f785c907"
CKAN_PACKAGE_SHOW_URL = (
    "https://dados.transportes.gov.br/api/3/action/package_show?id=" + CKAN_PACKAGE_ID
)
CHUNK_SIZE = 250_000
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DOWNLOAD_MAX_ATTEMPTS = 20

MONTH_SLUGS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

# O pipeline já aceita recursos TXT/CSV diretos além de ZIP/RAR.
# Overrides históricos podem ser adicionados aqui quando houver URL de download válida.
LEGACY_DIRECT_RESOURCE_OVERRIDES: list[dict] = []


@dataclass(frozen=True)
class BrandConfig:
    name: str
    table_name: str
    master_db_path: Path
    snapshot_db_path: Path
    match_fn: callable
    normalize_model_fn: callable


ProgressCallback = Callable[[str, str], None]


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().upper().split())


def canonicalize_columns(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for column in columns:
        normalized = normalize_text(column)
        lowered = str(column).strip().lower()
        tokenized = re.sub(r"[^a-z0-9]+", " ", lowered).strip()
        if normalized == "UF" or tokenized == "uf":
            mapping[column] = "uf"
        elif "municip" in lowered or "MUNIC" in normalized or "municip" in tokenized:
            mapping[column] = "municipio"
        elif (
            "marca modelo" in lowered
            or "MARCA MODELO" in normalized
            or tokenized == "marca modelo"
        ):
            mapping[column] = "marca_modelo"
        elif (
            "ano fabrica" in lowered
            or "ANO FABRICA" in normalized
            or tokenized == "ano fabricacao"
            or tokenized == "ano fabrica"
        ):
            mapping[column] = "ano_fabricacao"
        elif "qtd" in lowered or tokenized.startswith("qtd") or tokenized.startswith("quant"):
            mapping[column] = "qtd_veiculos"
    return mapping


def looks_like_access_placeholder_columns(columns: list[object]) -> bool:
    normalized_columns = [normalize_text(column) for column in columns]
    if not normalized_columns:
        return False
    campo_like = sum(value.startswith("CAMPO") for value in normalized_columns)
    trailing_placeholder_prefixes = ("IDENTIFICA", "COD", "CODIGO", "ID")
    placeholder_like = sum(
        value.startswith("CAMPO") or value.startswith(trailing_placeholder_prefixes)
        for value in normalized_columns
    )
    return campo_like >= max(1, len(normalized_columns) - 1) and placeholder_like == len(normalized_columns)


def promote_first_row_to_header_if_needed(chunk: pd.DataFrame) -> pd.DataFrame:
    if not looks_like_access_placeholder_columns(chunk.columns.tolist()):
        return chunk
    if chunk.empty:
        return chunk

    promoted_header = [str(value) for value in chunk.iloc[0].tolist()]
    promoted_chunk = chunk.iloc[1:].copy()
    promoted_chunk.columns = promoted_header
    return promoted_chunk


def detect_csv_separator(text_path: Path) -> str:
    if text_path.suffix.lower() != ".csv":
        return ";"

    with text_path.open("r", encoding="latin-1", errors="ignore") as fh:
        header = fh.readline()
    if header.count(";") >= header.count(","):
        return ";"
    return ","


def sanitize_fixed_width_delimited_file(text_path: Path) -> int:
    """Remove physically corrupt rows whose delimiter count differs from the header."""
    separator = detect_csv_separator(text_path).encode("ascii")
    sanitized_path = text_path.with_name(f"{text_path.name}.sanitized")
    removed = 0

    with text_path.open("rb") as source, sanitized_path.open("wb") as destination:
        header = source.readline()
        expected_separators = header.count(separator)
        destination.write(header.replace(b'"', b""))
        for line in source:
            if line.count(separator) != expected_separators:
                removed += 1
                continue
            # Nov/2018 also contains unmatched quotes inside the corrupt
            # region. This export does not use meaningful embedded quotes, so
            # normalize them only in this sanitized temporary copy.
            destination.write(line.replace(b'"', b""))

    sanitized_path.replace(text_path)
    return removed


def is_harley_model(value: object) -> bool:
    text = normalize_text(value)
    if "FORD" in text:
        return False
    return (
        "HARLEY" in text
        or "DAVIDSON" in text
        or text.startswith("H-D/")
        or text.startswith("H.DAVIDSON/")
    )


def normalize_harley_model(value: object) -> str:
    raw = "" if value is None else str(value).strip()
    normalized = normalize_text(raw)
    safe_map = {
        "HARLEYDAVIDSON/FLHTCI": "HARLEY DAVIDSON/FLHTCI",
        "HARLEYDAVIDSON/FLHTK TRI": "HARLEY DAVIDSON FLHT TRI",
        "I/H. DAVIDSON FXR": "I/H.DAVIDSON FXR",
        "I/HARLEY DAVIDSON FATBOY": "H-D/FLFB",
    }
    return safe_map.get(normalized, raw)


INDIAN_PATTERNS = [
    re.compile(r"^(I/)?INDIAN([ /-]|$)", re.I),
    re.compile(r"^IMP/INDIAN([ /-]|$)", re.I),
]


def is_indian_model(value: object) -> bool:
    text = "" if value is None else str(value).strip()
    normalized = normalize_text(text)
    return any(pattern.search(normalized) for pattern in INDIAN_PATTERNS)


def normalize_identity(value: object) -> str:
    return "" if value is None else str(value).strip()


def get_brand_configs(project_root: Path) -> dict[str, BrandConfig]:
    data_dir = project_root / "data"
    return {
        "harley": BrandConfig(
            name="harley",
            table_name="frota_harley",
            master_db_path=data_dir / "frota_harley.duckdb",
            snapshot_db_path=data_dir / "frota_harley_{competencia}.duckdb",
            match_fn=is_harley_model,
            normalize_model_fn=normalize_harley_model,
        ),
        "indian": BrandConfig(
            name="indian",
            table_name="frota_indian",
            master_db_path=data_dir / "frota_indian.duckdb",
            snapshot_db_path=data_dir / "frota_indian_{competencia}.duckdb",
            match_fn=is_indian_model,
            normalize_model_fn=normalize_identity,
        ),
    }


def build_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    try:
        import certifi

        context.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return context


def fetch_ckan_package_metadata() -> dict:
    with urllib.request.urlopen(
        CKAN_PACKAGE_SHOW_URL,
        context=build_ssl_context(),
    ) as response:
        payload = response.read().decode("utf-8")
    import json

    data = json.loads(payload)
    if not data.get("success"):
        raise RuntimeError("Falha ao consultar a API CKAN da SENATRAN.")
    return data["result"]


def parse_competencia_from_resource(resource: dict) -> str | None:
    candidates = [
        resource.get("url", ""),
        resource.get("name", ""),
        resource.get("description", ""),
    ]
    haystack = " ".join(str(value) for value in candidates)
    normalized = normalize_text(haystack).lower()

    # URLs do CKAN contêm UUIDs que eventualmente parecem anos (por exemplo,
    # `93520344`). Priorize o padrão explícito do nome do arquivo para não
    # interpretar janeiro/2015 como janeiro/2034.
    filename_match = re.search(
        r"(?:marca_e_modelo|marca-modelo).*?_ano_([a-z]+)_(20\d{2})",
        normalized,
    )
    if filename_match:
        month_slug, year_text = filename_match.groups()
        month = MONTH_SLUGS.get(month_slug)
        if month is not None:
            return f"{int(year_text):04d}-{month:02d}-01"

    month = None
    for slug, month_number in MONTH_SLUGS.items():
        if slug in normalized:
            month = month_number
            break
    year_match = re.search(r"(20\d{2})", normalized)
    if month is None or not year_match:
        return None
    year = int(year_match.group(1))
    return f"{year:04d}-{month:02d}-01"


def iter_brand_model_resources(package_metadata: dict) -> list[dict]:
    resources: list[dict] = []
    for resource in package_metadata.get("resources", []):
        haystack = " ".join(
            str(value)
            for value in (
                resource.get("url", ""),
                resource.get("name", ""),
                resource.get("description", ""),
            )
        )
        normalized_resource_text = normalize_text(haystack)
        if (
            "MARCA_E_MODELO" not in normalized_resource_text
            and ("FROTA" not in normalized_resource_text or "MODELO" not in normalized_resource_text)
        ):
            continue
        competencia = parse_competencia_from_resource(resource)
        if competencia is None:
            continue
        resource = dict(resource)
        resource["competencia"] = competencia
        resources.append(resource)
    resources.sort(key=lambda item: item["competencia"], reverse=True)
    return resources


def ensure_master_database(config: BrandConfig):
    if config.master_db_path.exists():
        return

    snapshot_candidate = config.master_db_path.parent / f"{config.table_name}_2026_04.duckdb"
    if snapshot_candidate.exists():
        shutil.copy2(snapshot_candidate, config.master_db_path)
        return

    con = duckdb.connect(str(config.master_db_path))
    con.execute(
        f"""
        CREATE TABLE {config.table_name} (
          competencia DATE,
          uf VARCHAR,
          municipio VARCHAR,
          marca_modelo VARCHAR,
          ano_fabricacao INTEGER,
          qtd_veiculos INTEGER,
          filename VARCHAR
        )
        """
    )
    con.close()


def existing_competencias(config: BrandConfig) -> set[str]:
    ensure_master_database(config)
    con = duckdb.connect(str(config.master_db_path), read_only=True)
    try:
        rows = con.execute(
            f"SELECT DISTINCT CAST(competencia AS VARCHAR) FROM {config.table_name}"
        ).fetchall()
    finally:
        con.close()
    return {row[0] for row in rows}


def prepare_brand_chunk(
    chunk: pd.DataFrame,
    competencia: str,
    source_label: str,
    config: BrandConfig,
) -> pd.DataFrame:
    chunk = promote_first_row_to_header_if_needed(chunk)
    renamed = chunk.rename(columns=canonicalize_columns(chunk.columns.tolist()))
    required_columns = {"uf", "municipio", "marca_modelo", "qtd_veiculos"}
    missing_columns = sorted(required_columns - set(renamed.columns))
    if missing_columns:
        available_columns = ", ".join(str(column) for column in renamed.columns)
        raise KeyError(
            "Colunas obrigatorias ausentes apos normalizacao: "
            + ", ".join(missing_columns)
            + f". Disponiveis: {available_columns}"
        )
    if "ano_fabricacao" not in renamed.columns:
        # Parte dos arquivos históricos da SENATRAN (como jan/2015) não
        # possui a dimensão de ano de fabricação. Mantemos a competência
        # utilizável e registramos o MY como não informado.
        renamed["ano_fabricacao"] = pd.NA
    filtered = renamed[renamed["marca_modelo"].map(config.match_fn)].copy()
    if filtered.empty:
        return filtered

    filtered["uf"] = filtered["uf"].astype(str).str.strip()
    filtered["municipio"] = filtered["municipio"].astype(str).str.strip()
    filtered["marca_modelo"] = filtered["marca_modelo"].map(config.normalize_model_fn)
    filtered["ano_fabricacao"] = pd.to_numeric(filtered["ano_fabricacao"], errors="coerce").astype("Int64")
    filtered["qtd_veiculos"] = (
        pd.to_numeric(filtered["qtd_veiculos"], errors="coerce")
        .fillna(0)
        .round()
        .astype("Int64")
    )
    filtered["competencia"] = pd.Timestamp(competencia)
    filtered["filename"] = source_label
    return filtered[
        [
            "competencia",
            "uf",
            "municipio",
            "marca_modelo",
            "ano_fabricacao",
            "qtd_veiculos",
            "filename",
        ]
    ]


def extract_primary_text_from_archive(archive_path: Path, temp_dir: Path) -> Path:
    suffix = archive_path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return archive_path
    if suffix in {".mdb", ".accdb"}:
        return export_mdb_to_csv(archive_path, temp_dir)

    if suffix == ".zip":
        with zipfile.ZipFile(archive_path) as zf:
            text_members = [
                member for member in zf.namelist() if member.lower().endswith((".txt", ".csv"))
            ]
            if text_members:
                preferred = sorted(
                    text_members,
                    key=lambda name: (
                        "marca_e_modelo" not in name.lower(),
                        len(name),
                    ),
                )[0]
                extracted_path = Path(zf.extract(preferred, path=temp_dir))
                return extracted_path

            access_members = [
                member for member in zf.namelist() if member.lower().endswith((".mdb", ".accdb"))
            ]
            if not access_members:
                raise FileNotFoundError(f"Nenhum TXT/CSV/MDB/ACCDB encontrado em {archive_path.name}")
            preferred_access = sorted(access_members, key=len)[0]
            extracted_access_path = Path(zf.extract(preferred_access, path=temp_dir))
            return export_mdb_to_csv(extracted_access_path, temp_dir)

    if suffix == ".rar":
        try:
            listing = subprocess.check_output(
                ["bsdtar", "-tf", str(archive_path)],
                text=True,
                stderr=subprocess.PIPE,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                "Não foi possível abrir o arquivo RAR com `bsdtar`."
            ) from exc

        members = [line.strip() for line in listing.splitlines() if line.strip()]
        text_members = [
            member for member in members if member.lower().endswith((".txt", ".csv"))
        ]
        access_members = [
            member for member in members if member.lower().endswith((".mdb", ".accdb"))
        ]
        candidates = text_members or access_members
        if not candidates:
            raise FileNotFoundError(f"Nenhum TXT/CSV/MDB/ACCDB encontrado em {archive_path.name}")

        preferred = sorted(
            candidates,
            key=lambda name: (
                "marca_e_modelo" not in name.lower(),
                len(name),
            ),
        )[0]
        subprocess.run(
            ["bsdtar", "-xf", str(archive_path), "-C", str(temp_dir), preferred],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        extracted_path = temp_dir / preferred
        if extracted_path.suffix.lower() in {".mdb", ".accdb"}:
            return export_mdb_to_csv(extracted_path, temp_dir)
        return extracted_path

    raise RuntimeError(f"Formato de arquivo não suportado: {archive_path.suffix}")


def choose_mdb_table(mdb_path: Path) -> str:
    output = subprocess.check_output(["mdb-tables", "-1", str(mdb_path)], text=True)
    tables = [line.strip() for line in output.splitlines() if line.strip()]
    if not tables:
        raise RuntimeError(f"Nenhuma tabela encontrada em {mdb_path.name}")

    preferred = sorted(
        tables,
        key=lambda name: (
            name.lower().startswith("msys"),
            "frota" not in normalize_text(name).lower(),
            "modelo" not in normalize_text(name).lower(),
            len(name),
        ),
    )[0]
    return preferred


def export_mdb_to_csv(mdb_path: Path, temp_dir: Path) -> Path:
    table_name = choose_mdb_table(mdb_path)
    csv_path = temp_dir / f"{mdb_path.stem}.csv"
    with csv_path.open("w", encoding="latin-1", newline="") as fh:
        subprocess.run(
            [
                "mdb-export",
                "-d",
                ";",
                "-D",
                "%Y-%m-%d",
                str(mdb_path),
                table_name,
            ],
            check=True,
            stdout=fh,
            stderr=subprocess.PIPE,
            text=True,
        )
    normalize_access_export_csv(csv_path)
    return csv_path


def normalize_access_export_csv(csv_path: Path) -> None:
    with csv_path.open("r", encoding="latin-1", newline="") as src:
        first_line = src.readline()
        second_line = src.readline()
        if not first_line or not second_line:
            return

        first_columns = first_line.rstrip("\n\r").split(";")
        if not looks_like_access_placeholder_columns(first_columns):
            return

        normalized_path = csv_path.with_suffix(csv_path.suffix + ".normalized")
        with normalized_path.open("w", encoding="latin-1", newline="") as dst:
            dst.write(second_line)
            shutil.copyfileobj(src, dst)

    normalized_path.replace(csv_path)


def build_snapshot_database(
    text_path: Path,
    competencia: str,
    source_label: str,
    config: BrandConfig,
    snapshot_path: Path,
) -> tuple[int, int, int]:
    if snapshot_path.exists():
        snapshot_path.unlink()

    con = duckdb.connect(str(snapshot_path))
    con.execute(
        f"""
        CREATE TABLE staging_{config.name} (
          competencia DATE,
          uf VARCHAR,
          municipio VARCHAR,
          marca_modelo VARCHAR,
          ano_fabricacao INTEGER,
          qtd_veiculos INTEGER,
          filename VARCHAR
        )
        """
    )

    raw_rows = 0
    brand_rows = 0
    for chunk in pd.read_csv(
        text_path,
        sep=detect_csv_separator(text_path),
        encoding="latin-1",
        # A few historical SENATRAN exports contain physically corrupted
        # records with more delimiters than their declared schema.
        on_bad_lines="skip",
        chunksize=CHUNK_SIZE,
        dtype=str,
    ):
        raw_rows += len(chunk)
        prepared = prepare_brand_chunk(chunk, competencia, source_label, config)
        if prepared.empty:
            continue
        brand_rows += len(prepared)
        con.register("prepared_chunk", prepared)
        con.execute(f"INSERT INTO staging_{config.name} SELECT * FROM prepared_chunk")
        con.unregister("prepared_chunk")

    con.execute(
        f"""
        CREATE TABLE {config.table_name} AS
        SELECT
          competencia,
          uf,
          municipio,
          marca_modelo,
          ano_fabricacao,
          SUM(qtd_veiculos) AS qtd_veiculos,
          filename
        FROM staging_{config.name}
        GROUP BY 1, 2, 3, 4, 5, 7
        ORDER BY uf, municipio, marca_modelo, ano_fabricacao
        """
    )
    snapshot_rows = con.execute(f"SELECT COUNT(*) FROM {config.table_name}").fetchone()[0] or 0
    con.close()
    return raw_rows, brand_rows, int(snapshot_rows)


def init_snapshot_staging(snapshot_path: Path, config: BrandConfig) -> duckdb.DuckDBPyConnection:
    if snapshot_path.exists():
        snapshot_path.unlink()

    con = duckdb.connect(str(snapshot_path))
    con.execute(
        f"""
        CREATE TABLE staging_{config.name} (
          competencia DATE,
          uf VARCHAR,
          municipio VARCHAR,
          marca_modelo VARCHAR,
          ano_fabricacao INTEGER,
          qtd_veiculos INTEGER,
          filename VARCHAR
        )
        """
    )
    return con


def finalize_snapshot_staging(
    con: duckdb.DuckDBPyConnection,
    config: BrandConfig,
) -> int:
    con.execute(
        f"""
        CREATE TABLE {config.table_name} AS
        SELECT
          competencia,
          uf,
          municipio,
          marca_modelo,
          ano_fabricacao,
          SUM(qtd_veiculos) AS qtd_veiculos,
          filename
        FROM staging_{config.name}
        GROUP BY 1, 2, 3, 4, 5, 7
        ORDER BY uf, municipio, marca_modelo, ano_fabricacao
        """
    )
    snapshot_rows = con.execute(f"SELECT COUNT(*) FROM {config.table_name}").fetchone()[0] or 0
    return int(snapshot_rows)


def build_multi_brand_snapshot_databases(
    text_path: Path,
    competencia: str,
    source_label: str,
    configs: list[BrandConfig],
    snapshot_paths: dict[str, Path],
) -> tuple[int, dict[str, int], dict[str, int]]:
    connections: dict[str, duckdb.DuckDBPyConnection] = {}
    brand_rows = {config.name: 0 for config in configs}
    snapshot_rows: dict[str, int] = {}

    try:
        for config in configs:
            connections[config.name] = init_snapshot_staging(snapshot_paths[config.name], config)

        raw_rows = 0
        for chunk in pd.read_csv(
            text_path,
            sep=detect_csv_separator(text_path),
            encoding="latin-1",
            # Invalid-width records cannot represent a valid fleet row; keep
            # every schema-conforming record and skip only those corrupt lines.
            on_bad_lines="skip",
            chunksize=CHUNK_SIZE,
            dtype=str,
        ):
            raw_rows += len(chunk)
            for config in configs:
                prepared = prepare_brand_chunk(chunk, competencia, source_label, config)
                if prepared.empty:
                    continue
                brand_rows[config.name] += len(prepared)
                con = connections[config.name]
                con.register("prepared_chunk", prepared)
                con.execute(f"INSERT INTO staging_{config.name} SELECT * FROM prepared_chunk")
                con.unregister("prepared_chunk")

        for config in configs:
            snapshot_rows[config.name] = finalize_snapshot_staging(connections[config.name], config)

        return raw_rows, brand_rows, snapshot_rows
    finally:
        for con in connections.values():
            con.close()


def resource_label(config: BrandConfig, competencia: str) -> str:
    return f"{config.name.upper()} | {competencia}"


def build_archive_path(resource: dict, config: BrandConfig) -> Path:
    archive_name = Path(str(resource["url"])).name or f"{config.name}_{resource['competencia']}.zip"
    archive_cache_dir = config.master_db_path.parent / "_download_cache" / config.name
    return archive_cache_dir / archive_name


def build_shared_archive_path(resource: dict, cache_root: Path) -> Path:
    archive_name = Path(str(resource["url"])).name or f"shared_{resource['competencia']}.zip"
    archive_cache_dir = cache_root / "_download_cache" / "shared"
    return archive_cache_dir / archive_name


def emit_progress(progress_callback: ProgressCallback | None, label: str, message: str):
    if progress_callback is not None:
        progress_callback(label, message)


def parse_total_bytes(
    response: http.client.HTTPResponse,
    existing_bytes: int,
) -> int | None:
    content_range = response.headers.get("Content-Range")
    if content_range:
        match = re.search(r"/(\d+)$", content_range)
        if match:
            return int(match.group(1))

    content_length = response.headers.get("Content-Length")
    if content_length is None:
        return None

    length = int(content_length)
    if response.status == 206 and existing_bytes > 0:
        return existing_bytes + length
    return length


def upsert_snapshot_into_master(config: BrandConfig, competencia: str, snapshot_path: Path):
    ensure_master_database(config)
    con = duckdb.connect(str(config.master_db_path))
    con.execute(f"DELETE FROM {config.table_name} WHERE competencia = ?", [competencia])
    con.execute(f"ATTACH '{snapshot_path}' AS snapshot_db (READ_ONLY)")
    con.execute(
        f"""
        INSERT INTO {config.table_name}
        SELECT * FROM snapshot_db.{config.table_name}
        """
    )
    con.execute("DETACH snapshot_db")
    total = con.execute(
        f"SELECT SUM(qtd_veiculos) FROM {config.table_name} WHERE competencia = ?",
        [competencia],
    ).fetchone()[0] or 0
    con.close()
    return int(total)


def download_resource(
    resource_url: str,
    destination: Path,
    progress_callback: ProgressCallback | None = None,
    progress_label: str | None = None,
):
    destination.parent.mkdir(parents=True, exist_ok=True)
    label = progress_label or destination.name
    if destination.exists():
        if archive_is_valid(destination):
            emit_progress(progress_callback, label, "download 100% (cache hit)")
            return
        destination.replace(destination.with_suffix(destination.suffix + ".corrupt"))

    partial_path = destination.with_suffix(destination.suffix + ".part")
    last_reported_percent = -1
    last_error: Exception | None = None
    for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            existing_bytes = partial_path.stat().st_size if partial_path.exists() else 0
            request = urllib.request.Request(
                resource_url,
                headers={"User-Agent": "harley-analytics-backfill/1.0"},
            )
            if existing_bytes > 0:
                request.add_header("Range", f"bytes={existing_bytes}-")
                emit_progress(
                    progress_callback,
                    label,
                    f"retry {attempt}/{DOWNLOAD_MAX_ATTEMPTS} from {existing_bytes:,} bytes".replace(",", "."),
                )

            with urllib.request.urlopen(
                request,
                timeout=120,
                context=build_ssl_context(),
            ) as response:
                if existing_bytes > 0 and response.status == 200:
                    partial_path.unlink(missing_ok=True)
                    emit_progress(progress_callback, label, "server ignored range; restarting partial download")
                    continue

                total_bytes = parse_total_bytes(response, existing_bytes)
                bytes_written = existing_bytes if response.status == 206 else 0
                open_mode = "ab" if response.status == 206 and existing_bytes > 0 else "wb"

                if total_bytes is not None and bytes_written > 0:
                    initial_percent = int((bytes_written / total_bytes) * 100)
                    if initial_percent > last_reported_percent:
                        for percent in range(last_reported_percent + 1, initial_percent + 1):
                            emit_progress(progress_callback, label, f"download {percent}%")
                        last_reported_percent = initial_percent

                with partial_path.open(open_mode) as fh:
                    while True:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        fh.write(chunk)
                        bytes_written += len(chunk)

                        if total_bytes is None:
                            continue

                        current_percent = min(100, int((bytes_written / total_bytes) * 100))
                        if current_percent > last_reported_percent:
                            for percent in range(last_reported_percent + 1, current_percent + 1):
                                emit_progress(progress_callback, label, f"download {percent}%")
                            last_reported_percent = current_percent

                if total_bytes is not None and bytes_written < total_bytes:
                    raise http.client.IncompleteRead(
                        partial=b"",
                        expected=total_bytes - bytes_written,
                    )

            if not archive_is_valid(partial_path, expected_suffix=destination.suffix.lower()):
                raise RuntimeError("Downloaded archive failed integrity validation.")

            partial_path.replace(destination)
            if last_reported_percent < 100:
                emit_progress(progress_callback, label, "download 100%")
            return
        except Exception as exc:
            last_error = exc
            if attempt == DOWNLOAD_MAX_ATTEMPTS:
                break
            emit_progress(progress_callback, label, f"download retry after error: {exc}")
            time.sleep(attempt)

    assert last_error is not None
    raise last_error


def archive_is_valid(path: Path, expected_suffix: str | None = None) -> bool:
    suffix = expected_suffix or path.suffix.lower()
    if not path.exists() or path.stat().st_size <= 0:
        return False
    if suffix == ".zip":
        return zipfile.is_zipfile(path)
    if suffix == ".rar":
        try:
            subprocess.run(
                # Listing alone does not catch damaged Huffman streams. Fully
                # decode to stdout and discard the payload before cache-hit.
                ["bsdtar", "-xOf", str(path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
    return True


def process_downloaded_resource(
    resource: dict,
    config: BrandConfig,
    archive_path: Path,
    keep_snapshot: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    competencia = resource["competencia"]
    label = resource_label(config, competencia)
    snapshot_path = Path(
        str(config.snapshot_db_path).format(competencia=competencia[:7].replace("-", "_"))
    )

    with tempfile.TemporaryDirectory(prefix=f"{config.name}_{competencia}_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        emit_progress(progress_callback, label, "preparing source file")
        text_path = extract_primary_text_from_archive(archive_path, temp_dir)
        emit_progress(progress_callback, label, "building snapshot")
        raw_rows, brand_rows, snapshot_rows = build_snapshot_database(
            text_path=text_path,
            competencia=competencia,
            source_label=resource["url"],
            config=config,
            snapshot_path=snapshot_path,
        )

    if not keep_snapshot and snapshot_path.exists():
        snapshot_path.unlink()

    emit_progress(progress_callback, label, "upserting into master db")
    total_units = upsert_snapshot_into_master(config, competencia, snapshot_path)
    return {
        "competencia": competencia,
        "brand": config.name,
        "archive_url": resource["url"],
        "raw_rows": raw_rows,
        "brand_rows": brand_rows,
        "snapshot_rows": snapshot_rows,
        "total_units": total_units,
        "snapshot_path": str(snapshot_path),
    }


def process_resource_for_brand(
    resource: dict,
    config: BrandConfig,
    keep_snapshot: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    competencia = resource["competencia"]
    label = resource_label(config, competencia)
    archive_path = build_archive_path(resource, config)
    download_resource(
        resource["url"],
        archive_path,
        progress_callback=progress_callback,
        progress_label=label,
    )
    return process_downloaded_resource(
        resource=resource,
        config=config,
        archive_path=archive_path,
        keep_snapshot=keep_snapshot,
        progress_callback=progress_callback,
    )


def process_downloaded_resource_multi_brand(
    resource: dict,
    configs: list[BrandConfig],
    archive_path: Path,
    keep_snapshot: bool = True,
    upsert_master: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    competencia = resource["competencia"]
    source_label = resource["url"]
    snapshot_paths = {
        config.name: Path(str(config.snapshot_db_path).format(competencia=competencia[:7].replace("-", "_")))
        for config in configs
    }

    with tempfile.TemporaryDirectory(prefix=f"multi_{competencia}_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        emit_progress(progress_callback, f"SOURCE | {competencia}", "preparing source file")
        text_path = extract_primary_text_from_archive(archive_path, temp_dir)
        if competencia == "2018-11-01":
            removed_rows = sanitize_fixed_width_delimited_file(text_path)
            emit_progress(
                progress_callback,
                f"SOURCE | {competencia}",
                f"removed {removed_rows} corrupt source rows",
            )
        emit_progress(progress_callback, f"SOURCE | {competencia}", "building multi-brand snapshots")
        raw_rows, brand_rows, snapshot_rows = build_multi_brand_snapshot_databases(
            text_path=text_path,
            competencia=competencia,
            source_label=source_label,
            configs=configs,
            snapshot_paths=snapshot_paths,
        )

    results: list[dict] = []
    for config in configs:
        snapshot_path = snapshot_paths[config.name]
        if not keep_snapshot and snapshot_path.exists():
            snapshot_path.unlink()

        if upsert_master:
            emit_progress(progress_callback, resource_label(config, competencia), "upserting into master db")
            total_units = upsert_snapshot_into_master(config, competencia, snapshot_path)
        else:
            with duckdb.connect(str(snapshot_path), read_only=True) as snapshot_con:
                total_units = int(
                    snapshot_con.execute(
                        f"SELECT COALESCE(SUM(qtd_veiculos), 0) FROM {config.table_name}"
                    ).fetchone()[0]
                )
            emit_progress(progress_callback, resource_label(config, competencia), "snapshot staged")
        results.append(
            {
                "competencia": competencia,
                "brand": config.name,
                "archive_url": source_label,
                "raw_rows": raw_rows,
                "brand_rows": brand_rows[config.name],
                "snapshot_rows": snapshot_rows[config.name],
                "total_units": total_units,
                "snapshot_path": str(snapshot_path),
            }
        )

    return results


def process_resources_with_prefetch(
    resources: list[dict],
    config: BrandConfig,
    keep_snapshot: bool = True,
    progress_callback: ProgressCallback | None = None,
    cleanup_archives: bool = False,
) -> list[dict]:
    if not resources:
        return []

    results: list[dict] = []

    def submit_download(executor: ThreadPoolExecutor, resource: dict) -> Future[Path]:
        competencia = resource["competencia"]
        label = resource_label(config, competencia)
        archive_path = build_archive_path(resource, config)
        emit_progress(progress_callback, label, "download queued")

        def _download() -> Path:
            download_resource(
                resource["url"],
                archive_path,
                progress_callback=progress_callback,
                progress_label=label,
            )
            return archive_path

        return executor.submit(_download)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"{config.name}_download") as executor:
        current_resource = resources[0]
        current_future = submit_download(executor, current_resource)

        for next_resource in resources[1:]:
            archive_path = current_future.result()
            next_future = submit_download(executor, next_resource)
            results.append(
                process_downloaded_resource(
                    resource=current_resource,
                    config=config,
                    archive_path=archive_path,
                    keep_snapshot=keep_snapshot,
                    progress_callback=progress_callback,
                )
            )
            if cleanup_archives and archive_path.exists():
                archive_path.unlink()
                emit_progress(
                    progress_callback,
                    resource_label(config, current_resource["competencia"]),
                    "cleaned cached archive",
                )
            current_resource = next_resource
            current_future = next_future

        final_archive_path = current_future.result()
        results.append(
            process_downloaded_resource(
                resource=current_resource,
                config=config,
                archive_path=final_archive_path,
                keep_snapshot=keep_snapshot,
                progress_callback=progress_callback,
            )
        )
        if cleanup_archives and final_archive_path.exists():
            final_archive_path.unlink()
            emit_progress(
                progress_callback,
                resource_label(config, current_resource["competencia"]),
                "cleaned cached archive",
            )

    return results


def process_resources_multi_brand_with_prefetch(
    resources: list[dict],
    configs: list[BrandConfig],
    keep_snapshot: bool = True,
    upsert_master: bool = True,
    progress_callback: ProgressCallback | None = None,
    cleanup_archives: bool = False,
) -> list[dict]:
    if not resources:
        return []

    results: list[dict] = []
    cache_root = configs[0].master_db_path.parent

    def submit_download(executor: ThreadPoolExecutor, resource: dict) -> Future[Path]:
        competencia = resource["competencia"]
        label = f"SOURCE | {competencia}"
        archive_path = build_shared_archive_path(resource, cache_root)
        emit_progress(progress_callback, label, "download queued")

        def _download() -> Path:
            download_resource(
                resource["url"],
                archive_path,
                progress_callback=progress_callback,
                progress_label=label,
            )
            return archive_path

        return executor.submit(_download)

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="shared_download") as executor:
        current_resource = resources[0]
        current_future = submit_download(executor, current_resource)

        for next_resource in resources[1:]:
            archive_path = current_future.result()
            next_future = submit_download(executor, next_resource)
            results.extend(
                process_downloaded_resource_multi_brand(
                    resource=current_resource,
                    configs=configs,
                    archive_path=archive_path,
                    keep_snapshot=keep_snapshot,
                    upsert_master=upsert_master,
                    progress_callback=progress_callback,
                )
            )
            if cleanup_archives and archive_path.exists():
                archive_path.unlink()
                emit_progress(progress_callback, f"SOURCE | {current_resource['competencia']}", "cleaned cached archive")
            current_resource = next_resource
            current_future = next_future

        final_archive_path = current_future.result()
        results.extend(
            process_downloaded_resource_multi_brand(
                resource=current_resource,
                configs=configs,
                archive_path=final_archive_path,
                keep_snapshot=keep_snapshot,
                upsert_master=upsert_master,
                progress_callback=progress_callback,
            )
        )
        if cleanup_archives and final_archive_path.exists():
            final_archive_path.unlink()
            emit_progress(progress_callback, f"SOURCE | {current_resource['competencia']}", "cleaned cached archive")

    return results


def determine_missing_resources(
    package_metadata: dict,
    config: BrandConfig,
    start_competencia: str | None = None,
    end_competencia: str | None = None,
) -> list[dict]:
    resources = iter_brand_model_resources(package_metadata)
    known_competencias = {resource["competencia"] for resource in resources}
    for override in LEGACY_DIRECT_RESOURCE_OVERRIDES:
        if override["competencia"] in known_competencias:
            continue
        resources.append(dict(override))
    resources.sort(key=lambda item: item["competencia"], reverse=True)

    existing = existing_competencias(config)
    selected: list[dict] = []
    for resource in resources:
        competencia = resource["competencia"]
        if start_competencia and competencia < start_competencia:
            continue
        if end_competencia and competencia > end_competencia:
            continue
        if competencia in existing:
            continue
        selected.append(resource)
    return selected
