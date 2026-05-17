from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import duckdb
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = Path("/Users/andrefaruolo/Downloads/I_Frota_por_UF_Municipio_Marca_e_Modelo_Ano_Abril_2026.TXT")
INDIAN_DB_PATH = PROJECT_ROOT / "data" / "frota_indian_2026_04.duckdb"
COMPETENCIA = "2026-04-01"
CHUNK_SIZE = 250_000
INDIAN_PATTERNS = [
    re.compile(r"^(I/)?INDIAN([ /-]|$)", re.I),
    re.compile(r"^IMP/INDIAN([ /-]|$)", re.I),
]


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


def is_indian_model(value: object) -> bool:
    text = "" if value is None else str(value).strip()
    normalized = normalize_text(text)
    return any(pattern.search(normalized) for pattern in INDIAN_PATTERNS)


def prepare_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    renamed = chunk.rename(columns=canonicalize_columns(chunk.columns.tolist()))
    filtered = renamed[renamed["marca_modelo"].map(is_indian_model)].copy()
    if filtered.empty:
        return filtered

    filtered["uf"] = filtered["uf"].astype(str).str.strip()
    filtered["municipio"] = filtered["municipio"].astype(str).str.strip()
    filtered["marca_modelo"] = filtered["marca_modelo"].astype(str).str.strip()
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


def build_indian_database() -> tuple[int, int, int]:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Arquivo fonte não encontrado: {SOURCE_PATH}")

    if INDIAN_DB_PATH.exists():
        INDIAN_DB_PATH.unlink()

    con = duckdb.connect(str(INDIAN_DB_PATH))
    con.execute(
        """
        CREATE TABLE staging_indian (
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
    indian_rows = 0
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
        indian_rows += len(prepared)
        con.register("prepared_chunk", prepared)
        con.execute("INSERT INTO staging_indian SELECT * FROM prepared_chunk")
        con.unregister("prepared_chunk")

    con.execute(
        """
        CREATE TABLE frota_indian AS
        SELECT
          competencia,
          uf,
          municipio,
          marca_modelo,
          ano_fabricacao,
          SUM(qtd_veiculos) AS qtd_veiculos,
          filename
        FROM staging_indian
        GROUP BY 1, 2, 3, 4, 5, 7
        ORDER BY uf, municipio, marca_modelo, ano_fabricacao
        """
    )
    total_units = con.execute("SELECT SUM(qtd_veiculos) FROM frota_indian").fetchone()[0] or 0
    total_rows = con.execute("SELECT COUNT(*) FROM frota_indian").fetchone()[0] or 0
    con.close()
    return raw_rows, indian_rows, int(total_rows), int(total_units)


def main():
    raw_rows, indian_rows, total_rows, total_units = build_indian_database()
    print(f"Arquivo fonte: {SOURCE_PATH}")
    print(f"Linhas lidas do TXT: {raw_rows:,}".replace(',', '.'))
    print(f"Linhas Indian filtradas antes da consolidação: {indian_rows:,}".replace(',', '.'))
    print(f"Base Indian DuckDB: {INDIAN_DB_PATH}")
    print(f"Linhas Indian após consolidação: {total_rows:,}".replace(',', '.'))
    print(f"Frota Indian abr/26: {total_units:,}".replace(',', '.'))


if __name__ == "__main__":
    main()
