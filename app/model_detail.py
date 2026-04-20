from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app.db import connect
from app.glossary import enrich_models
from app import queries

HARLEY_ORANGE = "#FF6A13"
MONTH_LABELS_PT = {
    1: "jan",
    2: "fev",
    3: "mar",
    4: "abr",
    5: "mai",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "set",
    10: "out",
    11: "nov",
    12: "dez",
}


DETAIL_PAGE_PATH = "pages/modelo_detalhe.py"


@st.cache_resource
def get_connection(db_path: str):
    return connect(db_path, read_only=True)


@st.cache_data
def get_model_snapshot(db_path: str, modelo: str, competencia: str):
    con = get_connection(db_path)
    return queries.model_snapshot(con, modelo=modelo, competencia=competencia)


@st.cache_data
def get_model_series(db_path: str, modelo: str):
    con = get_connection(db_path)
    return queries.monthly_series(con, modelo=modelo)


@st.cache_data
def get_model_entries(db_path: str, modelo: str):
    con = get_connection(db_path)
    return queries.monthly_entries_proxy(con, modelo=modelo)


@st.cache_data
def get_model_share_by_uf(db_path: str, modelo: str, competencia: str):
    con = get_connection(db_path)
    return queries.model_share_by_uf(con, modelo=modelo, competencia=competencia)


@st.cache_data
def get_model_share_by_city(db_path: str, modelo: str, competencia: str):
    con = get_connection(db_path)
    return queries.model_share_by_city(con, modelo=modelo, competencia=competencia)


def format_reference_month(value: str | pd.Timestamp) -> str:
    ts = pd.Timestamp(value)
    return f"{MONTH_LABELS_PT[int(ts.month)]}/{str(ts.year)[-2:]}"


def set_model_detail_context(modelo: str, db_path: str, competencia: str, ano_fabricacao: int):
    st.session_state["model_detail_modelo"] = modelo
    st.session_state["model_detail_db_path"] = db_path
    st.session_state["model_detail_competencia"] = competencia
    st.session_state["model_detail_ano_fabricacao"] = ano_fabricacao


def render_matrix_detail_selector(
    matrix_df,
    db_path: str,
    competencia: str,
    ano_fabricacao: int,
    key: str,
):
    display_df = matrix_df.copy()
    hidden_cols = [column for column in ["marca_modelo", "nome_exibicao"] if column in display_df.columns]
    if hidden_cols:
        display_df = display_df.drop(columns=hidden_cols)

    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=560,
        key=key,
        on_select="rerun",
        selection_mode="single-row",
    )

    selection = event.selection.rows if event and event.selection else []
    if not selection:
        st.caption("Selecione uma linha e clique em `Exibir detalhe` para abrir a página do modelo.")
        return

    source_col = "codigo_modelo" if "codigo_modelo" in matrix_df.columns else "marca_modelo"
    selected_model = matrix_df.iloc[selection[0]][source_col]
    button_label = f"Exibir detalhe: {selected_model}"
    if st.button(button_label, key=f"{key}_detail_button"):
        set_model_detail_context(
            modelo=selected_model,
            db_path=db_path,
            competencia=competencia,
            ano_fabricacao=ano_fabricacao,
        )
        st.switch_page(DETAIL_PAGE_PATH)


def render_model_detail_page():
    st.title("Detalhe do Modelo")

    modelo = st.session_state.get("model_detail_modelo")
    db_path = st.session_state.get("model_detail_db_path")
    competencia = st.session_state.get("model_detail_competencia")
    ano_fabricacao = st.session_state.get("model_detail_ano_fabricacao")

    if not modelo or not db_path or not competencia:
        st.error("Nenhum modelo foi selecionado no dashboard.")
        st.info("Volte ao dashboard, selecione uma linha e clique em `Exibir detalhe`.")
        st.stop()

    if not Path(str(db_path)).expanduser().exists():
        st.error(f"Banco não encontrado: {db_path}")
        st.stop()

    if st.button("Voltar ao dashboard"):
        st.switch_page("streamlit_app.py")

    reference_month = format_reference_month(str(competencia))
    glossary_df = enrich_models(pd.DataFrame({"marca_modelo": [modelo]}))
    friendly_name = glossary_df.iloc[0]["nome_amigavel"]
    if str(friendly_name).strip():
        st.caption(f"Modelo: {modelo} | Nome amigável: {friendly_name} | Mês de referência: {reference_month} | MY: {ano_fabricacao or '-'}")
    else:
        st.caption(f"Modelo: {modelo} | Mês de referência: {reference_month} | MY: {ano_fabricacao or '-'}")

    snapshot_df = get_model_snapshot(str(db_path), str(modelo), str(competencia))
    series_df = get_model_series(str(db_path), str(modelo))
    entries_df = get_model_entries(str(db_path), str(modelo))
    uf_df = get_model_share_by_uf(str(db_path), str(modelo), str(competencia))
    city_df = get_model_share_by_city(str(db_path), str(modelo), str(competencia))

    if snapshot_df.empty:
        st.warning("Sem dados para este modelo no mês selecionado.")
        st.stop()

    row = snapshot_df.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Frota no mês", f"{int(row['estoque']):,}".replace(",", "."))
    c2.metric("Emplacamentos do mês", f"{max(int(row['delta']), 0):,}".replace(",", "."))
    c3.metric("Mês de referência", format_reference_month(str(row["competencia"])))

    st.divider()

    col1, col2 = st.columns((1, 1))
    with col1:
        st.subheader("Série de frota")
        fig_series = px.line(
            series_df,
            x="competencia",
            y="estoque",
            markers=True,
            title=f"Frota acumulada | {modelo}",
        )
        fig_series.update_layout(xaxis_title="Mês", yaxis_title="Unidades")
        st.plotly_chart(fig_series, use_container_width=True)
    with col2:
        st.subheader("Série de emplacamentos")
        fig_entries = px.line(
            entries_df,
            x="competencia",
            y="emplacamentos_proxy",
            markers=True,
            title=f"Emplacamentos mensais | {modelo}",
        )
        fig_entries.update_layout(xaxis_title="Mês", yaxis_title="Unidades")
        st.plotly_chart(fig_entries, use_container_width=True)

    st.divider()

    col3, col4 = st.columns((1, 1))
    with col3:
        st.subheader(f"Distribuição por UF | {reference_month}")
        st.dataframe(uf_df, use_container_width=True, hide_index=True)
    with col4:
        fig_uf = px.bar(
            uf_df,
            x="uf",
            y="total",
            title=f"Frota por UF | {modelo}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        st.plotly_chart(fig_uf, use_container_width=True)

    st.divider()
    st.subheader(f"Top municípios | {reference_month}")
    st.dataframe(city_df, use_container_width=True, hide_index=True)
