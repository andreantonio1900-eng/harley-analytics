from __future__ import annotations

from pathlib import Path
import unicodedata

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDIAN_DB_PATH = PROJECT_ROOT / "data" / "frota_indian_2026_04.duckdb"
INDIAN_RED = "#7B1113"
INDIAN_GOLD = "#B08D57"


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.strip().upper().split())


def classify_indian_family(model: str) -> str:
    text = normalize_text(model)
    if "SCOUT" in text:
        return "Scout"
    if "SPRINGFIELD" in text:
        return "Springfield"
    if "ROADMASTER" in text:
        return "Roadmaster"
    if "CHIEFTAIN" in text:
        return "Chieftain"
    if "CHIEF" in text or "DARKHORSE" in text or "DARK HORSE" in text or "VINTAGE" in text or "CLASSIC" in text:
        return "Chief"
    if "FTR" in text:
        return "FTR"
    if text == "IMP/INDIAN" or text.startswith("I/INDIAN CHIEF"):
        return "Heritage / Classic"
    return "Outras"


def pretty_name(model: str) -> str:
    text = normalize_text(model)
    replacements = {
        "INDIAN/SCOUT": "Scout",
        "I/INDIAN SCOUT": "Scout",
        "I/INDIAN SCOUT BOBBER": "Scout Bobber",
        "INDIAN/CHIEF VINTAGE": "Chief Vintage",
        "I/INDIAN CHIEF VINTAGE": "Chief Vintage",
        "INDIAN/CHIEF CLASSIC": "Chief Classic",
        "INDIAN/CHIEF SPRINGFIELD": "Chief Springfield",
        "I/INDIAN CHIEF SPRINGFLD": "Chief Springfield",
        "INDIAN/CHIEF ROADMASTER": "Chief Roadmaster",
        "I/INDIAN CHIEF ROADMASTR": "Chief Roadmaster",
        "INDIAN/CHIEF CHIEFTAIN": "Chief Chieftain",
        "I/INDIAN CHIEF CHIEFTAIN": "Chief Chieftain",
        "I/INDIAN CHIEF CHIEFT DH": "Chief Chieftain Dark Horse",
        "I/INDIAN CHIEF DARKHORSE": "Chief Dark Horse",
        "I/INDIAN CHIEF": "Chief",
        "IMP/INDIAN": "Indian (Heritage Import)",
        "I/INDIAN BOARD TRACK RAC": "Board Track Racer",
        "I/INDIAN VINTAGE LE": "Vintage LE",
    }
    return replacements.get(text, model)


@st.cache_resource
def get_connection(db_path: str):
    return duckdb.connect(db_path, read_only=True)


@st.cache_data
def load_snapshot(db_path: str) -> pd.DataFrame:
    con = get_connection(db_path)
    df = con.execute("SELECT * FROM frota_indian").df()
    df["competencia"] = pd.to_datetime(df["competencia"])
    df["friendly_name"] = df["marca_modelo"].map(pretty_name)
    df["family"] = df["marca_modelo"].map(classify_indian_family)
    return df


def render_sidebar(default_db_path: str) -> str:
    with st.sidebar:
        st.header("Indian | Abr/26")
        db_path = st.text_input("Banco DuckDB", value=default_db_path)
        if not Path(db_path).expanduser().exists():
            st.error(f"Banco não encontrado: {db_path}")
            st.stop()
        st.caption("Snapshot dedicado da frota Indian no Brasil referente a abril de 2026.")
    return db_path


def render_kpis(df: pd.DataFrame):
    total = int(df["qtd_veiculos"].sum())
    top_model = (
        df.groupby(["marca_modelo", "friendly_name"], as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values("qtd_veiculos", ascending=False)
        .iloc[0]
    )
    top_year = (
        df.groupby("ano_fabricacao", dropna=False, as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values("qtd_veiculos", ascending=False)
        .iloc[0]
    )
    pending = int(
        df[
            df["ano_fabricacao"].isna()
            & df["municipio"].astype(str).map(normalize_text).eq("SEM INFORMACAO")
        ]["qtd_veiculos"].sum()
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Frota Indian", f"{total:,}".replace(",", "."))
    c2.metric("Modelos distintos", int(df["marca_modelo"].nunique()))
    c3.metric(
        "Modelo líder",
        str(top_model["friendly_name"]),
        delta=f"{int(top_model['qtd_veiculos']):,} motos".replace(",", "."),
    )
    year_label = "Sem MY" if pd.isna(top_year["ano_fabricacao"]) else f"MY {int(top_year['ano_fabricacao'])}"
    c4.metric(
        "MY líder",
        year_label,
        delta=f"{int(top_year['qtd_veiculos']):,} motos".replace(",", "."),
    )
    st.caption(
        f"Leitura rápida: a base tem {total:,} motos Indian em abril/26. "
        f"O bucket de `Sem Informação` + `MY nulo` soma {pending:,} unidades.".replace(",", ".")
    )


def render_models(df: pd.DataFrame):
    models = (
        df.groupby(["marca_modelo", "friendly_name"], as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["qtd_veiculos", "friendly_name"], ascending=[False, True])
    )
    st.subheader("Modelos mais prevalentes")
    col1, col2 = st.columns((1, 1))
    with col1:
        st.dataframe(
            models.rename(
                columns={
                    "marca_modelo": "Código",
                    "friendly_name": "Nome amigável",
                    "qtd_veiculos": "Frota",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=520,
        )
    with col2:
        fig = px.bar(
            models.head(12).sort_values("qtd_veiculos", ascending=True),
            x="qtd_veiculos",
            y="friendly_name",
            orientation="h",
            title="Top modelos Indian | abr/26",
            color_discrete_sequence=[INDIAN_RED],
        )
        fig.update_layout(xaxis_title="Frota", yaxis_title="Modelo")
        st.plotly_chart(fig, use_container_width=True)


def render_family_mix(df: pd.DataFrame):
    family_df = (
        df.groupby("family", as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values("qtd_veiculos", ascending=False)
    )
    family_df["share_pct"] = 100.0 * family_df["qtd_veiculos"] / family_df["qtd_veiculos"].sum()
    st.subheader("Composição por família")
    col1, col2 = st.columns((1, 1))
    with col1:
        fig = px.pie(
            family_df,
            names="family",
            values="qtd_veiculos",
            hole=0.55,
            title="Mix da frota Indian por família",
            color_discrete_sequence=[INDIAN_RED, INDIAN_GOLD, "#4E5D6C", "#8C5E58", "#AA7B4C", "#6A7F52"],
        )
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(
            family_df.rename(
                columns={
                    "family": "Família",
                    "qtd_veiculos": "Frota",
                    "share_pct": "Share %",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_geography(df: pd.DataFrame):
    uf_df = (
        df.groupby("uf", as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["qtd_veiculos", "uf"], ascending=[False, True])
    )
    city_df = (
        df.groupby(["municipio", "uf"], as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["qtd_veiculos", "municipio"], ascending=[False, True])
    )
    st.subheader("Geografia da frota")
    col1, col2 = st.columns((1, 1))
    with col1:
        fig_uf = px.bar(
            uf_df.head(12),
            x="uf",
            y="qtd_veiculos",
            title="Top UFs | abr/26",
            color_discrete_sequence=[INDIAN_RED],
        )
        fig_uf.update_layout(xaxis_title="UF", yaxis_title="Frota")
        st.plotly_chart(fig_uf, use_container_width=True)
    with col2:
        fig_city = px.bar(
            city_df.head(15).sort_values("qtd_veiculos", ascending=True),
            x="qtd_veiculos",
            y="municipio",
            orientation="h",
            title="Top cidades | abr/26",
            color_discrete_sequence=[INDIAN_RED],
        )
        fig_city.update_layout(xaxis_title="Frota", yaxis_title="Cidade")
        st.plotly_chart(fig_city, use_container_width=True)


def render_city_drilldown(df: pd.DataFrame):
    st.subheader("Municípios | Drilldown por modelo")
    st.caption(
        "Como ler: filtre por modelo para refinar o recorte. A tabela mostra os municípios; "
        "ao selecionar uma linha, o painel abaixo abre o mix de modelos daquele território."
    )

    model_options = (
        df[["marca_modelo", "friendly_name"]]
        .drop_duplicates()
        .sort_values(["friendly_name", "marca_modelo"])
        .reset_index(drop=True)
    )
    option_labels = {
        row["marca_modelo"]: f"{row['friendly_name']} | {row['marca_modelo']}"
        for _, row in model_options.iterrows()
    }
    default_models = model_options["marca_modelo"].head(8).tolist()
    selected_models = st.multiselect(
        "Filtrar por modelo",
        options=model_options["marca_modelo"].tolist(),
        default=default_models,
        format_func=lambda code: option_labels.get(code, code),
        key="indian_city_drilldown_models",
    )

    filtered_df = df[df["marca_modelo"].isin(selected_models)].copy() if selected_models else df.copy()
    city_df = (
        filtered_df.groupby(["uf", "municipio"], as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["qtd_veiculos", "municipio", "uf"], ascending=[False, True, True])
    )
    city_df["territorio"] = city_df["municipio"].astype(str) + " / " + city_df["uf"].astype(str)

    event = st.dataframe(
        city_df[["territorio", "qtd_veiculos"]],
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "territorio": "Município",
            "qtd_veiculos": "Frota",
        },
        key="indian_city_drilldown_table",
        on_select="rerun",
        selection_mode="single-row",
    )

    selection = event.selection.rows if event and event.selection else []
    if not selection:
        st.caption("Selecione um município para abrir o drilldown de modelos.")
        return

    selected_row = city_df.iloc[selection[0]]
    city_models = (
        filtered_df[
            (filtered_df["uf"] == selected_row["uf"])
            & (filtered_df["municipio"] == selected_row["municipio"])
        ]
        .groupby(["marca_modelo", "friendly_name", "family", "ano_fabricacao"], dropna=False, as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["qtd_veiculos", "friendly_name"], ascending=[False, True])
    )
    city_models["ano_fabricacao"] = city_models["ano_fabricacao"].map(
        lambda value: "Sem MY" if pd.isna(value) else int(value)
    )
    city_models["ano_fabricacao"] = city_models["ano_fabricacao"].astype(str)

    col1, col2 = st.columns((1, 1))
    with col1:
        st.markdown(f"**Drilldown | {selected_row['municipio'].title()} / {selected_row['uf'].title()}**")
        st.dataframe(
            city_models.rename(
                columns={
                    "friendly_name": "Modelo",
                    "marca_modelo": "Código",
                    "family": "Família",
                    "ano_fabricacao": "Ano-modelo",
                    "qtd_veiculos": "Frota",
                }
            ),
            use_container_width=True,
            hide_index=True,
            height=420,
        )
    with col2:
        chart_df = (
            city_models.groupby("friendly_name", as_index=False)["qtd_veiculos"]
            .sum()
            .sort_values("qtd_veiculos", ascending=True)
            .tail(12)
        )
        fig = px.bar(
            chart_df,
            x="qtd_veiculos",
            y="friendly_name",
            orientation="h",
            title=f"Top modelos | {selected_row['municipio'].title()} / {selected_row['uf'].title()}",
            color_discrete_sequence=[INDIAN_RED],
        )
        fig.update_layout(xaxis_title="Frota", yaxis_title="Modelo")
        st.plotly_chart(fig, use_container_width=True)


def render_years_and_pending(df: pd.DataFrame):
    year_df = (
        df.groupby("ano_fabricacao", dropna=False, as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values("qtd_veiculos", ascending=False)
    )
    pending_df = (
        df[
            df["ano_fabricacao"].isna()
            & df["municipio"].astype(str).map(normalize_text).eq("SEM INFORMACAO")
        ]
        .groupby(["marca_modelo", "friendly_name"], as_index=False)["qtd_veiculos"]
        .sum()
        .sort_values(["qtd_veiculos", "friendly_name"], ascending=[False, True])
    )

    st.subheader("Anos-modelo e pendências")
    col1, col2 = st.columns((1, 1))
    with col1:
        st.dataframe(
            year_df.assign(
                ano_fabricacao=year_df["ano_fabricacao"].map(
                    lambda x: "Sem MY" if pd.isna(x) else int(x)
                )
            ).rename(columns={"ano_fabricacao": "Ano-modelo", "qtd_veiculos": "Frota"}),
            use_container_width=True,
            hide_index=True,
            height=420,
        )
    with col2:
        if pending_df.empty:
            st.info("Nenhuma Indian no bucket de pendência (`Sem Informação` + `MY nulo`) em abr/26.")
        else:
            st.dataframe(
                pending_df.rename(
                    columns={
                        "marca_modelo": "Código",
                        "friendly_name": "Nome amigável",
                        "qtd_veiculos": "Pendente",
                    }
                ),
                use_container_width=True,
                hide_index=True,
                height=420,
            )


def render_indian_dashboard(default_db_path: str = str(INDIAN_DB_PATH)):
    db_path = render_sidebar(default_db_path)
    df = load_snapshot(db_path)

    st.title("Indian Motorcycle | Brasil | Abr/26")
    st.caption("Snapshot dedicado da frota Indian no Brasil, extraído do arquivo nacional de abril de 2026.")

    render_kpis(df)
    st.divider()
    render_models(df)
    st.divider()
    render_family_mix(df)
    st.divider()
    render_geography(df)
    st.divider()
    render_city_drilldown(df)
    st.divider()
    render_years_and_pending(df)
