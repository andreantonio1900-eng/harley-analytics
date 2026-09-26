from __future__ import annotations
import streamlit as st

from app.db import DEFAULT_DB
from app.dashboard import render_dashboard

st.set_page_config(page_title="Harley Analytics", layout="wide")


def render_home_hd():
    render_dashboard(str(DEFAULT_DB))


pages = [
    st.Page(render_home_hd, title="Dashboard Harley-Davidson", default=True),
    st.Page("pages/modelo_detalhe.py", title="Análise Detalhada por Modelo"),
    st.Page("pages/mercado_brasil.py", title="Harley-Davidson - Análise Geográfica"),
    st.Page("pages/indian_brasil.py", title="Dashboard Indian Motorcycle"),
    st.Page("pages/estoque_sem_info.py", title="Unidades Pré-Alocadas [Beta]"),
    st.Page("pages/roubos_furtos.py", title="Roubos e Furtos SSP [Beta]"),
]

navigation = st.navigation(pages)
navigation.run()
