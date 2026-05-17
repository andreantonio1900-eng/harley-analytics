from __future__ import annotations

from app.db import DEFAULT_DB
from app.market_overview import render_market_overview_page

render_market_overview_page(str(DEFAULT_DB))
