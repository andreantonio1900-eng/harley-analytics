from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SSP_DB = PROJECT_ROOT / "data" / "ssp_veiculos.duckdb"
DEFAULT_SSP_TABLE = "ssp_veiculos"


def resolve_ssp_db_path(db_path: str | None = None) -> Path:
    if db_path:
        return Path(db_path).expanduser().resolve()
    return DEFAULT_SSP_DB.resolve()


def connect_ssp_db(db_path: str | None = None, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    path = resolve_ssp_db_path(db_path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def ensure_ssp_database(db_path: str | None = None, table_name: str = DEFAULT_SSP_TABLE) -> Path:
    path = resolve_ssp_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = connect_ssp_db(str(path), read_only=False)
    try:
        con.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                data_fato DATE,
                competencia DATE,
                ano INTEGER,
                mes INTEGER,
                tipo_crime VARCHAR,
                natureza VARCHAR,
                municipio VARCHAR,
                uf VARCHAR,
                bairro VARCHAR,
                delegacia VARCHAR,
                tipo_veiculo VARCHAR,
                marca VARCHAR,
                modelo VARCHAR,
                marca_modelo VARCHAR,
                ano_fabricacao INTEGER,
                ano_modelo INTEGER,
                cor VARCHAR,
                placa VARCHAR,
                escopo_rapido VARCHAR,
                is_moto BOOLEAN,
                occurrence_kind VARCHAR,
                department_value VARCHAR,
                department_label VARCHAR,
                query_year INTEGER,
                query_month INTEGER,
                source_label VARCHAR,
                loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    finally:
        con.close()
    return path


def prepare_ssp_rows_for_storage(
    df: pd.DataFrame,
    occurrence_kind: str,
    query_year: int,
    query_month: int,
    department_value: str,
    department_label: str,
    source_label: str,
) -> pd.DataFrame:
    stored = df.copy()
    for column in [
        "bairro",
        "delegacia",
        "tipo_veiculo",
        "marca",
        "modelo",
        "marca_modelo",
        "cor",
        "placa",
        "uf",
        "municipio",
        "natureza",
        "tipo_crime",
        "escopo_rapido",
    ]:
        if column not in stored.columns:
            stored[column] = None

    if "ano_fabricacao" not in stored.columns:
        stored["ano_fabricacao"] = pd.Series([pd.NA] * len(stored), dtype="Int64")
    if "ano_modelo" not in stored.columns:
        stored["ano_modelo"] = pd.Series([pd.NA] * len(stored), dtype="Int64")
    if "is_moto" not in stored.columns:
        stored["is_moto"] = False

    stored["occurrence_kind"] = occurrence_kind
    stored["department_value"] = str(department_value)
    stored["department_label"] = department_label
    stored["query_year"] = int(query_year)
    stored["query_month"] = int(query_month)
    stored["source_label"] = source_label

    ordered_columns = [
        "data_fato",
        "competencia",
        "ano",
        "mes",
        "tipo_crime",
        "natureza",
        "municipio",
        "uf",
        "bairro",
        "delegacia",
        "tipo_veiculo",
        "marca",
        "modelo",
        "marca_modelo",
        "ano_fabricacao",
        "ano_modelo",
        "cor",
        "placa",
        "escopo_rapido",
        "is_moto",
        "occurrence_kind",
        "department_value",
        "department_label",
        "query_year",
        "query_month",
        "source_label",
    ]
    return stored[ordered_columns].copy()


def upsert_ssp_snapshot(
    df: pd.DataFrame,
    occurrence_kind: str,
    query_year: int,
    query_month: int,
    department_value: str,
    department_label: str,
    source_label: str,
    db_path: str | None = None,
    table_name: str = DEFAULT_SSP_TABLE,
) -> int:
    ensure_ssp_database(db_path=db_path, table_name=table_name)
    stored = prepare_ssp_rows_for_storage(
        df=df,
        occurrence_kind=occurrence_kind,
        query_year=query_year,
        query_month=query_month,
        department_value=department_value,
        department_label=department_label,
        source_label=source_label,
    )
    con = connect_ssp_db(db_path, read_only=False)
    try:
        con.execute(
            f"""
            DELETE FROM {table_name}
            WHERE occurrence_kind = ?
              AND query_year = ?
              AND query_month = ?
              AND department_value = ?
            """,
            [occurrence_kind, int(query_year), int(query_month), str(department_value)],
        )
        con.register("ssp_batch", stored)
        con.execute(
            f"""
            INSERT INTO {table_name} (
                data_fato, competencia, ano, mes, tipo_crime, natureza, municipio, uf,
                bairro, delegacia, tipo_veiculo, marca, modelo, marca_modelo,
                ano_fabricacao, ano_modelo, cor, placa, escopo_rapido, is_moto,
                occurrence_kind, department_value, department_label, query_year,
                query_month, source_label
            )
            SELECT
                data_fato, competencia, ano, mes, tipo_crime, natureza, municipio, uf,
                bairro, delegacia, tipo_veiculo, marca, modelo, marca_modelo,
                ano_fabricacao, ano_modelo, cor, placa, escopo_rapido, is_moto,
                occurrence_kind, department_value, department_label, query_year,
                query_month, source_label
            FROM ssp_batch
            """
        )
    finally:
        con.close()
    return int(len(stored))


def read_ssp_rows(
    db_path: str | None = None,
    table_name: str = DEFAULT_SSP_TABLE,
) -> pd.DataFrame:
    path = resolve_ssp_db_path(db_path)
    if not path.exists():
        return pd.DataFrame()
    con = connect_ssp_db(str(path), read_only=True)
    try:
        return con.execute(
            f"""
            SELECT
                data_fato, competencia, ano, mes, tipo_crime, natureza, municipio, uf,
                bairro, delegacia, tipo_veiculo, marca, modelo, marca_modelo,
                ano_fabricacao, ano_modelo, cor, placa, escopo_rapido, is_moto,
                occurrence_kind, department_value, department_label, query_year,
                query_month, source_label, loaded_at
            FROM {table_name}
            ORDER BY data_fato DESC, municipio
            """
        ).df()
    finally:
        con.close()


def list_ssp_loaded_snapshots(
    db_path: str | None = None,
    table_name: str = DEFAULT_SSP_TABLE,
) -> pd.DataFrame:
    path = resolve_ssp_db_path(db_path)
    if not path.exists():
        return pd.DataFrame()
    con = connect_ssp_db(str(path), read_only=True)
    try:
        return con.execute(
            f"""
            SELECT
                occurrence_kind,
                query_year,
                query_month,
                department_value,
                department_label,
                COUNT(*) AS linhas,
                MIN(data_fato) AS menor_data_fato,
                MAX(data_fato) AS maior_data_fato,
                MAX(loaded_at) AS loaded_at
            FROM {table_name}
            GROUP BY 1,2,3,4,5
            ORDER BY query_year DESC, query_month DESC, occurrence_kind, department_value
            """
        ).df()
    finally:
        con.close()
