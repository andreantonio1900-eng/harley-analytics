from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import time

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "_download_cache" / "shared"
MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}
MISSING_OFFICIAL = {"2015-06", "2015-07", "2017-06"}
EXPECTED = [
    f"{year}-{month:02d}"
    for year in range(2015, 2019)
    for month in range(1, 13)
    if f"{year}-{month:02d}" not in MISSING_OFFICIAL
]


def human_bytes(value: float) -> str:
    size = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024 or unit == "TB":
            return f"{size:,.1f} {unit}".replace(",", ".")
        size /= 1024
    return f"{size:,.1f} TB".replace(",", ".")


def competencia_from_name(name: str) -> str | None:
    normalized = name.lower().replace("ç", "c")
    match = re.search(r"_ano_([a-z]+)_(20\d{2})", normalized)
    if not match:
        return None
    month_name, year = match.groups()
    month = MONTHS.get(month_name)
    return f"{year}-{month:02d}" if month else None


def cache_snapshot() -> dict[str, dict]:
    snapshot: dict[str, dict] = {}
    for path in CACHE_DIR.glob("i_frota_por_uf_municipio_marca_e_modelo_ano_*"):
        competencia = competencia_from_name(path.name)
        if competencia not in EXPECTED:
            continue
        size = path.stat().st_size
        current = snapshot.get(competencia)
        is_complete = not path.name.endswith(".part")
        if current is None or is_complete or size > current["size"]:
            snapshot[competencia] = {
                "path": path,
                "size": size,
                "complete": is_complete,
            }
    return snapshot


st.title("Backfill Monitor")
st.caption(
    "Downloads SENATRAN de 2015 a 2018 para Harley-Davidson e Indian. "
    "Atualização automática a cada 2 segundos."
)


@st.fragment(run_every=2)
def render_live_monitor():
    now = time.time()
    snapshot = cache_snapshot()
    previous = st.session_state.get("backfill_monitor_previous", {})
    previous_time = st.session_state.get("backfill_monitor_previous_time", now)
    elapsed = max(now - previous_time, 0.1)

    complete_count = sum(item["complete"] for item in snapshot.values())
    partial_count = sum(not item["complete"] for item in snapshot.values())
    disk = shutil.disk_usage(PROJECT_ROOT)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Arquivos completos", f"{complete_count} / {len(EXPECTED)}")
    c2.metric("Downloads parciais", partial_count)
    c3.metric("Espaço livre", human_bytes(disk.free))
    c4.metric("Última atualização", datetime.now().strftime("%H:%M:%S"))
    st.progress(complete_count / len(EXPECTED))

    rows = []
    for competencia in EXPECTED:
        item = snapshot.get(competencia)
        if item is None:
            rows.append(
                {
                    "Competência": competencia,
                    "Status": "Na fila",
                    "Tamanho": "-",
                    "Velocidade": "-",
                }
            )
            continue

        old_size = previous.get(competencia, item["size"])
        speed = max(item["size"] - old_size, 0) / elapsed
        if item["complete"]:
            status = "Completo"
        elif speed > 0:
            status = "Baixando"
        else:
            status = "Parcial / retry"
        rows.append(
            {
                "Competência": competencia,
                "Status": status,
                "Tamanho": human_bytes(item["size"]),
                "Velocidade": f"{human_bytes(speed)}/s" if speed > 0 else "-",
            }
        )

    status_df = pd.DataFrame(rows)
    active_df = status_df[status_df["Status"].isin(["Baixando", "Parcial / retry", "Completo"])]
    st.dataframe(active_df, use_container_width=True, hide_index=True, height=520)
    st.caption(
        "Lacunas oficiais fora da fila: jun/15, jul/15 e jun/17. "
        "Arquivos completos permanecem no cache até o processamento dos snapshots."
    )

    st.session_state["backfill_monitor_previous"] = {
        competencia: item["size"] for competencia, item in snapshot.items()
    }
    st.session_state["backfill_monitor_previous_time"] = now


render_live_monitor()
