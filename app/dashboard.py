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
from app.model_detail import render_matrix_detail_selector

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


def format_reference_month(value: str | pd.Timestamp) -> str:
    ts = pd.Timestamp(value)
    return f"{MONTH_LABELS_PT[int(ts.month)]}/{str(ts.year)[-2:]}"


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

    col1, col2 = st.columns((1, 1))
    with col1:
        st.subheader("Frota por UF")
        st.caption(f"Mês de referência: {reference_month}")
        st.caption("Como ler: use esta visão para localizar concentração geográfica. Os primeiros estados são onde a frota está mais forte hoje.")
        st.dataframe(uf_df, use_container_width=True, hide_index=True)
    with col2:
        fig_uf = px.bar(
            uf_df,
            x="uf",
            y="total_hd_uf",
            title=f"Frota por UF | {reference_month}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        st.plotly_chart(fig_uf, use_container_width=True)


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


def render_registrations_macro_view(db_path: str, competencia: str):
    registrations_df = get_registrations_macro_monthly(db_path)
    reference_month = format_reference_month(competencia)

    st.subheader("Vendas macro")
    st.caption("Como ler: esta visão mostra o ciclo de vida comercial de cada ano-modelo. Você consegue ver quando um MY começa a vender, ganha tração e perde força até a entrada do próximo.")

    control_col1, control_col2, control_col3 = st.columns((1, 1, 2))
    with control_col1:
        aggregation = st.selectbox(
            "Agrupamento",
            options=["Mensal", "Trimestral", "Semestral"],
            index=0,
            key="macro_registrations_aggregation",
        )
    with control_col2:
        range_label = st.selectbox(
            "Janela",
            options=["3 meses", "6 meses", "12 meses", "24 meses", "All time"],
            index=2,
            key="macro_registrations_range",
        )
    with control_col3:
        st.caption("A curva consolidada permanece como referência. O gráfico sempre fecha a conta com `Outros MYs` e `MY nao identificado` quando houver diferença para os anos-modelo escolhidos.")

    range_map = {
        "3 meses": 3,
        "6 meses": 6,
        "12 meses": 12,
        "24 meses": 24,
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
        key=f"macro_registrations_years_{aggregation}_{range_label}",
    )
    support_curves = st.multiselect(
        "Curvas de apoio",
        options=["Total Harley", "Outros MYs", "MY nao identificado"],
        default=["Total Harley", "Outros MYs", "MY nao identificado"],
        key=f"macro_registrations_support_curves_{aggregation}_{range_label}",
    )

    by_year_selected = build_selected_model_years_chart_df(
        by_year_df=by_year,
        consolidated_df=consolidated,
        selected_years=selected_years,
    )
    if not selected_years and not support_curves:
        st.info("Selecione pelo menos um ano-modelo ou uma curva de apoio para montar a visão de vendas.")
        return

    other_years, unattributed_residual = build_macro_residual_series(
        consolidated_df=consolidated,
        by_year_df=by_year,
        selected_years=selected_years,
        unattributed_df=unattributed,
    )

    fig = go.Figure()
    if "Total Harley" in support_curves:
        fig.add_trace(
            go.Scatter(
                x=consolidated["period_start"],
                y=consolidated["emplacamentos"],
                mode="lines+markers",
                name="Total Harley",
                line={"color": HARLEY_ORANGE, "width": 4},
                hovertemplate="%{x|%b/%y}<br>Total Harley: %{y:.0f}<extra></extra>",
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
        title=f"Vendas Harley | {aggregation} | até {reference_month}",
        xaxis_title="Período",
        yaxis_title="Unidades",
        legend_title_text="Curvas",
        hovermode="x unified",
    )
    fig.update_xaxes(tickformat="%b/%y")
    st.plotly_chart(fig, use_container_width=True)


def render_sem_info_view(db_path: str, competencia: str):
    years = get_years(db_path)
    ano_fabricacao = st.selectbox(
        "Ano-modelo do dealer inventory",
        options=years,
        index=len(years) - 1,
        key="sem_info_my_selector",
    )
    ano_competencia = int(competencia[:4])
    reference_month = format_reference_month(competencia)
    snapshot_df = get_sem_info_my_snapshot(db_path, competencia, ano_fabricacao)
    series_df = get_sem_info_my_monthly_series(db_path, ano_fabricacao)
    top_models_df = enrich_models(get_sem_info_my_top_models(db_path, competencia, ano_fabricacao))
    model_series_df = enrich_models(get_sem_info_my_model_series(db_path, ano_fabricacao))

    st.subheader(f"Estoque pendente de emplacamento | MY {ano_fabricacao}")
    st.caption("Proxy: registros com `SEM INFORMAÇÃO` dentro da janela MY-1 até MY.")
    st.caption("Como ler: pense aqui como uma leitura de `dealer inventory`. Esse estoque pode estar na fábrica e/ou nas concessionárias, já cadastrado no sistema VIN, mas ainda aguardando emplacamento.")

    if ano_competencia not in {ano_fabricacao - 1, ano_fabricacao}:
        st.info(f"O mês de referência {reference_month} está fora da janela operacional deste proxy para o MY {ano_fabricacao}. Use meses de {ano_fabricacao - 1} ou {ano_fabricacao}.")
        return

    if snapshot_df.empty:
        st.info("Sem registros `SEM INFORMAÇÃO` associados ao MY selecionado no mês escolhido.")
        return

    row = snapshot_df.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Unidades sem informação", f"{int(row['total_sem_info']):,}".replace(",", "."))
    c2.metric("Modelos afetados", int(row["modelos"]))
    c3.metric("Delta vs mês anterior", f"{int(row['delta_sem_info']):+,}".replace(",", "."))

    col1, col2 = st.columns((1, 1))
    with col1:
        st.subheader("Top modelos")
        st.caption(f"Mês de referência: {reference_month}")
        st.caption("Como ler: a tabela mostra quais modelos mais puxam esse estoque pendente no mês selecionado.")
        st.dataframe(
            top_models_df[["codigo_modelo", "nome_amigavel", "total_sem_info"]],
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "codigo_modelo": "Codigo",
                "nome_amigavel": "Nome amigavel",
                "total_sem_info": "Unidades",
            },
        )
    with col2:
        fig_top = px.bar(
            top_models_df.head(12),
            x="nome_exibicao",
            y="total_sem_info",
            title=f"Top modelos | MY {ano_fabricacao} | {reference_month}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        st.plotly_chart(fig_top, use_container_width=True)

    if not top_models_df.empty and not model_series_df.empty:
        model_options = top_models_df["codigo_modelo"].tolist()
        default_models = model_options[:8]
        aggregate_all_models = st.checkbox(
            "Curva consolidada: todos os modelos",
            value=False,
            key=f"sem_info_select_all_{ano_fabricacao}_{competencia}",
        )

        if aggregate_all_models:
            detail_df = (
                model_series_df.groupby("competencia", as_index=False)["total_sem_info"]
                .sum()
                .rename(columns={"total_sem_info": "valor"})
            )
            detail_df["competencia_label"] = detail_df["competencia"].astype(str)
            fig_detail = px.line(
                detail_df,
                x="competencia_label",
                y="valor",
                markers=True,
                title=f"Evolução por modelo | MY {ano_fabricacao}",
            )
            fig_detail.update_traces(name="Todos os modelos", showlegend=True)
            fig_detail.update_layout(legend_title_text="Modelo")
        else:
            selected_models = st.multiselect(
                "Modelos no gráfico",
                options=model_options,
                default=default_models,
                format_func=lambda code: top_models_df.loc[top_models_df["codigo_modelo"] == code, "nome_exibicao"].iloc[0],
                key=f"sem_info_model_toggle_{ano_fabricacao}_{competencia}",
            )
            if not selected_models:
                st.info("Selecione pelo menos um modelo para ver a evolução por modelo.")
                return

            detail_df = model_series_df[model_series_df["codigo_modelo"].isin(selected_models)].copy()
            detail_df["competencia_label"] = detail_df["competencia"].astype(str)
            fig_detail = px.line(
                detail_df,
                x="competencia_label",
                y="total_sem_info",
                color="nome_exibicao",
                markers=True,
                title=f"Evolução por modelo | MY {ano_fabricacao}",
            )
        fig_detail.update_layout(
            xaxis_title="Mês",
            yaxis_title="Unidades",
            legend_title_text="Modelo",
        )
        st.plotly_chart(fig_detail, use_container_width=True)


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


def render_models_by_year(db_path: str, competencia: str):
    years = get_years(db_path)
    ano_fabricacao = st.selectbox(
        "Ano-modelo da matriz",
        options=years,
        index=len(years) - 1,
        key="models_by_year_selector",
    )
    matrix_df = enrich_models(get_model_year_monthly_matrix(db_path, ano_fabricacao, competencia))
    registrations_df = enrich_models(get_model_year_registrations_matrix(db_path, ano_fabricacao, competencia))
    reference_month = format_reference_month(competencia)

    st.subheader(f"Modelos | MY {ano_fabricacao}")
    st.caption(f"Mês de referência: {reference_month}")
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
            key="fleet_matrix_chart",
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
            key="registrations_matrix_chart",
        )


def render_dashboard(default_db_path: str):
    st.title("Harley Analytics")
    st.caption("Visão macro da frota Harley-Davidson")

    filters = render_sidebar(default_db_path)

    render_kpis(filters.db_path, filters.competencia)
    st.divider()
    render_registrations_macro_view(filters.db_path, filters.competencia)
    st.divider()
    render_share_by_uf(filters.db_path, filters.competencia)
    st.divider()
    render_top_models_national(filters.db_path, filters.competencia)
    st.divider()
    render_sem_info_view(filters.db_path, filters.competencia)
    st.divider()
    render_models_by_year(filters.db_path, filters.competencia)
