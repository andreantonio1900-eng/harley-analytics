from __future__ import annotations

from app.dashboard import render_sem_info_page
from app.db import DEFAULT_DB

render_sem_info_page(str(DEFAULT_DB))
