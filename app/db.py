from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "frota_harley.duckdb"

def resolve_db_path(db_path: str | None = None) -> Path:
    if db_path:
        return Path(db_path).expanduser().resolve()
    return DEFAULT_DB.resolve()

def connect(db_path: str | None = None, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    path = resolve_db_path(db_path)
    return duckdb.connect(str(path), read_only=read_only)

def query_df(con: duckdb.DuckDBPyConnection, sql: str, params: list | tuple | None = None) -> pd.DataFrame:
    if params is None:
        return con.execute(sql).df()
    return con.execute(sql, params).df()
