from __future__ import annotations

import streamlit as st

from app.model_detail import render_model_detail_page

st.set_page_config(page_title="Detalhe do Modelo", layout="wide")
render_model_detail_page()
