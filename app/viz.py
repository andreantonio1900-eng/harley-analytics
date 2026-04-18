from __future__ import annotations
import plotly.express as px
import plotly.graph_objects as go
from app import queries

def plot_family(con, pattern: str):
    df = queries.family_like(con, pattern)
    if df.empty:
        raise ValueError("Sem dados para esse pattern.")
    agg = df.groupby("competencia", as_index=False)["total"].sum()
    fig = px.line(agg, x="competencia", y="total", markers=True, title=f"Família {pattern}")
    fig.show()

def plot_entries_proxy(con, modelo: str, inicio: str | None = None, fim: str | None = None):
    df = queries.monthly_entries_proxy(con, modelo, inicio=inicio, fim=fim)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["competencia"], y=df["emplacamentos_proxy"], mode="lines+markers", name="Emplacamentos proxy"))
    fig.add_trace(go.Scatter(x=df["competencia"], y=df["estoque"], mode="lines", name="Frota"))
    fig.update_layout(title=f"{modelo}: frota, líquido e emplacamentos proxy", xaxis_title="Competência", yaxis_title="Unidades")
    fig.show()
