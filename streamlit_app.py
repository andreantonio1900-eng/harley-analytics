from __future__ import annotations
import streamlit as st

from app.db import DEFAULT_DB
from app.dashboard import render_dashboard

st.set_page_config(page_title="Harley Analytics", layout="wide")
render_dashboard(str(DEFAULT_DB))
