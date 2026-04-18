from __future__ import annotations
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from app.db import connect, resolve_db_path
from app import queries, viz

app = typer.Typer(help="CLI local para análise do banco Harley")
console = Console()

def _render_df(df, title: str = "Resultado"):
    if df.empty:
        console.print(f"[yellow]{title}: sem linhas[/yellow]")
        return
    table = Table(title=title)
    for col in df.columns:
        table.add_column(str(col))
    for row in df.fillna("").astype(str).itertuples(index=False):
        table.add_row(*row)
    console.print(table)

@app.command()
def info(
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    df = queries.info(con)
    _render_df(df, title=f"Info | {resolve_db_path(db)}")

@app.command()
def modelos(
    ano: int = typer.Option(..., "--ano"),
    competencia: Optional[str] = typer.Option(None, "--competencia"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    df = queries.list_models_by_year(con, ano=ano, competencia=competencia)
    _render_df(df, title=f"Modelos {ano}")

@app.command("frota-modelo")
def frota_modelo(
    modelo: str = typer.Option(..., "--modelo"),
    competencia: Optional[str] = typer.Option(None, "--competencia"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    df = queries.fleet_model(con, modelo=modelo, competencia=competencia)
    _render_df(df, title=f"Frota modelo | {modelo}")

@app.command("variacao-modelo")
def variacao_modelo(
    modelo: str = typer.Option(..., "--modelo"),
    de_: str = typer.Option(..., "--de"),
    para: str = typer.Option(..., "--para"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    df = queries.model_variation(con, modelo=modelo, inicio=de_, fim=para)
    _render_df(df, title=f"Variação | {modelo}")

@app.command("serie-modelo")
def serie_modelo(
    modelo: str = typer.Option(..., "--modelo"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    df = queries.monthly_series(con, modelo=modelo)
    _render_df(df, title=f"Série mensal | {modelo}")

@app.command("entradas-modelo")
def entradas_modelo(
    modelo: str = typer.Option(..., "--modelo"),
    inicio: Optional[str] = typer.Option(None, "--inicio"),
    fim: Optional[str] = typer.Option(None, "--fim"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    df = queries.monthly_entries_proxy(con, modelo=modelo, inicio=inicio, fim=fim)
    _render_df(df, title=f"Entradas proxy | {modelo}")

@app.command("share-uf")
def share_uf(
    competencia: str = typer.Option(..., "--competencia"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    df = queries.share_by_uf(con, competencia=competencia)
    _render_df(df, title=f"Share por UF | {competencia}")

@app.command("familia")
def familia(
    pattern: str = typer.Option(..., "--pattern"),
    grafico: bool = typer.Option(False, "--grafico"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    if grafico:
        viz.plot_family(con, pattern)
        return
    df = queries.family_like(con, pattern=pattern)
    _render_df(df, title=f"Família | {pattern}")

@app.command("grafico-modelo")
def grafico_modelo(
    modelo: str = typer.Option(..., "--modelo"),
    inicio: Optional[str] = typer.Option(None, "--inicio"),
    fim: Optional[str] = typer.Option(None, "--fim"),
    db: str = typer.Option(None, "--db", help="Path do banco DuckDB")
):
    con = connect(db, read_only=True)
    viz.plot_entries_proxy(con, modelo=modelo, inicio=inicio, fim=fim)

if __name__ == "__main__":
    app()
