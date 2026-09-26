from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import shutil

from app.brand_ingestion import (
    download_resource,
    fetch_ckan_package_metadata,
    iter_brand_model_resources,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "_download_cache" / "shared"
START = "2015-01-01"
END = "2018-12-01"
MAX_WORKERS = 3
MIN_FREE_BYTES = 12 * 1024**3


def destination_for(resource: dict) -> Path:
    return CACHE_DIR / Path(str(resource["url"])).name


def is_complete(resource: dict) -> bool:
    destination = destination_for(resource)
    return destination.exists() and destination.stat().st_size > 0


def download_one(resource: dict) -> tuple[str, str, int]:
    competencia = resource["competencia"]
    destination = destination_for(resource)
    if shutil.disk_usage(PROJECT_ROOT).free < MIN_FREE_BYTES:
        raise RuntimeError("Espaço livre abaixo do limite de 12 GiB.")
    download_resource(resource["url"], destination)
    return competencia, destination.name, destination.stat().st_size


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    metadata = fetch_ckan_package_metadata()
    resources = [
        resource
        for resource in iter_brand_model_resources(metadata)
        if START <= resource["competencia"] <= END
    ]
    pending = [resource for resource in resources if not is_complete(resource)]
    print(
        f"Recursos oficiais={len(resources)} | completos={len(resources) - len(pending)} "
        f"| pendentes={len(pending)} | workers={MAX_WORKERS}",
        flush=True,
    )
    if not pending:
        return

    failures: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for resource in sorted(pending, key=lambda item: item["competencia"]):
            print(f"QUEUE {resource['competencia']}", flush=True)
            futures[executor.submit(download_one, resource)] = resource

        for future in as_completed(futures):
            resource = futures[future]
            try:
                competencia, filename, size = future.result()
                print(f"DONE {competencia} | {size:,} bytes | {filename}", flush=True)
            except Exception as exc:
                failures.append((resource["competencia"], str(exc)))
                print(f"FAIL {resource['competencia']} | {exc}", flush=True)

    print(f"Rodada concluída | falhas={len(failures)}", flush=True)
    for competencia, error in failures:
        print(f"- {competencia}: {error}", flush=True)


if __name__ == "__main__":
    main()
