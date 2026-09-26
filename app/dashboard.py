from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.db import connect
from app.glossary import enrich_models
from app import queries
from app.model_detail import render_matrix_detail_selector, set_model_detail_context

HARLEY_ORANGE = "#FF6A13"
INVENTORY_QUERY_VERSION = 3
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
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "harley_davidson_logo.jpg"


@dataclass(frozen=True)
class DashboardFilters:
    db_path: str
    competencia: str


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
def get_fleet_national_snapshot(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.fleet_national_snapshot(con, competencia=competencia)


@st.cache_data
def get_share_by_uf(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.share_by_uf(con, competencia=competencia)


@st.cache_data
def get_top_models_national(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.top_models_national(con, competencia=competencia)


@st.cache_data
def get_top_model_year_national(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.top_model_year_national(con, competencia=competencia)


@st.cache_data
def get_top_model_national_snapshot(db_path: str, competencia: str):
    con = get_connection(db_path)
    return enrich_models(queries.top_model_national_snapshot(con, competencia=competencia))


@st.cache_data
def get_registrations_macro_monthly(db_path: str):
    con = get_connection(db_path)
    return queries.registrations_macro_monthly(con)


@st.cache_data
def get_search_model_instances(db_path: str, pattern: str):
    con = get_connection(db_path)
    return queries.search_model_instances(con, pattern=pattern)


@st.cache_data
def get_commercial_year_stock_series(
    db_path: str,
    ano_comercial: int,
    competencia: str,
    inventory_query_version: int,
):
    con = get_connection(db_path)
    return queries.commercial_year_stock_model_series(
        con,
        ano_comercial=ano_comercial,
        competencia_corte=competencia,
    )


@st.cache_data
def get_commercial_year_stock_snapshot(
    db_path: str,
    ano_comercial: int,
    competencia: str,
    inventory_query_version: int,
):
    con = get_connection(db_path)
    return queries.commercial_year_stock_snapshot(
        con,
        ano_comercial=ano_comercial,
        competencia_corte=competencia,
    )


@st.cache_data
def get_commercial_year_stock_top_models(
    db_path: str,
    ano_comercial: int,
    competencia: str,
    inventory_query_version: int,
):
    con = get_connection(db_path)
    return queries.commercial_year_stock_top_models(
        con,
        ano_comercial=ano_comercial,
        competencia_corte=competencia,
        limit=500,
    )


@st.cache_data
def get_inventory_vs_territorialized_series(
    db_path: str,
    marca_modelo: str,
    competencia: str,
    inventory_query_version: int,
):
    con = get_connection(db_path)
    return queries.inventory_vs_territorialized_series(
        con,
        marca_modelo=marca_modelo,
        competencia_corte=competencia,
    )


@st.cache_data
def get_inventory_tracking_models(
    db_path: str,
    competencia: str,
    inventory_query_version: int,
):
    con = get_connection(db_path)
    return enrich_models(queries.inventory_tracking_models(con, competencia))


@st.cache_data
def get_models_by_year(db_path: str, ano_fabricacao: int, competencia: str):
    con = get_connection(db_path)
    return queries.list_models_by_year(con, ano=ano_fabricacao, competencia=competencia)


@st.cache_data
def get_model_year_monthly_matrix(db_path: str, anos_fabricacao: tuple[int, ...], competencia: str):
    con = get_connection(db_path)
    return queries.model_year_monthly_matrix(
        con,
        anos=list(anos_fabricacao),
        competencia=competencia,
        ano_comercial=pd.Timestamp(competencia).year,
    )


@st.cache_data
def get_model_year_registrations_matrix(db_path: str, anos_fabricacao: tuple[int, ...], competencia: str):
    con = get_connection(db_path)
    return queries.model_year_registrations_matrix(
        con,
        anos=list(anos_fabricacao),
        competencia=competencia,
        ano_comercial=pd.Timestamp(competencia).year,
    )


@st.cache_data
def get_model_year_monthly_matrix_by_commercial_year(
    db_path: str,
    anos_fabricacao: tuple[int, ...],
    competencia: str,
    ano_comercial: int,
):
    con = get_connection(db_path)
    return queries.model_year_monthly_matrix(
        con,
        anos=list(anos_fabricacao),
        competencia=competencia,
        ano_comercial=ano_comercial,
    )


@st.cache_data
def get_model_year_registrations_matrix_by_commercial_year(
    db_path: str,
    anos_fabricacao: tuple[int, ...],
    competencia: str,
    ano_comercial: int,
):
    con = get_connection(db_path)
    return queries.model_year_registrations_matrix(
        con,
        anos=list(anos_fabricacao),
        competencia=competencia,
        ano_comercial=ano_comercial,
    )


@st.cache_data
def get_model_year_territory_snapshot(
    db_path: str,
    anos_fabricacao: tuple[int, ...],
    competencia: str,
    granularity: str,
):
    con = get_connection(db_path)
    return queries.model_year_territory_snapshot(
        con,
        anos=list(anos_fabricacao),
        competencia=competencia,
        granularity=granularity,
    )


def format_reference_month(value: str | pd.Timestamp) -> str:
    ts = pd.Timestamp(value)
    return f"{MONTH_LABELS_PT[int(ts.month)]}/{str(ts.year)[-2:]}"


def get_valid_years_for_reference(db_path: str, competencia: str) -> list[int]:
    reference_year = pd.Timestamp(competencia).year
    return [year for year in get_years(db_path) if year <= reference_year]


def get_commercial_years(db_path: str, competencia: str) -> list[int]:
    reference_ts = pd.Timestamp(competencia)
    competencia_years = sorted({pd.Timestamp(value).year for value in get_competencias(db_path)})
    return [year for year in competencia_years if year <= reference_ts.year]


def format_year_selection_label(years: list[int]) -> str:
    if not years:
        return "Sem MY"
    if len(years) == 1:
        return f"MY {years[0]}"
    return "MYs " + ", ".join(str(year) for year in years)


def render_header(subtitle: str = "Visão macro da frota Harley-Davidson"):
    col_logo, col_copy = st.columns((1, 3))
    with col_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
    with col_copy:
        st.markdown(
            f"""
            <div style="padding-top: 1.1rem;">
                <h1 style="margin: 0; font-size: 2.3rem; line-height: 1;">Harley Analytics</h1>
                <p style="margin: 0.45rem 0 0 0; color: #B8BDC7; font-size: 1rem;">
                    {subtitle}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


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
            st.error("Nenhum mês de referência encontrado no banco.")
            st.stop()

        if not years:
            st.error("Nenhum ano de fabricação encontrado no banco.")
            st.stop()

        competencia = st.selectbox(
            "Mês de referência",
            options=competencias,
            index=len(competencias) - 1,
            format_func=format_reference_month,
        )
        st.caption("Escolha o mês que você quer analisar. Para frota, ele representa a foto do mês. Para emplacamentos, é o mês final da série.")
    return DashboardFilters(
        db_path=db_path,
        competencia=competencia,
    )


def render_kpis(db_path: str, competencia: str):
    st.markdown(
        """
        <style>
        [data-testid="stMetric"] {
            overflow: visible;
        }
        [data-testid="stMetricLabel"] p,
        [data-testid="stMetricValue"],
        [data-testid="stMetricValue"] > div,
        [data-testid="stMetricDelta"] > div {
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
            overflow-wrap: anywhere;
            word-break: normal;
            line-height: 1.15;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    kpi = get_info(db_path)
    fleet_snapshot = get_fleet_national_snapshot(db_path, competencia)
    top_model_year = get_top_model_year_national(db_path, competencia)
    top_model = get_top_model_national_snapshot(db_path, competencia)
    row = kpi.iloc[0]
    st.caption("Como ler: este bloco dá contexto da base inteira, para você saber período coberto, volume total e amplitude do portfólio.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Modelos distintos", int(row["modelos_distintos"]))
    if fleet_snapshot.empty:
        c2.metric("Frota nacional", "n/d")
    else:
        fleet_row = fleet_snapshot.iloc[0]
        delta_value = None if pd.isna(fleet_row["mom_pct"]) else f"{fleet_row['mom_pct']:.2f}%"
        c2.metric(
            "Frota nacional",
            f"{int(fleet_row['frota_total']):,}".replace(",", "."),
            delta=delta_value,
        )
    if top_model_year.empty:
        c3.metric("MY mais prevalente", "n/d")
    else:
        top_row = top_model_year.iloc[0]
        c3.metric(
            "MY mais prevalente",
            f"MY {int(top_row['ano_fabricacao'])}",
            delta=f"{int(top_row['total']):,} un.".replace(",", "."),
        )
    if top_model.empty:
        c4.metric("Moto mais prevalente", "n/d")
    else:
        top_model_row = top_model.iloc[0]
        c4.metric(
            "Moto mais prevalente",
            top_model_row["nome_exibicao"],
            delta=f"{int(top_model_row['total']):,} un.".replace(",", "."),
        )


def render_share_by_uf(db_path: str, competencia: str):
    uf_df = get_share_by_uf(db_path, competencia)
    reference_month = format_reference_month(competencia)
    identified_df = uf_df[
        ~uf_df["uf"].astype(str).str.upper().str.startswith("SEM INFORMA")
    ].copy()
    if identified_df.empty:
        st.info("Sem distribuição estadual identificada para o mês selecionado.")
        return

    identified_total = float(identified_df["total_hd_uf"].sum())
    identified_df["share_identificado"] = (
        100.0 * identified_df["total_hd_uf"] / identified_total
    )
    identified_df["estado"] = identified_df["uf"].astype(str).str.title()
    identified_df = identified_df.sort_values("total_hd_uf", ascending=False)

    leader = identified_df.iloc[0]
    top5_share = float(identified_df.head(5)["share_identificado"].sum())

    st.subheader("Distribuição da Frota por Estado")
    st.caption(
        f"Onde está concentrada a frota Harley-Davidson no Brasil em {reference_month}. "
        "As barras representam a quantidade de motos; os rótulos também mostram a "
        "participação de cada estado na frota com UF identificada."
    )

    metric1, metric2 = st.columns(2)
    metric1.metric(
        "Estado líder",
        str(leader["estado"]),
        delta=(
            f"{int(leader['total_hd_uf']):,} unidades · "
            f"{leader['share_identificado']:.1f}%"
        ).replace(",", "."),
    )
    metric2.metric("Concentração nas 5 maiores UFs", f"{top5_share:.1f}%")

    chart_df = identified_df[
        ["estado", "total_hd_uf", "share_identificado"]
    ].copy()

    chart_df["rotulo"] = chart_df.apply(
        lambda row: (
            f"{int(row['total_hd_uf']):,} · {row['share_identificado']:.1f}%"
        ).replace(",", "."),
        axis=1,
    )
    plot_df = chart_df.sort_values("total_hd_uf", ascending=True)
    fig_uf = go.Figure(
        go.Bar(
            x=plot_df["total_hd_uf"],
            y=plot_df["estado"],
            orientation="h",
            marker_color=HARLEY_ORANGE,
            text=plot_df["rotulo"],
            textposition="outside",
            customdata=plot_df[["total_hd_uf", "share_identificado"]],
            hovertemplate=(
                "%{y}<br>Frota: %{customdata[0]:,.0f}"
                "<br>Participação: %{customdata[1]:.1f}%<extra></extra>"
            ),
        )
    )
    fig_uf.update_layout(
        title=f"Todas as UFs | {reference_month}",
        xaxis_title="Quantidade de motos",
        yaxis_title=None,
        showlegend=False,
        height=max(620, 29 * len(chart_df) + 120),
        margin={"l": 10, "r": 90, "t": 60, "b": 40},
    )
    st.plotly_chart(fig_uf, use_container_width=True)

    unidentified_total = int(uf_df.loc[~uf_df.index.isin(identified_df.index), "total_hd_uf"].sum())
    if unidentified_total:
        st.caption(
            f"{unidentified_total:,} unidades sem UF identificada foram excluídas da distribuição geográfica."
            .replace(",", ".")
        )


def render_top_models_national(db_path: str, competencia: str):
    top_df = enrich_models(get_top_models_national(db_path, competencia))
    reference_month = format_reference_month(competencia)

    st.subheader("Harleys mais prevalentes no país")
    st.caption(f"Mês de referência: {reference_month}")
    st.caption("Como ler: este ranking mostra os modelos com maior estoque nacional no mês selecionado. É a melhor visão para entender o topo do parque circulante.")

    col1, col2 = st.columns((1, 1))
    with col1:
        st.dataframe(
            top_df[["codigo_modelo", "nome_amigavel", "total"]],
            use_container_width=True,
            hide_index=True,
            height=540,
            column_config={
                "codigo_modelo": "Codigo",
                "nome_amigavel": "Nome amigavel",
                "total": "Frota",
            },
        )
    with col2:
        fig_top = px.bar(
            top_df,
            x="total",
            y="nome_exibicao",
            orientation="h",
            title=f"Top 30 modelos no Brasil | {reference_month}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig_top.update_layout(
            yaxis={"categoryorder": "total ascending"},
            xaxis_title="Unidades",
            yaxis_title="Modelo",
        )
        st.plotly_chart(fig_top, use_container_width=True)


def build_registrations_macro_chart_df(
    registrations_df: pd.DataFrame,
    competencia: str,
    aggregation: str,
    range_months: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[int]]:
    end_date = pd.Timestamp(competencia)

    df = registrations_df.copy()
    df["competencia"] = pd.to_datetime(df["competencia"])
    if range_months is not None:
        start_date = end_date - pd.DateOffset(months=range_months - 1)
        df = df[(df["competencia"] >= start_date) & (df["competencia"] <= end_date)]
    else:
        df = df[df["competencia"] <= end_date]

    if aggregation == "Mensal":
        df["period_start"] = df["competencia"]
        df["period_label"] = df["competencia"].dt.strftime("%b/%y")
    elif aggregation == "Bimestral":
        df["bimester"] = ((df["competencia"].dt.month - 1) // 2) + 1
        df["period_start"] = pd.to_datetime(
            {
                "year": df["competencia"].dt.year,
                "month": (df["bimester"] * 2) - 1,
                "day": 1,
            }
        )
        df["period_label"] = "B" + df["bimester"].astype(str) + "/" + df["competencia"].dt.year.astype(str)
    elif aggregation == "Trimestral":
        period = df["competencia"].dt.to_period("Q")
        df["period_start"] = period.dt.start_time
        df["period_label"] = period.astype(str).str.replace("Q", "T", regex=False)
    else:
        df["semester"] = df["competencia"].dt.month.map(lambda month: 1 if month <= 6 else 2)
        df["period_start"] = pd.to_datetime(
            {
                "year": df["competencia"].dt.year,
                "month": df["semester"].map({1: 1, 2: 7}),
                "day": 1,
            }
        )
        df["period_label"] = "S" + df["semester"].astype(str) + "/" + df["competencia"].dt.year.astype(str)

    by_year = (
        df.dropna(subset=["ano_fabricacao"])
        .groupby(["period_start", "period_label", "ano_fabricacao"], as_index=False)["emplacamentos"]
        .sum()
    )

    monthly_totals = (
        df[["competencia", "period_start", "period_label", "total_harley"]]
        .drop_duplicates(subset=["competencia"])
        .copy()
    )
    consolidated = (
        monthly_totals.groupby(["period_start", "period_label"], as_index=False)["total_harley"]
        .sum()
        .rename(columns={"total_harley": "emplacamentos"})
    )
    consolidated["serie"] = "Total Harley"

    attributed = (
        by_year.groupby(["period_start", "period_label"], as_index=False)["emplacamentos"]
        .sum()
        .rename(columns={"emplacamentos": "emplacamentos_atribuidos"})
    )
    unattributed = consolidated.merge(
        attributed,
        how="left",
        on=["period_start", "period_label"],
    )
    unattributed["emplacamentos_atribuidos"] = unattributed["emplacamentos_atribuidos"].fillna(0)
    unattributed["emplacamentos"] = (
        unattributed["emplacamentos"] - unattributed["emplacamentos_atribuidos"]
    ).clip(lower=0)
    unattributed["serie"] = "MY nao identificado"
    unattributed = unattributed[["period_start", "period_label", "emplacamentos", "serie"]]

    available_years = (
        by_year[by_year["emplacamentos"] > 0]["ano_fabricacao"]
        .dropna()
        .astype(int)
        .sort_values()
        .unique()
        .tolist()
    )

    return consolidated, by_year, unattributed, available_years


def build_selected_model_years_chart_df(
    by_year_df: pd.DataFrame,
    consolidated_df: pd.DataFrame,
    selected_years: list[int],
) -> pd.DataFrame:
    if not selected_years or consolidated_df.empty:
        return pd.DataFrame(columns=["period_start", "period_label", "ano_fabricacao", "emplacamentos", "serie"])

    periods = consolidated_df[["period_start", "period_label"]].drop_duplicates().copy()
    grid = pd.MultiIndex.from_product(
        [periods["period_start"].tolist(), selected_years],
        names=["period_start", "ano_fabricacao"],
    ).to_frame(index=False)
    grid = grid.merge(periods, how="left", on="period_start")

    selected_df = by_year_df[by_year_df["ano_fabricacao"].isin(selected_years)].copy()
    merged = grid.merge(
        selected_df,
        how="left",
        on=["period_start", "period_label", "ano_fabricacao"],
    )
    merged["emplacamentos"] = merged["emplacamentos"].fillna(0)
    merged["ano_fabricacao"] = merged["ano_fabricacao"].astype(int)
    merged["serie"] = "MY " + merged["ano_fabricacao"].astype(str)
    return merged.sort_values(["period_start", "ano_fabricacao"])


def build_macro_residual_series(
    consolidated_df: pd.DataFrame,
    by_year_df: pd.DataFrame,
    selected_years: list[int],
    unattributed_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    periods = consolidated_df[["period_start", "period_label"]].drop_duplicates().copy()

    attributed_df = (
        by_year_df.groupby(["period_start", "period_label"], as_index=False)["emplacamentos"]
        .sum()
        .rename(columns={"emplacamentos": "valor"})
    )
    attributed_df = periods.merge(attributed_df, how="left", on=["period_start", "period_label"])
    attributed_df["valor"] = attributed_df["valor"].fillna(0)

    selected_df = (
        by_year_df[by_year_df["ano_fabricacao"].isin(selected_years)]
        .groupby(["period_start", "period_label"], as_index=False)["emplacamentos"]
        .sum()
        .rename(columns={"emplacamentos": "valor"})
    )
    selected_df = periods.merge(selected_df, how="left", on=["period_start", "period_label"])
    selected_df["valor"] = selected_df["valor"].fillna(0)

    other_years = periods.copy()
    other_years["emplacamentos"] = (attributed_df["valor"] - selected_df["valor"]).clip(lower=0)
    other_years["serie"] = "Outros MYs"

    unattributed = periods.merge(
        unattributed_df[["period_start", "period_label", "emplacamentos"]],
        how="left",
        on=["period_start", "period_label"],
    )
    unattributed["emplacamentos"] = unattributed["emplacamentos"].fillna(0)
    unattributed["serie"] = "MY nao identificado"

    return other_years, unattributed


def render_registrations_macro_view(
    db_path: str,
    competencia: str,
    *,
    brand_label: str = "Harley",
    accent_color: str = HARLEY_ORANGE,
    key_prefix: str = "macro_registrations",
    registrations_df: pd.DataFrame | None = None,
):
    if registrations_df is None:
        registrations_df = get_registrations_macro_monthly(db_path)
    reference_month = format_reference_month(competencia)

    st.subheader("Ritmo de Emplacamentos por Ano-Modelo")
    st.caption("Como ler: esta visão mostra o ciclo de vida comercial de cada ano-modelo. Você consegue ver quando um MY começa a vender, ganha tração e perde força até a entrada do próximo.")

    control_col1, control_col2, control_col3 = st.columns((1, 1, 2))
    with control_col1:
        aggregation = st.selectbox(
            "Agrupamento",
            options=["Mensal", "Bimestral", "Trimestral", "Semestral"],
            index=0,
            key=f"{key_prefix}_aggregation",
        )
    with control_col2:
        range_label = st.selectbox(
            "Janela",
            options=[
                "3 meses",
                "6 meses",
                "12 meses",
                "24 meses",
                "36 meses",
                "48 meses",
                "All time",
            ],
            index=2,
            key=f"{key_prefix}_range",
        )
    with control_col3:
        st.caption(
            "A curva TOTAL soma somente os MYs selecionados. Assim, registros sem MY e "
            "anos-modelo fora do recorte não criam picos artificiais."
        )

    range_map = {
        "3 meses": 3,
        "6 meses": 6,
        "12 meses": 12,
        "24 meses": 24,
        "36 meses": 36,
        "48 meses": 48,
        "All time": None,
    }
    range_months = range_map[range_label]

    consolidated, by_year, unattributed, available_years = build_registrations_macro_chart_df(
        registrations_df=registrations_df,
        competencia=competencia,
        aggregation=aggregation,
        range_months=range_months,
    )

    year_options = sorted(available_years, reverse=True)
    recent_default = [year for year in year_options if year >= pd.Timestamp(competencia).year - 2]
    default_years = sorted((recent_default[:3] if recent_default else year_options[:3]))
    selected_years = st.multiselect(
        "Anos-modelo no gráfico",
        options=year_options,
        default=default_years,
        format_func=lambda year: f"MY {year}",
        key=f"{key_prefix}_years_{aggregation}_{range_label}",
    )
    support_curves = st.multiselect(
        "Curvas de apoio",
        options=["TOTAL selecionado", f"Total {brand_label} bruto", "Outros MYs", "MY nao identificado"],
        default=["TOTAL selecionado"],
        key=f"{key_prefix}_support_curves_v2_{aggregation}_{range_label}",
    )

    by_year_selected = build_selected_model_years_chart_df(
        by_year_df=by_year,
        consolidated_df=consolidated,
        selected_years=selected_years,
    )
    if not selected_years and not support_curves:
        st.info("Selecione pelo menos um ano-modelo ou uma curva de apoio para montar a visão de emplacamentos.")
        return

    other_years, unattributed_residual = build_macro_residual_series(
        consolidated_df=consolidated,
        by_year_df=by_year,
        selected_years=selected_years,
        unattributed_df=unattributed,
    )

    fig = go.Figure()
    selected_total = (
        by_year_selected.groupby(["period_start", "period_label"], as_index=False)["emplacamentos"]
        .sum()
        .sort_values("period_start")
    )
    if "TOTAL selecionado" in support_curves and not selected_total.empty:
        fig.add_trace(
            go.Scatter(
                x=selected_total["period_start"],
                y=selected_total["emplacamentos"],
                mode="lines+markers",
                name="TOTAL selecionado",
                line={"color": accent_color, "width": 4},
                hovertemplate="%{x|%b/%y}<br>TOTAL selecionado: %{y:.0f}<extra></extra>",
            )
        )

    gross_total_label = f"Total {brand_label} bruto"
    if gross_total_label in support_curves:
        fig.add_trace(
            go.Scatter(
                x=consolidated["period_start"],
                y=consolidated["emplacamentos"],
                mode="lines+markers",
                name=gross_total_label,
                line={"color": "#777777", "width": 2, "dash": "dot"},
                hovertemplate=f"%{{x|%b/%y}}<br>{gross_total_label}: %{{y:.0f}}<extra></extra>",
            )
        )

    for serie_name in sorted(by_year_selected["serie"].unique()):
        serie_df = by_year_selected[by_year_selected["serie"] == serie_name]
        fig.add_trace(
            go.Scatter(
                x=serie_df["period_start"],
                y=serie_df["emplacamentos"],
                mode="lines+markers",
                name=serie_name,
                hovertemplate="%{x|%b/%y}<br>%{fullData.name}: %{y:.0f}<extra></extra>",
            )
        )

    if "Outros MYs" in support_curves and not other_years.empty and other_years["emplacamentos"].sum() > 0:
        fig.add_trace(
            go.Scatter(
                x=other_years["period_start"],
                y=other_years["emplacamentos"],
                mode="lines+markers",
                name="Outros MYs",
                line={"color": "#B0B0B0", "width": 2, "dash": "dash"},
                hovertemplate="%{x|%b/%y}<br>Outros MYs: %{y:.0f}<extra></extra>",
            )
        )

    if "MY nao identificado" in support_curves and not unattributed_residual.empty and unattributed_residual["emplacamentos"].sum() > 0:
        fig.add_trace(
            go.Scatter(
                x=unattributed_residual["period_start"],
                y=unattributed_residual["emplacamentos"],
                mode="lines+markers",
                name="MY nao identificado",
                line={"color": "#8F8F8F", "width": 2, "dash": "dot"},
                hovertemplate="%{x|%b/%y}<br>MY nao identificado: %{y:.0f}<extra></extra>",
            )
        )

    fig.update_layout(
        title=f"Ritmo de Emplacamentos | {aggregation} | até {reference_month}",
        xaxis_title="Período",
        yaxis_title="Unidades",
        legend_title_text="Curvas",
        hovermode="x unified",
    )
    fig.update_xaxes(tickformat="%b/%y")
    st.plotly_chart(fig, use_container_width=True)


def render_sem_info_view(db_path: str, competencia: str):
    commercial_years = get_commercial_years(db_path, competencia)
    if not commercial_years:
        st.info("Não há anos comerciais válidos para o mês de referência selecionado.")
        return

    default_year = pd.Timestamp(competencia).year
    ano_comercial = st.selectbox(
        "Ano comercial das unidades pré-alocadas",
        options=commercial_years,
        index=commercial_years.index(default_year) if default_year in commercial_years else len(commercial_years) - 1,
        key="stock_view_commercial_year_selector",
    )
    reference_month = format_reference_month(competencia)
    snapshot_df = get_commercial_year_stock_snapshot(
        db_path, ano_comercial, competencia, INVENTORY_QUERY_VERSION
    )
    model_series_df = enrich_models(
        get_commercial_year_stock_series(
            db_path, ano_comercial, competencia, INVENTORY_QUERY_VERSION
        )
    )
    top_models_df = enrich_models(
        get_commercial_year_stock_top_models(
            db_path, ano_comercial, competencia, INVENTORY_QUERY_VERSION
        )
    )

    st.subheader(f"Unidades Pré-Alocadas | {ano_comercial}")
    st.caption(
        "O que este painel comunica: potencial estoque de motocicletas em prateleira, "
        "ainda pendentes de emplacamento. Não sabemos se essas unidades estão na fábrica, "
        "em trânsito ou em uma concessionária; para simplificar a análise, tratamos todo "
        "esse volume como INVENTORY."
    )
    st.caption(f"O mês de referência continua definindo até onde a base pode ir; o gráfico abaixo plota apenas o calendário de {ano_comercial}.")

    if snapshot_df.empty or model_series_df.empty:
        st.info("Sem unidades pré-alocadas no ano comercial selecionado.")
        return

    row = snapshot_df.iloc[0]
    latest_month = format_reference_month(str(row["competencia"]))
    c1, c2, c3 = st.columns(3)
    c1.metric("Unidades Pré-Alocadas", f"{int(row['total_estoque']):,}".replace(",", "."))
    c2.metric("Modelos em pré-alocação", int(row["modelos"]))
    c3.metric("Delta vs mês anterior", f"{int(row['delta_estoque']):+,}".replace(",", "."), delta=latest_month)

    consolidated_df = (
        model_series_df.groupby("competencia", as_index=False)["total_estoque"]
        .sum()
        .rename(columns={"total_estoque": "valor"})
    )
    consolidated_df["serie"] = "Consolidado"

    plot_consolidated = st.checkbox(
        "Plotar curva consolidada",
        value=True,
        key=f"stock_view_consolidated_toggle_{ano_comercial}_{competencia}",
    )

    model_options = top_models_df["codigo_modelo"].tolist()
    default_models = model_options[: min(8, len(model_options))]
    selected_models = st.multiselect(
        "Modelos plotados",
        options=model_options,
        default=default_models,
        format_func=lambda code: top_models_df.loc[top_models_df["codigo_modelo"] == code, "nome_exibicao"].iloc[0],
        key=f"stock_view_model_toggle_{ano_comercial}_{competencia}",
    )

    chart_frames = []
    if plot_consolidated:
        chart_frames.append(consolidated_df)
    if selected_models:
        selected_df = (
            model_series_df[model_series_df["codigo_modelo"].isin(selected_models)][
                ["competencia", "nome_exibicao", "total_estoque"]
            ]
            .rename(columns={"nome_exibicao": "serie", "total_estoque": "valor"})
        )
        chart_frames.append(selected_df)

    if not chart_frames:
        st.info("Ative a curva consolidada ou selecione pelo menos um modelo para plotar.")
        return

    chart_df = pd.concat(chart_frames, ignore_index=True)
    chart_df["competencia"] = pd.to_datetime(chart_df["competencia"])

    fig_detail = px.line(
        chart_df,
        x="competencia",
        y="valor",
        color="serie",
        markers=True,
        title=f"Unidades Pré-Alocadas | Ano comercial {ano_comercial}",
    )
    fig_detail.update_layout(
        xaxis_title="Mês",
        yaxis_title="Unidades",
        legend_title_text="Série",
        hovermode="x unified",
    )
    fig_detail.update_xaxes(tickformat="%b/%y")
    st.plotly_chart(fig_detail, use_container_width=True)

    st.subheader("O que saiu x o que ficou")
    tracking_models_df = get_inventory_tracking_models(
        db_path, competencia, INVENTORY_QUERY_VERSION
    )
    comparison_options = tracking_models_df["codigo_modelo"].tolist()
    comparison_default = "H-D/FLSTFI"
    comparison_model = st.selectbox(
        "Modelo para comparar",
        options=comparison_options,
        index=(
            comparison_options.index(comparison_default)
            if comparison_default in comparison_options
            else 0
        ),
        format_func=lambda code: tracking_models_df.loc[
            tracking_models_df["codigo_modelo"] == code, "nome_exibicao"
        ].iloc[0],
        key=f"inventory_comparison_model_v3_{competencia}",
    )
    comparison_df = get_inventory_vs_territorialized_series(
        db_path,
        comparison_model,
        competencia,
        INVENTORY_QUERY_VERSION,
    ).copy()

    if not comparison_df.empty:
        comparison_df["competencia"] = pd.to_datetime(comparison_df["competencia"])
        comparison_name = tracking_models_df.loc[
            tracking_models_df["codigo_modelo"] == comparison_model, "nome_exibicao"
        ].iloc[0]
        comparison_fig = go.Figure()
        comparison_fig.add_trace(
            go.Bar(
                x=comparison_df["competencia"],
                y=comparison_df["novas_territorializacoes"],
                name="Novas territorializações",
                marker_color="#A7A7A7",
                opacity=0.55,
                hovertemplate="%{x|%b/%y}<br>Novas territorializações: %{y:.0f}<extra></extra>",
            )
        )
        comparison_fig.add_trace(
            go.Scatter(
                x=comparison_df["competencia"],
                y=comparison_df["inventory"],
                mode="lines+markers",
                name="INVENTORY no fechamento",
                line={"color": HARLEY_ORANGE, "width": 3},
                marker={"size": 7},
                hovertemplate="%{x|%b/%y}<br>INVENTORY: %{y:.0f}<extra></extra>",
            )
        )
        comparison_fig.update_layout(
            title=f"{comparison_name} | Tracking de 24 meses",
            xaxis_title="Mês",
            yaxis_title="Unidades",
            hovermode="x unified",
            barmode="overlay",
            legend_title_text="Leitura",
        )
        comparison_fig.update_xaxes(tickformat="%b/%y")
        st.plotly_chart(comparison_fig, use_container_width=True)

        latest_comparison = comparison_df.iloc[-1]
        left, right = st.columns(2)
        left.metric(
            "Territorializadas no mês (proxy de saída)",
            f"{int(latest_comparison['novas_territorializacoes']):,}".replace(",", "."),
        )
        right.metric(
            "INVENTORY no fechamento",
            f"{int(latest_comparison['inventory']):,}".replace(",", "."),
        )
        st.caption(
            "A territorialização é uma aproximação de saída de INVENTORY. "
            "Sem identificação por chassi, não é possível comprovar a conversão individual das unidades."
        )

    col1, col2 = st.columns((1, 1))
    with col1:
        st.subheader("Modelos pré-alocados no último mês")
        st.caption(f"Última foto disponível dentro de {ano_comercial}: {latest_month}")
        st.dataframe(
            top_models_df[["codigo_modelo", "nome_amigavel", "total_estoque"]],
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "codigo_modelo": "Código",
                "nome_amigavel": "Nome amigável",
                "total_estoque": "Unidades",
            },
        )
    with col2:
        fig_top = px.bar(
            top_models_df.head(12),
            x="nome_exibicao",
            y="total_estoque",
            title=f"Top modelos pré-alocados | {latest_month}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig_top.update_layout(xaxis_title="Modelo", yaxis_title="Unidades")
        st.plotly_chart(fig_top, use_container_width=True)


def render_sem_info_page(default_db_path: str):
    render_header("Unidades Pré-Alocadas")
    filters = render_sidebar(default_db_path)

    st.caption(
        "Uma leitura de potencial INVENTORY: motocicletas possivelmente em estoque, "
        "ainda pendentes de emplacamento e sem destino territorial identificado."
    )
    render_sem_info_view(filters.db_path, filters.competencia)


def build_line_chart_df(matrix_df, top_n: int = 8, selected_series: list[str] | None = None):
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

    name_col = "nome_exibicao" if "nome_exibicao" in matrix_df.columns else "marca_modelo"
    value_frame = matrix_df[[name_col, *available_months]].copy()
    if selected_series is None:
        score = value_frame[available_months].fillna(0)
        top_models = (
            score.sum(axis=1)
            .sort_values(ascending=False)
            .head(top_n)
            .index
        )
    else:
        top_models = value_frame[value_frame[name_col].isin(selected_series)].index

    chart_df = value_frame.loc[top_models].melt(
        id_vars=name_col,
        value_vars=available_months,
        var_name="mes",
        value_name="valor",
    )
    chart_df = chart_df.dropna(subset=["valor"])
    chart_df = chart_df.rename(columns={name_col: "serie"})
    chart_df["mes"] = pd.Categorical(chart_df["mes"], categories=available_months, ordered=True)
    chart_df["mes_label"] = chart_df["mes"].map(month_labels)
    return chart_df.sort_values(["mes", "valor"], ascending=[True, False])


def render_matrix_line_chart(matrix_df, title: str, y_axis_title: str, key: str):
    name_col = "nome_exibicao" if "nome_exibicao" in matrix_df.columns else "marca_modelo"
    all_series = matrix_df[name_col].tolist()
    default_series = all_series[:8]
    aggregate_all = st.checkbox(
        "Curva consolidada: todos os modelos",
        value=False,
        key=f"{key}_aggregate_all",
    )

    if aggregate_all:
        chart_df = build_line_chart_df(matrix_df, selected_series=all_series)
        if chart_df.empty:
            return
        chart_df = (
            chart_df.groupby(["mes", "mes_label"], as_index=False)["valor"]
            .sum()
            .assign(serie="Todos os modelos")
        )
    else:
        selected_series = st.multiselect(
            "Modelos no gráfico",
            options=all_series,
            default=default_series,
            key=f"{key}_series_toggle",
        )
        if not selected_series:
            st.info("Selecione pelo menos um modelo para ver o gráfico.")
            return
        chart_df = build_line_chart_df(matrix_df, selected_series=selected_series)
        if chart_df.empty:
            return

    fig = px.line(
        chart_df,
        x="mes_label",
        y="valor",
        color="serie",
        markers=True,
        title=title,
    )
    fig.update_layout(
        xaxis_title="Mês",
        yaxis_title=y_axis_title,
        legend_title_text="Modelo",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_territory_growth_view(db_path: str, competencia: str, selected_years: list[int], year_label: str):
    uf_df = get_model_year_territory_snapshot(db_path, tuple(selected_years), competencia, "uf")
    city_df = get_model_year_territory_snapshot(db_path, tuple(selected_years), competencia, "municipio")
    reference_month = format_reference_month(competencia)

    st.caption(
        "Como ler: esta visão mostra onde o recorte ganhou mais tração no mês e onde já existe mais massa crítica. "
        "O `ganho mensal` é o crescimento positivo versus o mês anterior dentro do recorte selecionado."
    )

    if uf_df.empty and city_df.empty:
        st.info("Sem dados territoriais para o recorte selecionado.")
        return

    top_uf = uf_df.head(12).copy()
    top_city = city_df.head(15).copy()

    k1, k2, k3 = st.columns(3)
    if not top_uf.empty:
        uf_row = top_uf.iloc[0]
        k1.metric(
            "UF com maior ganho",
            str(uf_row["uf"]).title(),
            delta=f"+{int(uf_row['ganho_mensal']):,} no mês".replace(",", "."),
        )
    else:
        k1.metric("UF com maior ganho", "n/d")

    if not top_city.empty:
        city_row = top_city.iloc[0]
        k2.metric(
            "Cidade com maior ganho",
            f"{str(city_row['municipio']).title()} / {str(city_row['uf']).title()}",
            delta=f"+{int(city_row['ganho_mensal']):,} no mês".replace(",", "."),
        )
    else:
        k2.metric("Cidade com maior ganho", "n/d")

    current_total = int(uf_df["total_atual"].sum()) if not uf_df.empty else 0
    k3.metric("Frota do recorte", f"{current_total:,}".replace(",", "."), delta=reference_month)

    col1, col2 = st.columns((1, 1))
    with col1:
        st.dataframe(
            top_uf[["uf", "ganho_mensal", "total_atual", "delta_liquido"]],
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "uf": "UF",
                "ganho_mensal": "Ganho mensal",
                "total_atual": "Frota atual",
                "delta_liquido": "Delta líquido",
            },
        )
    with col2:
        fig_uf = px.bar(
            top_uf.sort_values("ganho_mensal", ascending=True),
            x="ganho_mensal",
            y="uf",
            orientation="h",
            title=f"Territórios com maior ganho | UF | {year_label}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig_uf.update_layout(xaxis_title="Ganho mensal", yaxis_title="UF")
        st.plotly_chart(fig_uf, use_container_width=True)

    non_empty_city = top_city[top_city["municipio"].notna()].copy()
    if not non_empty_city.empty:
        non_empty_city["territorio"] = (
            non_empty_city["municipio"].astype(str).str.title()
            + " / "
            + non_empty_city["uf"].astype(str).str.title()
        )
        col3, col4 = st.columns((1, 1))
        with col3:
            st.dataframe(
                non_empty_city[["territorio", "ganho_mensal", "total_atual", "delta_liquido"]],
                use_container_width=True,
                hide_index=True,
                height=480,
                column_config={
                    "territorio": "Cidade",
                    "ganho_mensal": "Ganho mensal",
                    "total_atual": "Frota atual",
                    "delta_liquido": "Delta líquido",
                },
            )
        with col4:
            fig_city = px.scatter(
                non_empty_city,
                x="total_atual",
                y="ganho_mensal",
                size="total_atual",
                hover_name="territorio",
                title=f"Massa crítica vs ganho mensal | Cidade | {year_label}",
                color_discrete_sequence=[HARLEY_ORANGE],
            )
            fig_city.update_layout(xaxis_title="Frota atual", yaxis_title="Ganho mensal")
            st.plotly_chart(fig_city, use_container_width=True)


def render_search_explorer_view(db_path: str, competencia: str):
    st.subheader("Busca livre")
    st.caption("Como ler: digite uma string para explorar famílias, códigos e variações de modelo. Depois refine por ano-modelo, UF e município, e escolha como quer quebrar a série histórica.")

    search_term = st.text_input(
        "Buscar por string",
        value="",
        placeholder="Ex.: 883, FLHX, Road Glide, Pan America",
        key="free_search_term",
    ).strip()
    if len(search_term) < 2:
        st.info("Digite pelo menos 2 caracteres para buscar na base.")
        return

    raw_df = enrich_models(get_search_model_instances(db_path, f"%{search_term}%"))
    if raw_df.empty:
        st.info("Nenhuma instância encontrada para essa busca.")
        return

    raw_df["competencia"] = pd.to_datetime(raw_df["competencia"])
    raw_df = raw_df[raw_df["competencia"] <= pd.Timestamp(competencia)].copy()
    if raw_df.empty:
        st.info("Nenhum resultado encontrado até o mês de referência selecionado.")
        return

    my_options = sorted(
        [int(value) for value in raw_df["ano_fabricacao"].dropna().unique().tolist() if int(value) <= pd.Timestamp(competencia).year]
    )
    uf_options = sorted(raw_df["uf"].dropna().astype(str).unique().tolist())
    city_options = sorted(raw_df["municipio"].dropna().astype(str).unique().tolist())

    f1, f2, f3 = st.columns((1, 1, 1))
    with f1:
        selected_years = st.multiselect(
            "Filtrar por MY",
            options=my_options,
            default=[],
            format_func=lambda year: f"MY {year}",
            key="free_search_my_filter",
        )
    with f2:
        selected_ufs = st.multiselect(
            "Filtrar por UF",
            options=uf_options,
            default=[],
            key="free_search_uf_filter",
        )
    with f3:
        selected_cities = st.multiselect(
            "Filtrar por município",
            options=city_options,
            default=[],
            key="free_search_city_filter",
        )

    filtered_df = raw_df.copy()
    if selected_years:
        filtered_df = filtered_df[filtered_df["ano_fabricacao"].isin(selected_years)]
    if selected_ufs:
        filtered_df = filtered_df[filtered_df["uf"].isin(selected_ufs)]
    if selected_cities:
        filtered_df = filtered_df[filtered_df["municipio"].isin(selected_cities)]

    if filtered_df.empty:
        st.info("Os filtros zeraram o recorte. Ajuste os toggles para continuar.")
        return

    snapshot_df = (
        filtered_df[filtered_df["competencia"] == pd.Timestamp(competencia)]
        .groupby(["codigo_modelo", "nome_amigavel", "nome_exibicao", "ano_fabricacao"], as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["qtd_veiculos", "codigo_modelo"], ascending=[False, True])
    )

    st.dataframe(
        snapshot_df[["codigo_modelo", "nome_amigavel", "ano_fabricacao", "qtd_veiculos"]],
        use_container_width=True,
        hide_index=True,
        height=340,
        column_config={
            "codigo_modelo": "Codigo",
            "nome_amigavel": "Nome amigavel",
            "ano_fabricacao": "MY",
            "qtd_veiculos": "Unidades",
        },
    )

    detail_candidates = snapshot_df.copy()
    if not detail_candidates.empty:
        detail_candidates["detail_label"] = detail_candidates.apply(
            lambda row: (
                f"{row['nome_exibicao']} | MY {int(row['ano_fabricacao'])}"
                if pd.notna(row["ano_fabricacao"])
                else f"{row['nome_exibicao']} | MY -"
            ),
            axis=1,
        )
        selected_detail_label = st.selectbox(
            "Abrir detalhe do modelo",
            options=detail_candidates["detail_label"].tolist(),
            key="free_search_detail_selector",
        )
        selected_detail_row = detail_candidates.loc[
            detail_candidates["detail_label"] == selected_detail_label
        ].iloc[0]
        if st.button("Ir para detalhe do modelo", key="free_search_detail_button"):
            set_model_detail_context(
                modelo=selected_detail_row["codigo_modelo"],
                db_path=db_path,
                competencia=competencia,
                ano_fabricacao=(
                    int(selected_detail_row["ano_fabricacao"])
                    if pd.notna(selected_detail_row["ano_fabricacao"])
                    else None
                ),
            )
            st.switch_page("pages/modelo_detalhe.py")

    segment = st.selectbox(
        "Segmentar série por",
        options=["Consolidado", "Modelo", "Ano-modelo", "UF", "Município"],
        index=0,
        key="free_search_segment",
    )

    if segment == "Consolidado":
        chart_df = (
            filtered_df.groupby("competencia", as_index=False)["qtd_veiculos"]
            .sum()
            .rename(columns={"qtd_veiculos": "valor"})
        )
        chart_df["serie"] = f"Busca: {search_term}"
    else:
        segment_map = {
            "Modelo": "nome_exibicao",
            "Ano-modelo": "ano_fabricacao",
            "UF": "uf",
            "Município": "municipio",
        }
        col = segment_map[segment]
        chart_df = (
            filtered_df.groupby(["competencia", col], as_index=False)["qtd_veiculos"]
            .sum()
            .rename(columns={"qtd_veiculos": "valor", col: "serie"})
        )
        chart_df["serie"] = chart_df["serie"].astype(str)

    chart_df["competencia_label"] = chart_df["competencia"].dt.strftime("%b/%y")
    fig = px.line(
        chart_df,
        x="competencia_label",
        y="valor",
        color="serie",
        markers=True,
        title=f"Busca livre | {search_term}",
    )
    fig.update_layout(
        xaxis_title="Mês",
        yaxis_title="Unidades",
        legend_title_text="Série",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_models_by_year(db_path: str, competencia: str):
    years = get_valid_years_for_reference(db_path, competencia)
    if not years:
        st.info("Não há anos-modelo válidos para o mês de referência selecionado.")
        return
    selected_years = st.multiselect(
        "Anos-modelo da matriz",
        options=years,
        default=[years[-1]],
        key="models_by_year_selector",
    )
    if not selected_years:
        st.info("Selecione pelo menos um ano-modelo para montar a matriz.")
        return

    selected_years = sorted(selected_years)
    year_label = format_year_selection_label(selected_years)
    reference_month = format_reference_month(competencia)
    commercial_years = get_commercial_years(db_path, competencia)
    default_commercial_year = pd.Timestamp(competencia).year
    if default_commercial_year not in commercial_years:
        default_commercial_year = commercial_years[-1]
    ano_comercial = st.selectbox(
        "Ano comercial da matriz",
        options=commercial_years,
        index=commercial_years.index(default_commercial_year),
        key="models_commercial_year_selector",
    )
    matrix_df = enrich_models(
        get_model_year_monthly_matrix_by_commercial_year(
            db_path,
            tuple(selected_years),
            competencia,
            ano_comercial,
        )
    )
    registrations_df = enrich_models(
        get_model_year_registrations_matrix_by_commercial_year(
            db_path,
            tuple(selected_years),
            competencia,
            ano_comercial,
        )
    )

    st.subheader(f"Modelos | {year_label}")
    st.caption(f"Mês de referência: {reference_month}")
    st.caption(f"Ano comercial exibido: {ano_comercial}")
    st.caption("Como ler: aqui o foco sai do macro e entra no mix de produto. O mês de referência define a foto disponível da base; o ano comercial define qual calendário mensal a matriz plota.")

    tab_frota, tab_emplacamentos, tab_territorio = st.tabs(
        ["Frota (estoque)", "Emplacamentos (delta mensal)", "Território"]
    )

    with tab_frota:
        st.caption(
            "Como ler: cada linha é um modelo. As colunas mostram a evolução do estoque ao longo do ano. "
            "Aqui janeiro representa a foto do mês, não o delta contra dezembro."
        )
        if len(selected_years) == 1:
            render_matrix_detail_selector(
                matrix_df,
                db_path=db_path,
                competencia=competencia,
                ano_fabricacao=selected_years[0],
                key="fleet_matrix",
            )
        else:
            st.caption("Detalhe do modelo desabilitado na visão consolidada de múltiplos anos-modelo.")
            display_df = matrix_df.drop(columns=[column for column in ["marca_modelo", "nome_exibicao"] if column in matrix_df.columns])
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=560)
        render_matrix_line_chart(
            matrix_df,
            title=f"Evolução da frota | {year_label}",
            y_axis_title="Frota",
            key="fleet_matrix_chart",
        )

    with tab_emplacamentos:
        st.caption(
            "Como ler: aqui cada célula representa entrada do mês, não estoque. "
            "Janeiro é calculado contra dezembro do ano anterior, e não contra zero."
        )
        if len(selected_years) == 1:
            render_matrix_detail_selector(
                registrations_df,
                db_path=db_path,
                competencia=competencia,
                ano_fabricacao=selected_years[0],
                key="registrations_matrix",
            )
        else:
            st.caption("Detalhe do modelo desabilitado na visão consolidada de múltiplos anos-modelo.")
            display_df = registrations_df.drop(columns=[column for column in ["marca_modelo", "nome_exibicao"] if column in registrations_df.columns])
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=560)
        render_matrix_line_chart(
            registrations_df,
            title=f"Emplacamentos mensais | {year_label}",
            y_axis_title="Emplacamentos",
            key="registrations_matrix_chart",
        )

    with tab_territorio:
        render_territory_growth_view(
            db_path=db_path,
            competencia=competencia,
            selected_years=selected_years,
            year_label=year_label,
        )


def render_dashboard(default_db_path: str):
    render_header()

    filters = render_sidebar(default_db_path)

    render_kpis(filters.db_path, filters.competencia)
    st.divider()
    render_search_explorer_view(filters.db_path, filters.competencia)
    st.divider()
    registrations_col, divider_col, fleet_distribution_col = st.columns(
        (1, 0.025, 1),
        gap="medium",
    )
    with registrations_col:
        render_registrations_macro_view(filters.db_path, filters.competencia)
    with divider_col:
        st.markdown(
            '<div style="border-left: 1px solid rgba(128, 128, 128, 0.35); '
            'height: 980px; margin: 0 auto;"></div>',
            unsafe_allow_html=True,
        )
    with fleet_distribution_col:
        render_share_by_uf(filters.db_path, filters.competencia)
    st.divider()
    render_top_models_national(filters.db_path, filters.competencia)
    st.divider()
    render_models_by_year(filters.db_path, filters.competencia)
