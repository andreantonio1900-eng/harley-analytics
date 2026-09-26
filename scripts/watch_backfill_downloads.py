from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import time


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "_download_cache" / "shared"
REFRESH_SECONDS = 2
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


def human_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
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


def scan_files() -> list[dict]:
    rows: list[dict] = []
    for path in CACHE_DIR.glob("i_frota_por_uf_municipio_marca_e_modelo_ano_*"):
        competencia = competencia_from_name(path.name)
        if competencia is None or not ("2015-01" <= competencia <= "2018-12"):
            continue
        rows.append(
            {
                "path": path,
                "competencia": competencia,
                "size": path.stat().st_size,
                "complete": not path.name.endswith(".part"),
            }
        )
    return sorted(rows, key=lambda row: row["competencia"])


def main() -> None:
    previous_sizes: dict[Path, int] = {}
    previous_completed: set[Path] = set()
    print("BACKFILL SENATRAN 2015–2018 | LOG AO VIVO", flush=True)
    print("Atualizações aparecem abaixo sem limpar o terminal. Ctrl+C encerra apenas o monitor.", flush=True)
    while True:
        started = time.monotonic()
        rows = scan_files()
        completed = sum(row["complete"] for row in rows)
        partial = len(rows) - completed
        disk = shutil.disk_usage(PROJECT_ROOT)
        active: list[str] = []
        for row in rows:
            path = row["path"]
            old_size = previous_sizes.get(path, row["size"])
            speed = max(row["size"] - old_size, 0) / REFRESH_SECONDS
            if speed > 0:
                active.append(
                    f"{row['competencia']} {human_bytes(row['size'])} @ {human_bytes(speed)}/s"
                )

        completed_paths = {row["path"] for row in rows if row["complete"]}
        newly_completed = completed_paths - previous_completed
        completed_text = ""
        if newly_completed:
            labels = sorted(
                competencia_from_name(path.name) or path.name for path in newly_completed
            )
            completed_text = " | NOVO COMPLETO: " + ", ".join(labels)

        active_text = "; ".join(active) if active else "aguardando/retry"
        print(
            f"[{datetime.now():%H:%M:%S}] completos={completed} parciais={partial} "
            f"livre={human_bytes(disk.free)} | ativos: {active_text}{completed_text}",
            flush=True,
        )

        previous_sizes = {row["path"]: row["size"] for row in rows}
        previous_completed = completed_paths
        elapsed = time.monotonic() - started
        time.sleep(max(REFRESH_SECONDS - elapsed, 0.2))


if __name__ == "__main__":
    main()
