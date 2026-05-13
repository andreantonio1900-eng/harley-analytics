from __future__ import annotations

from pathlib import Path
import unicodedata

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = Path("/Users/andrefaruolo/Downloads/I_Frota_por_UF_Municipio_Marca_e_Modelo_Ano_Abril_2026.TXT")
MASTER_DB_PATH = PROJECT_ROOT / "data" / "frota_harley.duckdb"
APRIL_DB_PATH = PROJECT_ROOT / "data" / "frota_harley_2026_04.duckdb"
COMPETENCIA = "2026-04-01"
CHUNK_SIZE = 250_000


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().upper().split())


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


def normalize_model_code(value: object) -> str:
    raw = "" if value is None else str(value).strip()
    normalized = normalize_text(raw)
    safe_map = {
        "HARLEYDAVIDSON/FLHTCI": "HARLEY DAVIDSON/FLHTCI",
        "HARLEYDAVIDSON/FLHTK TRI": "HARLEY DAVIDSON FLHT TRI",
        "I/H. DAVIDSON FXR": "I/H.DAVIDSON FXR",
        "I/HARLEY DAVIDSON FATBOY": "H-D/FLFB",
    }
    return safe_map.get(normalized, raw)


def canonicalize_columns(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for column in columns:
        normalized = normalize_text(column)
        lowered = str(column).strip().lower()
        if normalized == "UF":
            mapping[column] = "uf"
        elif "municip" in lowered or "MUNIC" in normalized:
            mapping[column] = "municipio"
        elif "marca modelo" in lowered or "MARCA MODELO" in normalized:
            mapping[column] = "marca_modelo"
        elif "ano fabrica" in lowered or "ANO FABRICA" in normalized:
            mapping[column] = "ano_fabricacao"
        elif "qtd" in lowered:
            mapping[column] = "qtd_veiculos"
    return mapping


def prepare_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    renamed = chunk.rename(columns=canonicalize_columns(chunk.columns.tolist()))
    filtered = renamed[renamed["marca_modelo"].map(is_harley_model)].copy()
    if filtered.empty:
        return filtered

    filtered["uf"] = filtered["uf"].astype(str).str.strip()
    filtered["municipio"] = filtered["municipio"].astype(str).str.strip()
    filtered["marca_modelo"] = filtered["marca_modelo"].map(normalize_model_code)
    filtered["ano_fabricacao"] = pd.to_numeric(filtered["ano_fabricacao"], errors="coerce").astype("Int64")
    filtered["qtd_veiculos"] = (
        pd.to_numeric(filtered["qtd_veiculos"], errors="coerce")
        .fillna(0)
        .round()
        .astype("Int64")
    )
    filtered["competencia"] = pd.Timestamp(COMPETENCIA)
    filtered["filename"] = str(SOURCE_PATH)
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


def build_april_database() -> tuple[int, int]:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Arquivo fonte não encontrado: {SOURCE_PATH}")

    if APRIL_DB_PATH.exists():
        APRIL_DB_PATH.unlink()

    april_con = duckdb.connect(str(APRIL_DB_PATH))
    april_con.execute(
        """
        CREATE TABLE staging_harley (
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
    harley_rows = 0
    for chunk in pd.read_csv(
        SOURCE_PATH,
        sep=";",
        encoding="latin-1",
        chunksize=CHUNK_SIZE,
        dtype=str,
    ):
        raw_rows += len(chunk)
        prepared = prepare_chunk(chunk)
        if prepared.empty:
            continue
        harley_rows += len(prepared)
        april_con.register("prepared_chunk", prepared)
        april_con.execute("INSERT INTO staging_harley SELECT * FROM prepared_chunk")
        april_con.unregister("prepared_chunk")

    april_con.execute(
        """
        CREATE TABLE frota_harley AS
        SELECT
          competencia,
          uf,
          municipio,
          marca_modelo,
          ano_fabricacao,
          SUM(qtd_veiculos) AS qtd_veiculos,
          filename
        FROM staging_harley
        GROUP BY 1, 2, 3, 4, 5, 7
        ORDER BY uf, municipio, marca_modelo, ano_fabricacao
        """
    )
    april_con.close()
    return raw_rows, harley_rows


def append_to_master():
    master_con = duckdb.connect(str(MASTER_DB_PATH))
    master_con.execute("DELETE FROM frota_harley WHERE competencia = ?", [COMPETENCIA])
    master_con.execute(f"ATTACH '{APRIL_DB_PATH}' AS april_db (READ_ONLY)")
    master_con.execute(
        """
        INSERT INTO frota_harley
        SELECT * FROM april_db.frota_harley
        """
    )
    master_con.execute("DETACH april_db")
    march_total = master_con.execute(
        "SELECT SUM(qtd_veiculos) FROM frota_harley WHERE competencia = '2026-03-01'"
    ).fetchone()[0]
    april_total = master_con.execute(
        "SELECT SUM(qtd_veiculos) FROM frota_harley WHERE competencia = '2026-04-01'"
    ).fetchone()[0]
    april_lines = master_con.execute(
        "SELECT COUNT(*) FROM frota_harley WHERE competencia = '2026-04-01'"
    ).fetchone()[0]
    master_con.close()
    return int(march_total or 0), int(april_total or 0), int(april_lines or 0)


def main():
    raw_rows, harley_rows = build_april_database()
    march_total, april_total, april_lines = append_to_master()

    print(f"Arquivo fonte: {SOURCE_PATH}")
    print(f"Linhas lidas do TXT: {raw_rows:,}".replace(",", "."))
    print(f"Linhas Harley filtradas antes da consolidação: {harley_rows:,}".replace(",", "."))
    print(f"Base April DuckDB: {APRIL_DB_PATH}")
    print(f"Linhas Harley em abril/26 após consolidação: {april_lines:,}".replace(",", "."))
    print(f"Frota Harley mar/26: {march_total:,}".replace(",", "."))
    print(f"Frota Harley abr/26: {april_total:,}".replace(",", "."))
    print(f"Delta abr vs mar: {april_total - march_total:+,}".replace(",", "."))


if __name__ == "__main__":
    main()
