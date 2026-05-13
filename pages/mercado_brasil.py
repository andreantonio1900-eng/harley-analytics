from __future__ import annotations

import streamlit as st

from app.db import DEFAULT_DB
from app.market_overview import render_market_overview_page

st.set_page_config(page_title="Mercado Harley no Brasil", layout="wide")
render_market_overview_page(str(DEFAULT_DB))
