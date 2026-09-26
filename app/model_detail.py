from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app.glossary import enrich_models
from app.db import connect
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
def get_model_snapshot(db_path: str, modelo: str, competencia: str, ano_fabricacao: int | None = None):
    con = get_connection(db_path)
    return queries.model_snapshot(
        con,
        modelo=modelo,
        competencia=competencia,
        ano_fabricacao=ano_fabricacao,
    )


@st.cache_data
def get_model_series(db_path: str, modelo: str, ano_fabricacao: int | None = None):
    con = get_connection(db_path)
    return queries.monthly_series(con, modelo=modelo, ano_fabricacao=ano_fabricacao)


@st.cache_data
def get_model_entries(db_path: str, modelo: str, ano_fabricacao: int | None = None):
    con = get_connection(db_path)
    return queries.monthly_entries_proxy(con, modelo=modelo, ano_fabricacao=ano_fabricacao)


@st.cache_data
def get_model_share_by_uf(
    db_path: str,
    modelo: str,
    competencia: str,
    ano_fabricacao: int | None = None,
):
    con = get_connection(db_path)
    return queries.model_share_by_uf(
        con,
        modelo=modelo,
        competencia=competencia,
        ano_fabricacao=ano_fabricacao,
    )


@st.cache_data
def get_model_share_by_city(
    db_path: str,
    modelo: str,
    competencia: str,
    ano_fabricacao: int | None = None,
):
    con = get_connection(db_path)
    return queries.model_share_by_city(
        con,
        modelo=modelo,
        competencia=competencia,
        ano_fabricacao=ano_fabricacao,
    )


@st.cache_data
def get_cvo_models(db_path: str):
    con = get_connection(db_path)
    base_df = enrich_models(queries.list_cvo_models(con))
    if base_df.empty:
        return base_df

    cvo_df = base_df[
        base_df.apply(
            lambda row: is_special_edition_model(
                row["codigo_modelo"], row["nome_amigavel"]
            ),
            axis=1,
        )
    ].copy()
    return cvo_df.sort_values(["nome_exibicao", "codigo_modelo"]).reset_index(drop=True)


@st.cache_data
def get_model_years(db_path: str, modelo: str):
    con = get_connection(db_path)
    year_df = queries.list_model_years(con, modelo=modelo)
    if year_df.empty:
        return []
    return [int(value) for value in year_df["ano_fabricacao"].dropna().tolist()]


@st.cache_data
def get_model_territory_series(db_path: str, modelo: str, ano_fabricacao: int):
    con = get_connection(db_path)
    return queries.model_year_territory_series(con, modelo=modelo, ano_fabricacao=ano_fabricacao)


def format_reference_month(value: str | pd.Timestamp) -> str:
    ts = pd.Timestamp(value)
    return f"{MONTH_LABELS_PT[int(ts.month)]}/{str(ts.year)[-2:]}"


def set_model_detail_context(modelo: str, db_path: str, competencia: str, ano_fabricacao: int | None):
    st.session_state["model_detail_modelo"] = modelo
    st.session_state["model_detail_db_path"] = db_path
    st.session_state["model_detail_competencia"] = competencia
    st.session_state["model_detail_ano_fabricacao"] = ano_fabricacao


def is_cvo_model(code: str, friendly_name: str) -> bool:
    code_upper = str(code).strip().upper().replace(" ", "")
    friendly_upper = str(friendly_name).strip().upper()
    return "CVO" in friendly_upper or code_upper.endswith("SE")


def is_special_edition_model(code: str, friendly_name: str) -> bool:
    friendly_upper = str(friendly_name).strip().upper()
    return is_cvo_model(code, friendly_name) or "GRAY GHOST" in friendly_upper


def format_territory_label(municipio: str | None, uf: str | None) -> str:
    city = str(municipio or "Sem informação").strip().title()
    state = str(uf or "Sem informação").strip().title()
    return f"{city} / {state}"


def build_cvo_tracker_df(history_df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    if history_df.empty:
        return pd.DataFrame(columns=["Unidade"]), 0, 0

    base_df = history_df.copy()
    base_df["competencia"] = pd.to_datetime(base_df["competencia"])
    grouped = (
        base_df.groupby(["competencia", "uf", "municipio"], dropna=False, as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["competencia", "uf", "municipio"])
    )

    monthly_snapshots: list[tuple[pd.Timestamp, dict[tuple[str, str], int]]] = []
    for competencia, month_df in grouped.groupby("competencia", sort=True):
        territory_counts: dict[tuple[str, str], int] = {}
        for row in month_df.itertuples(index=False):
            territory = (str(row.uf or ""), str(row.municipio or ""))
            territory_counts[territory] = int(row.qtd_veiculos)
        monthly_snapshots.append((pd.Timestamp(competencia), territory_counts))

    peak_units = max(sum(counts.values()) for _, counts in monthly_snapshots)
    active_by_territory: dict[tuple[str, str], list[int]] = defaultdict(list)
    available_units: list[int] = []
    unit_events: dict[int, list[str]] = defaultdict(list)
    next_unit_id = 1
    previous_counts: dict[tuple[str, str], int] = {}

    for competencia, current_counts in monthly_snapshots:
        territories = sorted(set(previous_counts) | set(current_counts))
        for territory in territories:
            delta = current_counts.get(territory, 0) - previous_counts.get(territory, 0)
            if delta >= 0:
                continue
            units_here = active_by_territory[territory]
            for _ in range(abs(delta)):
                if not units_here:
                    break
                available_units.append(units_here.pop())

        for territory in territories:
            delta = current_counts.get(territory, 0) - previous_counts.get(territory, 0)
            if delta <= 0:
                continue
            for _ in range(delta):
                if available_units:
                    unit_id = available_units.pop(0)
                else:
                    unit_id = next_unit_id
                    next_unit_id += 1
                event_label = f"{format_reference_month(competencia)} | {format_territory_label(territory[1], territory[0])}"
                if not unit_events[unit_id] or unit_events[unit_id][-1] != event_label:
                    unit_events[unit_id].append(event_label)
                active_by_territory[territory].append(unit_id)
        previous_counts = current_counts

    current_assignments: dict[int, str] = {}
    for territory, unit_ids in active_by_territory.items():
        territory_label = format_territory_label(territory[1], territory[0])
        for unit_id in unit_ids:
            current_assignments[unit_id] = territory_label

    total_units = max(peak_units, next_unit_id - 1)
    max_events = max((len(events) for events in unit_events.values()), default=0)
    rows: list[dict[str, str]] = []
    for unit_id in range(1, total_units + 1):
        row = {
            "Unidade": f"Unidade {unit_id:02d}",
            "Status atual": current_assignments.get(unit_id, "Fora da foto atual"),
        }
        events = unit_events.get(unit_id, [])
        for index in range(max_events):
            row[f"Lic. {index + 1}"] = events[index] if index < len(events) else ""
        rows.append(row)

    tracker_df = pd.DataFrame(rows)
    ordered_columns = ["Unidade", *[f"Lic. {index + 1}" for index in range(max_events)], "Status atual"]
    return tracker_df[ordered_columns], peak_units, len(current_assignments)


def render_cvo_tracker(db_path: str, default_modelo: str, default_ano_fabricacao: int | None):
    st.subheader("Special Edition Tracker")
    st.caption(
        "Como ler: cada linha representa uma unidade estimada do lote brasileiro daquela edição especial. "
        "As colunas `Lic.` mostram a sequência territorial reconstruída a partir das mudanças mensais de estoque por município."
    )

    cvo_models_df = get_cvo_models(db_path)
    if cvo_models_df.empty:
        st.info("Nenhuma edição especial com MY identificado foi encontrada na base Harley.")
        return

    cvo_options = cvo_models_df["codigo_modelo"].tolist()
    default_model = default_modelo if default_modelo in cvo_options else cvo_options[0]
    selected_model = st.selectbox(
        "Edição especial",
        options=cvo_options,
        index=cvo_options.index(default_model),
        format_func=lambda code: cvo_models_df.loc[
            cvo_models_df["codigo_modelo"] == code,
            "nome_exibicao",
        ].iloc[0],
        key="special_edition_tracker_model_selector_v2",
    )

    available_years = get_model_years(db_path, selected_model)
    if not available_years:
        st.info("Essa edição ainda não tem ano-modelo estruturado na base.")
        return

    default_year = default_ano_fabricacao if default_ano_fabricacao in available_years else available_years[-1]
    selected_year = st.selectbox(
        "Ano-modelo da edição",
        options=available_years,
        index=available_years.index(default_year),
        format_func=lambda year: f"MY {year}",
        key="special_edition_tracker_year_selector_v2",
    )

    selected_meta = cvo_models_df.loc[cvo_models_df["codigo_modelo"] == selected_model].iloc[0]
    st.caption(
        f"Edição selecionada: {selected_meta['nome_exibicao']} | MY {selected_year}"
    )

    territory_series_df = get_model_territory_series(db_path, selected_model, selected_year)
    if territory_series_df.empty:
        st.info("Sem histórico territorial para essa edição no ano-modelo selecionado.")
        return

    tracker_df, peak_units, current_units = build_cvo_tracker_df(territory_series_df)
    max_licenses = max(
        [int(column.split(". ")[1]) for column in tracker_df.columns if column.startswith("Lic. ")],
        default=0,
    )
    latest_month = format_reference_month(territory_series_df["competencia"].max())

    k1, k2, k3 = st.columns(3)
    k1.metric("Pico de unidades rastreadas", f"{peak_units:,}".replace(",", "."))
    k2.metric("Unidades na foto atual", f"{current_units:,}".replace(",", "."), delta=latest_month)
    k3.metric("Máx. de licenças na trilha", f"{max_licenses:,}".replace(",", "."))

    territory_snapshot_df = (
        territory_series_df.assign(competencia=pd.to_datetime(territory_series_df["competencia"]))
        .sort_values("competencia")
    )
    latest_competencia = territory_snapshot_df["competencia"].max()
    latest_snapshot_df = territory_snapshot_df[territory_snapshot_df["competencia"] == latest_competencia].copy()
    latest_snapshot_df["territorio"] = latest_snapshot_df.apply(
        lambda row: format_territory_label(row["municipio"], row["uf"]),
        axis=1,
    )
    latest_snapshot_df = latest_snapshot_df.sort_values(["qtd_veiculos", "territorio"], ascending=[False, True])

    st.dataframe(
        tracker_df,
        use_container_width=True,
        hide_index=True,
        height=min(560, 70 + len(tracker_df) * 35),
    )

    st.caption(
        "Leitura importante: como a base é agregada por município e mês, a trilha por unidade é uma reconstrução analítica. "
        "Ela é ótima para enxergar alocação original e migrações prováveis, mas não substitui VIN/chassi."
    )

    with st.expander("Ver distribuição atual da edição por território"):
        st.dataframe(
            latest_snapshot_df[["territorio", "qtd_veiculos"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "territorio": "Território atual",
                "qtd_veiculos": "Unidades",
            },
        )


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
        st.caption(f"Código modelo: {modelo} | Nome comercial: {friendly_name} | Mês de referência: {reference_month} | MY: {ano_fabricacao or '-'}")
    else:
        st.caption(f"Modelo: {modelo} | Mês de referência: {reference_month} | MY: {ano_fabricacao or '-'}")

    snapshot_df = get_model_snapshot(
        str(db_path),
        str(modelo),
        str(competencia),
        ano_fabricacao=ano_fabricacao,
    )
    series_df = get_model_series(str(db_path), str(modelo), ano_fabricacao=ano_fabricacao)
    entries_df = get_model_entries(str(db_path), str(modelo), ano_fabricacao=ano_fabricacao)
    uf_df = get_model_share_by_uf(
        str(db_path),
        str(modelo),
        str(competencia),
        ano_fabricacao=ano_fabricacao,
    )
    city_df = get_model_share_by_city(
        str(db_path),
        str(modelo),
        str(competencia),
        ano_fabricacao=ano_fabricacao,
    )

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
            title=f"Frota acumulada | {modelo}" + (f" | MY {ano_fabricacao}" if ano_fabricacao else ""),
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
            title=f"Emplacamentos mensais | {modelo}" + (f" | MY {ano_fabricacao}" if ano_fabricacao else ""),
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

    st.divider()
    render_cvo_tracker(
        db_path=str(db_path),
        default_modelo=str(modelo),
        default_ano_fabricacao=ano_fabricacao,
    )
