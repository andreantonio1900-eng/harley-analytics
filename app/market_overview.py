from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from app import queries
from app.db import connect
from app.glossary import enrich_models

HARLEY_ORANGE = "#FF6A13"
HARLEY_GRAY = "#6F7785"
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


@st.cache_resource
def get_connection(db_path: str):
    return connect(db_path, read_only=True)


@st.cache_data
def get_competencias(db_path: str) -> list[str]:
    con = get_connection(db_path)
    df = queries.list_competencias(con)
    return [str(value) for value in df["competencia"].tolist()]


@st.cache_data
def get_annual_sales_totals(db_path: str):
    con = get_connection(db_path)
    return queries.annual_sales_totals(con)


@st.cache_data
def get_model_year_snapshot_distribution(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.model_year_snapshot_distribution(con, competencia=competencia)


@st.cache_data
def get_model_base_builder_ranking(db_path: str):
    con = get_connection(db_path)
    return enrich_models(queries.model_base_builder_ranking(con))


@st.cache_data
def get_current_model_snapshot(db_path: str, competencia: str):
    con = get_connection(db_path)
    return enrich_models(queries.current_model_snapshot(con, competencia=competencia))


@st.cache_data
def get_share_by_uf(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.share_by_uf(con, competencia=competencia)


@st.cache_data
def get_city_concentration_snapshot(db_path: str, competencia: str):
    con = get_connection(db_path)
    return queries.city_concentration_snapshot(con, competencia=competencia, limit=30)


def format_reference_month(value: str | pd.Timestamp) -> str:
    ts = pd.Timestamp(value)
    return f"{MONTH_LABELS_PT[int(ts.month)]}/{str(ts.year)[-2:]}"


def normalize_label(value: str) -> str:
    return (
        str(value)
        .strip()
        .upper()
        .replace("Á", "A")
        .replace("À", "A")
        .replace("Ã", "A")
        .replace("Â", "A")
        .replace("É", "E")
        .replace("Ê", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ô", "O")
        .replace("Õ", "O")
        .replace("Ú", "U")
        .replace("Ç", "C")
    )


def is_independent_import(code: str) -> bool:
    code_upper = str(code).strip().upper()
    return code_upper.startswith("I/") or code_upper.startswith("IMP/")


def is_cvo(code: str, friendly_name: str) -> bool:
    code_upper = str(code).strip().upper().replace(" ", "")
    friendly_upper = str(friendly_name).strip().upper()
    return "CVO" in friendly_upper or code_upper.endswith("SE")


def classify_family(code: str, friendly_name: str) -> str:
    code_upper = str(code).strip().upper().replace(" ", "")
    friendly_upper = str(friendly_name).strip().upper()
    text = f"{code_upper} {friendly_upper}"

    if "PAN AMERICA" in text or "RA1250" in code_upper:
        return "Adventure"
    if any(token in text for token in ["SPORTSTER", "IRON 883", "IRON 1200", "FORTY-EIGHT", "ROADSTER", "NIGHTSTER", "SPORTSTER S"]):
        return "Sportster"
    if any(token in code_upper for token in ["XL", "RH975", "RH1250", "XR1200"]):
        return "Sportster"
    if any(token in text for token in ["ROAD GLIDE", "STREET GLIDE", "ROAD KING", "ULTRA", "ELECTRA GLIDE", "TRI GLIDE", "FREEWHEELER", "LIMITED"]):
        return "Touring"
    if any(token in code_upper for token in ["FLHX", "FLHT", "FLHR", "FLTR", "FLHXS", "FLHXU", "FLTRX", "FLHTK", "FLHTCU", "FLHTCUTG", "FLTRXL", "FLHXL"]):
        return "Touring"
    if any(token in text for token in ["FAT BOY", "BREAKOUT", "HERITAGE", "STREET BOB", "LOW RIDER", "SOFTAIL", "SLIM", "DELUXE", "SPRINGER", "ROCKER", "CROSS BONES"]):
        return "Softail"
    if any(token in code_upper for token in ["FLST", "FLFB", "FLHC", "FLHCS", "FXBB", "FXBR", "FXBRS", "FXLRS", "FXLRST", "FXSB", "FXST"]):
        return "Softail"
    if any(token in text for token in ["DYNA", "SWITCHBACK", "WIDE GLIDE", "SUPER GLIDE"]):
        return "Dyna"
    if any(token in code_upper for token in ["FXD", "FXDC", "FXDF", "FLD"]):
        return "Dyna"
    if any(token in text for token in ["V-ROD", "NIGHT ROD", "MUSCLE"]):
        return "V-Rod"
    if "VRSC" in code_upper:
        return "V-Rod"
    if "XG" in code_upper or "STREET 750" in text or "STREET 500" in text:
        return "Street"
    if "TRIKE" in text or "TRI GLIDE" in text or "FREEWHEELER" in text:
        return "Trike"
    return "Outras familias"


def prepare_snapshot(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    df = snapshot_df.copy()
    df["codigo_modelo"] = df["codigo_modelo"].fillna(df["marca_modelo"])
    df["nome_amigavel"] = df["nome_amigavel"].fillna("")
    df["family"] = df.apply(
        lambda row: classify_family(row["codigo_modelo"], row["nome_amigavel"]),
        axis=1,
    )
    df["is_import_indep"] = df["codigo_modelo"].apply(is_independent_import)
    df["is_cvo"] = df.apply(
        lambda row: is_cvo(row["codigo_modelo"], row["nome_amigavel"]),
        axis=1,
    )
    return df


def render_sidebar(default_db_path: str) -> tuple[str, str]:
    with st.sidebar:
        st.header("Mercado Brasileiro")
        db_path = st.text_input("Banco DuckDB", value=default_db_path, key="market_overview_db_path")
        if not Path(db_path).expanduser().exists():
            st.error(f"Banco não encontrado: {db_path}")
            st.stop()

        competencias = get_competencias(db_path)
        if not competencias:
            st.error("Nenhum mês de referência encontrado no banco.")
            st.stop()

        competencia = st.selectbox(
            "Mês de referência",
            options=competencias,
            index=len(competencias) - 1,
            format_func=format_reference_month,
            key="market_overview_competencia",
        )
        st.caption("Esta página responde perguntas estratégicas de mercado. Alguns blocos usam a foto do mês; outros olham toda a janela histórica da base.")

    return db_path, competencia


def render_gold_year(db_path: str, competencia: str, reference_month: str):
    model_year_df = get_model_year_snapshot_distribution(db_path, competencia).copy()
    model_year_df["ano_fabricacao"] = model_year_df["ano_fabricacao"].astype(int)
    model_year_df["total"] = model_year_df["total"].astype(float)
    gold_row = model_year_df.iloc[0]
    total_fleet = float(model_year_df["total"].sum())
    share_pct = 100.0 * float(gold_row["total"]) / total_fleet if total_fleet else 0

    st.subheader("Qual foi o verdadeiro ano de ouro da Harley-Davidson no Brasil?")
    st.caption(f"Como ler: aqui o critério mudou. Em vez de vendas históricas, olhamos para o ano-modelo mais prevalente na foto atual da frota em {reference_month}. Em outras palavras: qual MY mais representa o parque circulante Harley no Brasil hoje.")

    c1, c2 = st.columns((1, 1))
    c1.metric(
        "Ano-modelo de ouro",
        f"MY {int(gold_row['ano_fabricacao'])}",
        delta=f"{int(gold_row['total']):,} motos".replace(",", "."),
    )
    c2.metric(
        "Leitura executiva",
        "Maior presença no parque atual",
        delta=f"{share_pct:.1f}% da frota com MY conhecido",
    )

    col1, col2 = st.columns((1, 1))
    with col1:
        fig = px.bar(
            model_year_df.head(20).sort_values("total", ascending=True),
            x="total",
            y="ano_fabricacao",
            orientation="h",
            text="total",
            title=f"Top anos-modelo na frota | {reference_month}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        fig.update_layout(xaxis_title="Frota", yaxis_title="Ano-modelo")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(
            model_year_df.rename(
                columns={
                    "ano_fabricacao": "Ano-modelo",
                    "total": "Frota",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_base_builder(db_path: str):
    base_df = get_model_base_builder_ranking(db_path).copy()
    base_df["vendas_proxy_total"] = base_df["vendas_proxy_total"].astype(float)
    leader = base_df.iloc[0]

    st.subheader("Qual modelo realmente construiu a base da Harley-Davidson no Brasil?")
    st.caption("Como ler: este ranking soma as entradas líquidas por modelo ao longo de toda a base. Em termos práticos, ele mostra quem mais colocou novas motos no parque circulante dentro da janela observada.")

    c1, c2 = st.columns((1, 1))
    c1.metric(
        "Modelo que mais construiu base",
        leader["nome_exibicao"],
        delta=f"{int(leader['vendas_proxy_total']):,} entradas liquidas".replace(",", "."),
    )
    c2.metric(
        "Escopo da leitura",
        "Jan/24 a mar/26",
        delta="janela historica observada",
    )

    top_df = base_df.head(15).copy()
    col1, col2 = st.columns((1, 1))
    with col1:
        st.dataframe(
            top_df[["codigo_modelo", "nome_amigavel", "vendas_proxy_total"]],
            use_container_width=True,
            hide_index=True,
            height=520,
            column_config={
                "codigo_modelo": "Codigo",
                "nome_amigavel": "Nome amigavel",
                "vendas_proxy_total": "Entradas liquidas",
            },
        )
    with col2:
        fig = px.bar(
            top_df.sort_values("vendas_proxy_total", ascending=True),
            x="vendas_proxy_total",
            y="nome_exibicao",
            orientation="h",
            title="Top modelos que mais ampliaram a base",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig.update_layout(xaxis_title="Entradas liquidas", yaxis_title="Modelo")
        st.plotly_chart(fig, use_container_width=True)


def render_family_mix(snapshot_df: pd.DataFrame, reference_month: str):
    family_df = (
        snapshot_df.groupby("family", as_index=False)["total"]
        .sum()
        .sort_values("total", ascending=False)
    )
    family_df["share_pct"] = 100.0 * family_df["total"] / family_df["total"].sum()
    core = family_df[family_df["family"].isin(["Touring", "Softail", "Sportster"])].copy()
    if core.empty:
        leader_label = "Sem leitura"
    else:
        leader_row = core.sort_values("total", ascending=False).iloc[0]
        leader_label = leader_row["family"]

    st.subheader("O Brasil e um pais de Harley Touring, Softail ou Sportster?")
    st.caption(f"Como ler: esta resposta usa a foto da frota em {reference_month}. O recorte por familia revela o perfil real de consumo da base circulante, e nao apenas o hype do momento.")

    c1, c2 = st.columns((1, 1))
    if core.empty:
        c1.metric("Familia lider", "n/d")
    else:
        c1.metric(
            "Familia lider",
            leader_label,
            delta=f"{leader_row['share_pct']:.1f}% da frota",
        )
    c2.metric(
        "Leitura executiva",
        "Mix da frota atual",
        delta=f"{int(family_df['total'].sum()):,} motos".replace(",", "."),
    )

    col1, col2 = st.columns((1, 1))
    with col1:
        fig = px.pie(
            family_df,
            names="family",
            values="total",
            hole=0.55,
            title=f"Composicao da frota por familia | {reference_month}",
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(
            family_df.rename(
                columns={
                    "family": "Familia",
                    "total": "Frota",
                    "share_pct": "Share %",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_geography(snapshot_df: pd.DataFrame, uf_df: pd.DataFrame, city_df: pd.DataFrame, reference_month: str):
    city_clean = city_df[
        city_df["municipio"].apply(normalize_label) != "SEM INFORMACAO"
    ].copy()
    uf_leader = uf_df.iloc[0]
    city_leader = city_clean.iloc[0]
    concentration_df = city_clean[city_clean["total"] >= 100].copy()
    concentration_df = concentration_df.sort_values(["share_uf_pct", "total"], ascending=[False, False]).head(15)

    st.subheader("Onde mora a Harley-Davidson no Brasil de verdade?")
    st.caption(f"Como ler: aqui combinamos massa critica e concentracao. O ranking absoluto mostra onde a Harley realmente mora; a concentracao proporcional mostra cidades que dominam a frota do proprio estado.")

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "UF lider",
        str(uf_leader["uf"]).title(),
        delta=f"{uf_leader['share_percentual']:.1f}% da frota nacional",
    )
    c2.metric(
        "Cidade lider",
        f"{str(city_leader['municipio']).title()} / {str(city_leader['uf']).title()}",
        delta=f"{int(city_leader['total']):,} motos".replace(",", "."),
    )
    if concentration_df.empty:
        c3.metric("Maior concentracao", "n/d")
    else:
        concentration_row = concentration_df.iloc[0]
        c3.metric(
            "Maior concentracao",
            f"{str(concentration_row['municipio']).title()} / {str(concentration_row['uf']).title()}",
            delta=f"{concentration_row['share_uf_pct']:.1f}% da frota da UF",
        )

    col1, col2 = st.columns((1, 1))
    with col1:
        fig_uf = px.bar(
            uf_df.head(12),
            x="uf",
            y="total_hd_uf",
            title=f"Top UFs | {reference_month}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig_uf.update_layout(xaxis_title="UF", yaxis_title="Frota")
        st.plotly_chart(fig_uf, use_container_width=True)
    with col2:
        fig_city = px.bar(
            city_clean.head(15).sort_values("total", ascending=True),
            x="total",
            y="municipio",
            orientation="h",
            title=f"Top cidades | {reference_month}",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig_city.update_layout(xaxis_title="Frota", yaxis_title="Cidade")
        st.plotly_chart(fig_city, use_container_width=True)

    col3, col4 = st.columns((1, 1))
    with col3:
        st.dataframe(
            city_clean.head(15).rename(
                columns={
                    "municipio": "Cidade",
                    "uf": "UF",
                    "total": "Frota",
                    "share_brasil_pct": "Share Brasil %",
                }
            )[["Cidade", "UF", "Frota", "share_brasil_pct"]],
            use_container_width=True,
            hide_index=True,
            height=420,
        )
    with col4:
        st.dataframe(
            concentration_df.rename(
                columns={
                    "municipio": "Cidade",
                    "uf": "UF",
                    "total": "Frota",
                    "share_uf_pct": "Share da UF %",
                }
            )[["Cidade", "UF", "Frota", "share_uf_pct"]],
            use_container_width=True,
            hide_index=True,
            height=420,
        )


def render_premium_pyramid(snapshot_df: pd.DataFrame, reference_month: str):
    cvo_df = snapshot_df[snapshot_df["is_cvo"]].copy()
    import_df = snapshot_df[snapshot_df["is_import_indep"]].copy()
    total_fleet = float(snapshot_df["total"].sum())
    cvo_total = float(cvo_df["total"].sum())
    import_total = float(import_df["total"].sum())

    pyramid_df = pd.DataFrame(
        {
            "categoria": ["CVOs", "Importacao independente"],
            "total": [cvo_total, import_total],
            "share_pct": [
                100.0 * cvo_total / total_fleet if total_fleet else 0,
                100.0 * import_total / total_fleet if total_fleet else 0,
            ],
        }
    )

    st.subheader("Qual e o peso real das CVOs e importacoes independentes na frota brasileira?")
    st.caption(f"Como ler: aqui olhamos para o topo da piramide em {reference_month}. CVOs capturam exclusividade de produto; prefixos `I/` e `IMP/` aproximam o mercado de importacao independente na base brasileira.")

    c1, c2 = st.columns((1, 1))
    c1.metric(
        "Peso das CVOs",
        f"{int(cvo_total):,} motos".replace(",", "."),
        delta=f"{(100.0 * cvo_total / total_fleet):.2f}% da frota" if total_fleet else None,
    )
    c2.metric(
        "Peso da importacao independente",
        f"{int(import_total):,} motos".replace(",", "."),
        delta=f"{(100.0 * import_total / total_fleet):.2f}% da frota" if total_fleet else None,
    )

    col1, col2 = st.columns((1, 1))
    with col1:
        fig = px.bar(
            pyramid_df,
            x="categoria",
            y="total",
            text="share_pct",
            title=f"Peso no parque circulante | {reference_month}",
            color="categoria",
            color_discrete_map={
                "CVOs": HARLEY_ORANGE,
                "Importacao independente": HARLEY_GRAY,
            },
        )
        fig.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Frota")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(
            pyramid_df.rename(
                columns={
                    "categoria": "Categoria",
                    "total": "Frota",
                    "share_pct": "Share %",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    col3, col4 = st.columns((1, 1))
    with col3:
        st.dataframe(
            cvo_df.sort_values("total", ascending=False).head(12)[["codigo_modelo", "nome_amigavel", "total"]],
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "codigo_modelo": "Codigo",
                "nome_amigavel": "Nome amigavel",
                "total": "Frota",
            },
        )
    with col4:
        st.dataframe(
            import_df.sort_values("total", ascending=False).head(12)[["codigo_modelo", "nome_amigavel", "total"]],
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "codigo_modelo": "Codigo",
                "nome_amigavel": "Nome amigavel",
                "total": "Frota",
            },
        )


def render_market_overview_page(default_db_path: str):
    db_path, competencia = render_sidebar(default_db_path)
    reference_month = format_reference_month(competencia)

    st.title("Mercado Harley no Brasil")
    st.caption("Uma leitura executiva da base para responder perguntas estratégicas sobre crescimento, composição da frota, geografia e o topo da pirâmide da marca.")

    snapshot_df = prepare_snapshot(get_current_model_snapshot(db_path, competencia))
    uf_df = get_share_by_uf(db_path, competencia).copy()
    city_df = get_city_concentration_snapshot(db_path, competencia).copy()

    render_gold_year(db_path, competencia, reference_month)
    st.divider()
    render_base_builder(db_path)
    st.divider()
    render_family_mix(snapshot_df, reference_month)
    st.divider()
    render_geography(snapshot_df, uf_df, city_df, reference_month)
    st.divider()
    render_premium_pyramid(snapshot_df, reference_month)
