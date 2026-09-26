from __future__ import annotations
import streamlit as st

from app.db import DEFAULT_DB
from app.dashboard import render_dashboard

st.set_page_config(page_title="Harley Analytics", layout="wide")


def render_home_hd():
    render_dashboard(str(DEFAULT_DB))


pages = [
    st.Page(render_home_hd, title="Home HD", default=True),
    st.Page("pages/mercado_brasil.py", title="HD Mercado Brasil"),
    st.Page("pages/modelo_detalhe.py", title="HD Modelo Detalhe"),
    st.Page("pages/estoque_sem_info.py", title="Unidades Pré-Alocadas"),
    st.Page("pages/backfill_monitor.py", title="Backfill Monitor"),
    st.Page("pages/indian_brasil.py", title="Bônus Indian Brasil"),
    st.Page("pages/roubos_furtos.py", title="Roubos e Furtos SSP"),
]

navigation = st.navigation(pages)
navigation.run()
