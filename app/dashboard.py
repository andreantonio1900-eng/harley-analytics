from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app.db import connect
from app import queries
from app.model_detail import render_matrix_detail_selector

HARLEY_ORANGE = "#FF6A13"


@dataclass(frozen=True)
class DashboardFilters:
    db_path: str
    competencia: str
    ano_fabricacao: int


@st.cache_resource
def get_connection(db_path: str):
    return connect(db_path, read_only=True)


@st.cache_data
def get_competencias(db_path: str) -> list[str]:
    con = get_connection(db_path)
    df = queries.list_competencias(con)
    return [str(value) for value in df["competencia"].tolist()]


@st.cache_data
def get_years(db_path: str) -> list[int]:
    con = get_connection(db_path)
    df = queries.list_years(con)
    return [int(value) for value in df["ano_fabricacao"].tolist()]


@st.cache_data
def get_info(db_path: str):
    con = get_connection(db_path)
    return queries.info(con)


@st.cache_data
def get_share_by_uf(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.share_by_uf(con, competencia=competencia)


@st.cache_data
def get_top_models_national(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.top_models_national(con, competencia=competencia)


@st.cache_data
def get_sem_info_my_monthly_series(db_path: str, ano_fabricacao: int):
    con = get_connection(db_path)
    return queries.sem_info_my_monthly_series(con, ano_modelo=ano_fabricacao)


@st.cache_data
def get_sem_info_my_snapshot(db_path: str, competencia: str, ano_fabricacao: int):
    con = get_connection(db_path)
    return queries.sem_info_my_snapshot(con, competencia=competencia, ano_modelo=ano_fabricacao)


@st.cache_data
def get_sem_info_my_top_models(db_path: str, competencia: str, ano_fabricacao: int):
    con = get_connection(db_path)
    return queries.sem_info_my_top_models(con, competencia=competencia, ano_modelo=ano_fabricacao)


@st.cache_data
def get_sem_info_my_model_series(db_path: str, ano_fabricacao: int):
    con = get_connection(db_path)
    return queries.sem_info_my_model_series(con, ano_modelo=ano_fabricacao)


@st.cache_data
def get_models_by_year(db_path: str, ano_fabricacao: int, competencia: str):
    con = get_connection(db_path)
    return queries.list_models_by_year(con, ano=ano_fabricacao, competencia=competencia)


@st.cache_data
def get_model_year_monthly_matrix(db_path: str, ano_fabricacao: int, competencia: str):
    con = get_connection(db_path)
    return queries.model_year_monthly_matrix(con, ano=ano_fabricacao, competencia=competencia)


@st.cache_data
def get_model_year_registrations_matrix(db_path: str, ano_fabricacao: int, competencia: str):
    con = get_connection(db_path)
    return queries.model_year_registrations_matrix(con, ano=ano_fabricacao, competencia=competencia)


def render_sidebar(default_db_path: str) -> DashboardFilters:
    with st.sidebar:
        st.header("Filtros")
        db_path = st.text_input("Banco DuckDB", value=default_db_path)
        if not Path(db_path).expanduser().exists():
            st.error(f"Banco não encontrado: {db_path}")
            st.stop()

        competencias = get_competencias(db_path)
        years = get_years(db_path)

        if not competencias:
            st.error("Nenhuma competência encontrada no banco.")
            st.stop()

        if not years:
            st.error("Nenhum ano de fabricação encontrado no banco.")
            st.stop()

        competencia = st.selectbox(
            "Competência",
            options=competencias,
            index=len(competencias) - 1,
        )
        ano_fabricacao = st.selectbox(
            "Ano de fabricação",
            options=years,
            index=len(years) - 1,
        )

    return DashboardFilters(
        db_path=db_path,
        competencia=competencia,
        ano_fabricacao=ano_fabricacao,
    )


def render_kpis(db_path: str):
    kpi = get_info(db_path)
    row = kpi.iloc[0]
    st.caption("Como ler: este bloco dá contexto da base inteira, para você saber período coberto, volume total e amplitude do portfólio.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Primeira competência", str(row["primeira_competencia"]))
    c2.metric("Última competência", str(row["ultima_competencia"]))
    c3.metric("Linhas", f"{int(row['linhas']):,}".replace(",", "."))
    c4.metric("Modelos distintos", int(row["modelos_distintos"]))


def render_share_by_uf(db_path: str, competencia: str):
    uf_df = get_share_by_uf(db_path, competencia)

    col1, col2 = st.columns((1, 1))
    with col1:
        st.subheader("Frota por UF")
        st.caption(f"Competência: {competencia}")
        st.caption("Como ler: use esta visão para localizar concentração geográfica. Os primeiros estados são onde a frota está mais forte hoje.")
        st.dataframe(uf_df, use_container_width=True, hide_index=True)
    with col2:
        fig_uf = px.bar(
            uf_df,
            x="uf",
            y="total_hd_uf",
            title=f"Frota por UF | {competencia}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        st.plotly_chart(fig_uf, use_container_width=True)


def render_top_models_national(db_path: str, competencia: str):
    top_df = get_top_models_national(db_path, competencia)

    st.subheader("Harleys mais prevalentes no país")
    st.caption(f"Competência: {competencia}")
    st.caption("Como ler: este ranking mostra os modelos com maior estoque nacional no mês selecionado. É a melhor visão para entender o topo do parque circulante.")

    col1, col2 = st.columns((1, 1))
    with col1:
        st.dataframe(top_df, use_container_width=True, hide_index=True, height=540)
    with col2:
        fig_top = px.bar(
            top_df,
            x="total",
            y="marca_modelo",
            orientation="h",
            title=f"Top 30 modelos no Brasil | {competencia}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig_top.update_layout(
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="Unidades",
            yaxis_title="Modelo",
        )
        st.plotly_chart(fig_top, use_container_width=True)


def render_sem_info_view(db_path: str, competencia: str, ano_fabricacao: int):
    ano_competencia = int(competencia[:4])
    snapshot_df = get_sem_info_my_snapshot(db_path, competencia, ano_fabricacao)
    series_df = get_sem_info_my_monthly_series(db_path, ano_fabricacao)
    top_models_df = get_sem_info_my_top_models(db_path, competencia, ano_fabricacao)
    model_series_df = get_sem_info_my_model_series(db_path, ano_fabricacao)

    st.subheader(f"Estoque pendente de emplacamento | MY {ano_fabricacao}")
    st.caption("Proxy: registros com `SEM INFORMAÇÃO` dentro da janela MY-1 até MY.")
    st.caption("Como ler: pense aqui como um termômetro de estoque em rampa. Se esse bloco sobe, há mais unidades do MY selecionado ainda aguardando emplacamento.")

    if ano_competencia not in {ano_fabricacao - 1, ano_fabricacao}:
        st.info(f"A competência {competencia} está fora da janela operacional deste proxy para o MY {ano_fabricacao}. Use competências em {ano_fabricacao - 1} ou {ano_fabricacao}.")
        return

    if snapshot_df.empty:
        st.info("Sem registros `SEM INFORMAÇÃO` associados ao MY selecionado na competência escolhida.")
        return

    row = snapshot_df.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Unidades sem informação", f"{int(row['total_sem_info']):,}".replace(",", "."))
    c2.metric("Modelos afetados", int(row["modelos"]))
    c3.metric("Delta vs mês anterior", f"{int(row['delta_sem_info']):+,}".replace(",", "."))

    col1, col2 = st.columns((1, 1))
    with col1:
        st.subheader("Top modelos")
        st.caption(f"Competência: {competencia}")
        st.caption("Como ler: a tabela mostra quais modelos mais puxam esse estoque pendente no mês selecionado.")
        st.dataframe(top_models_df, use_container_width=True, hide_index=True, height=420)
    with col2:
        fig_top = px.bar(
            top_models_df.head(12),
            x="marca_modelo",
            y="total_sem_info",
            title=f"Top modelos | MY {ano_fabricacao} | {competencia}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        st.plotly_chart(fig_top, use_container_width=True)

    trend_df = series_df.copy()
    trend_df["competencia_label"] = trend_df["competencia"].astype(str)
    fig_series = px.line(
        trend_df,
        x="competencia_label",
        y="total_sem_info",
        markers=True,
        title=f"Evolução do estoque pendente | MY {ano_fabricacao}",
    )
    fig_series.update_layout(
        xaxis_title="Competência",
        yaxis_title="Unidades",
    )
    st.plotly_chart(fig_series, use_container_width=True)

    if not top_models_df.empty and not model_series_df.empty:
        tracked_models = top_models_df.head(8)["marca_modelo"].tolist()
        detail_df = model_series_df[model_series_df["marca_modelo"].isin(tracked_models)].copy()
        detail_df["competencia_label"] = detail_df["competencia"].astype(str)
        fig_detail = px.line(
            detail_df,
            x="competencia_label",
            y="total_sem_info",
            color="marca_modelo",
            markers=True,
            title=f"Evolução por modelo | MY {ano_fabricacao}",
        )
        fig_detail.update_layout(
            xaxis_title="Competência",
            yaxis_title="Unidades",
            legend_title_text="Modelo",
        )
        st.plotly_chart(fig_detail, use_container_width=True)


def build_line_chart_df(matrix_df, top_n: int = 8):
    month_order = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
    available_months = [month for month in month_order if month in matrix_df.columns]
    if not available_months:
        return pd.DataFrame()

    month_labels = {
        "jan": "Jan",
        "fev": "Fev",
        "mar": "Mar",
        "abr": "Abr",
        "mai": "Mai",
        "jun": "Jun",
        "jul": "Jul",
        "ago": "Ago",
        "set": "Set",
        "out": "Out",
        "nov": "Nov",
        "dez": "Dez",
    }

    value_frame = matrix_df[["marca_modelo", *available_months]].copy()
    score = value_frame[available_months].fillna(0)
    top_models = (
        score.sum(axis=1)
        .sort_values(ascending=False)
        .head(top_n)
        .index
    )

    chart_df = value_frame.loc[top_models].melt(
        id_vars="marca_modelo",
        value_vars=available_months,
        var_name="mes",
        value_name="valor",
    )
    chart_df = chart_df.dropna(subset=["valor"])
    chart_df["mes"] = pd.Categorical(chart_df["mes"], categories=available_months, ordered=True)
    chart_df["mes_label"] = chart_df["mes"].map(month_labels)
    return chart_df.sort_values(["mes", "valor"], ascending=[True, False])


def render_matrix_line_chart(matrix_df, title: str, y_axis_title: str):
    chart_df = build_line_chart_df(matrix_df)
    if chart_df.empty:
        return

    fig = px.line(
        chart_df,
        x="mes_label",
        y="valor",
        color="marca_modelo",
        markers=True,
        title=title,
    )
    fig.update_layout(
        xaxis_title="Mês",
        yaxis_title=y_axis_title,
        legend_title_text="Modelo",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_models_by_year(db_path: str, ano_fabricacao: int, competencia: str):
    matrix_df = get_model_year_monthly_matrix(db_path, ano_fabricacao, competencia)
    registrations_df = get_model_year_registrations_matrix(db_path, ano_fabricacao, competencia)
    ano_competencia = competencia[:4]

    st.subheader(f"Modelos | MY {ano_fabricacao}")
    st.caption(f"Competência: {competencia}")
    st.caption("Como ler: aqui o foco sai do macro e entra no mix de produto. Use as abas para alternar entre estoque acumulado e emplacamentos mensais.")

    tab_frota, tab_emplacamentos = st.tabs(["Frota", "Emplacamentos"])

    with tab_frota:
        st.caption("Como ler: cada linha é um modelo. As colunas mostram a evolução do estoque ao longo do ano. Selecione uma linha para abrir o detalhe.")
        render_matrix_detail_selector(
            matrix_df,
            db_path=db_path,
            competencia=competencia,
            ano_fabricacao=ano_fabricacao,
            key="fleet_matrix",
        )
        render_matrix_line_chart(
            matrix_df,
            title=f"Evolução da frota | MY {ano_fabricacao}",
            y_axis_title="Frota",
        )

    with tab_emplacamentos:
        st.caption("Como ler: aqui cada célula representa entrada do mês, não estoque. É a melhor visão para entender ritmo de emplacamento por modelo.")
        render_matrix_detail_selector(
            registrations_df,
            db_path=db_path,
            competencia=competencia,
            ano_fabricacao=ano_fabricacao,
            key="registrations_matrix",
        )
        render_matrix_line_chart(
            registrations_df,
            title=f"Emplacamentos mensais | MY {ano_fabricacao}",
            y_axis_title="Emplacamentos",
        )


def render_dashboard(default_db_path: str):
    st.title("Harley Analytics")
    st.caption("Visão macro da frota Harley-Davidson")

    filters = render_sidebar(default_db_path)

    render_kpis(filters.db_path)
    st.divider()
    render_share_by_uf(filters.db_path, filters.competencia)
    st.divider()
    render_top_models_national(filters.db_path, filters.competencia)
    st.divider()
    render_sem_info_view(filters.db_path, filters.competencia, filters.ano_fabricacao)
    st.divider()
    render_models_by_year(filters.db_path, filters.ano_fabricacao, filters.competencia)
