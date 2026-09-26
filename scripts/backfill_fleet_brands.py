from __future__ import annotations

from pathlib import Path
import threading
from typing import Optional

import duckdb
import typer

from app.brand_ingestion import (
    determine_missing_resources,
    fetch_ckan_package_metadata,
    get_brand_configs,
    iter_brand_model_resources,
    process_resources_multi_brand_with_prefetch,
    process_resources_with_prefetch,
    resource_label,
    upsert_snapshot_into_master,
)


app = typer.Typer(add_completion=False, help="Backfill mensal das marcas Harley-Davidson e Indian a partir da base SENATRAN.")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def snapshot_total(config, competencia: str) -> int:
    path = Path(str(config.snapshot_db_path).format(competencia=competencia[:7].replace("-", "_")))
    if not path.exists():
        return 0
    try:
        with duckdb.connect(str(path), read_only=True) as con:
            return int(
                con.execute(
                    f"SELECT COALESCE(SUM(qtd_veiculos), 0) FROM {config.table_name}"
                ).fetchone()[0]
            )
    except (duckdb.Error, OSError):
        return 0


class ProgressReporter:
    def __init__(self):
        self._lock = threading.Lock()
        self._last_percent: dict[str, int] = {}

    def __call__(self, label: str, message: str):
        with self._lock:
            if message.startswith("download "):
                percent_text = message.removeprefix("download ").removesuffix("%")
                try:
                    percent = int(percent_text)
                except ValueError:
                    typer.echo(f"[{label}] {message}")
                    return

                last_percent = self._last_percent.get(label, -1)
                if percent <= last_percent:
                    return
                self._last_percent[label] = percent
                typer.echo(f"[{label}] download {percent}%")
                return

            typer.echo(f"[{label}] {message}")


@app.command()
def run(
    brand: str = typer.Option("all", help="harley, indian ou all"),
    start: Optional[str] = typer.Option(None, help="Competência inicial em YYYY-MM-01"),
    end: Optional[str] = typer.Option(None, help="Competência final em YYYY-MM-01"),
    limit: Optional[int] = typer.Option(None, help="Limite de competências a processar nesta rodada"),
    descending: bool = typer.Option(True, help="Processar do mais recente para o mais antigo"),
    dry_run: bool = typer.Option(False, help="Só listar o que seria processado"),
    keep_snapshots: bool = typer.Option(True, help="Manter os DuckDBs mensais por competência"),
    stage_only: bool = typer.Option(False, help="Gerar/validar snapshots sem escrever nos bancos mestres"),
    publish_only: bool = typer.Option(False, help="Publicar snapshots já validados nos bancos mestres"),
    cleanup_archives: bool = typer.Option(False, help="Apagar arquivos brutos após processamento"),
):
    configs = get_brand_configs(PROJECT_ROOT)
    if brand not in {"harley", "indian", "all"}:
        raise typer.BadParameter("`brand` precisa ser harley, indian ou all.")

    selected_brands = list(configs.keys()) if brand == "all" else [brand]
    package_metadata = fetch_ckan_package_metadata()
    progress_reporter = ProgressReporter()

    if stage_only and publish_only:
        raise typer.BadParameter("Use apenas um entre --stage-only e --publish-only.")

    if publish_only:
        resources = [
            resource
            for resource in iter_brand_model_resources(package_metadata)
            if (start is None or resource["competencia"] >= start)
            and (end is None or resource["competencia"] <= end)
        ]
        published = 0
        for resource in sorted(resources, key=lambda item: item["competencia"], reverse=descending):
            competencia = resource["competencia"]
            for brand_name in selected_brands:
                config = configs[brand_name]
                total = snapshot_total(config, competencia)
                if total <= 0:
                    continue
                snapshot_path = Path(
                    str(config.snapshot_db_path).format(
                        competencia=competencia[:7].replace("-", "_")
                    )
                )
                persisted = upsert_snapshot_into_master(config, competencia, snapshot_path)
                typer.echo(f"PUBLISHED {brand_name} | {competencia} | frota={persisted:,}".replace(",", "."))
                published += 1
        typer.echo(f"Publicações concluídas: {published}")
        return

    if brand == "all":
        typer.echo("\n=== ALL BRANDS ===")
        if stage_only:
            resources = [
                resource
                for resource in iter_brand_model_resources(package_metadata)
                if (start is None or resource["competencia"] >= start)
                and (end is None or resource["competencia"] <= end)
                and any(snapshot_total(configs[name], resource["competencia"]) <= 0 for name in selected_brands)
            ]
        else:
            resources_by_brand = {
                brand_name: determine_missing_resources(
                    package_metadata=package_metadata,
                    config=configs[brand_name],
                    start_competencia=start,
                    end_competencia=end,
                )
                for brand_name in selected_brands
            }

            merged_by_competencia: dict[str, dict] = {}
            for brand_resources in resources_by_brand.values():
                for resource in brand_resources:
                    merged_by_competencia.setdefault(resource["competencia"], resource)
            resources = list(merged_by_competencia.values())

        resources = sorted(resources, key=lambda item: item["competencia"], reverse=descending)
        if limit is not None:
            resources = resources[:limit]

        if not resources:
            typer.echo("Nenhuma competência faltante para processar.")
            return

        typer.echo(f"Competências faltantes encontradas: {len(resources)}")
        for resource in resources:
            typer.echo(f"- {resource['competencia']} | {resource['url']}")

        if dry_run:
            return

        for resource in resources:
            typer.echo(f"\nPreparando SOURCE | {resource['competencia']} ...")

        results = process_resources_multi_brand_with_prefetch(
            resources=resources,
            configs=[configs[brand_name] for brand_name in selected_brands],
            keep_snapshot=keep_snapshots,
            upsert_master=not stage_only,
            progress_callback=progress_reporter,
            cleanup_archives=cleanup_archives,
        )

        for result in sorted(results, key=lambda item: (item["competencia"], item["brand"]), reverse=descending):
            typer.echo(
                " | ".join(
                    [
                        f"brand={result['brand']}",
                        f"competência={result['competencia']}",
                        f"linhas_brutas={result['raw_rows']:,}".replace(",", "."),
                        f"linhas_marca={result['brand_rows']:,}".replace(",", "."),
                        f"linhas_snapshot={result['snapshot_rows']:,}".replace(",", "."),
                        f"frota={result['total_units']:,}".replace(",", "."),
                    ]
                )
            )
        return

    for brand_name in selected_brands:
        config = configs[brand_name]
        typer.echo(f"\n=== {brand_name.upper()} ===")
        resources = determine_missing_resources(
            package_metadata=package_metadata,
            config=config,
            start_competencia=start,
            end_competencia=end,
        )
        resources = sorted(resources, key=lambda item: item["competencia"], reverse=descending)
        if limit is not None:
            resources = resources[:limit]

        if not resources:
            typer.echo("Nenhuma competência faltante para processar.")
            continue

        typer.echo(f"Competências faltantes encontradas: {len(resources)}")
        for resource in resources:
            typer.echo(f"- {resource['competencia']} | {resource['url']}")

        if dry_run:
            continue

        for resource in resources:
            typer.echo(f"\nPreparando {resource_label(config, resource['competencia'])} ...")

        results = process_resources_with_prefetch(
            resources=resources,
            config=config,
            keep_snapshot=keep_snapshots,
            progress_callback=progress_reporter,
            cleanup_archives=cleanup_archives,
        )

        for result in results:
            typer.echo(
                " | ".join(
                    [
                        f"competência={result['competencia']}",
                        f"linhas_brutas={result['raw_rows']:,}".replace(",", "."),
                        f"linhas_marca={result['brand_rows']:,}".replace(",", "."),
                        f"linhas_snapshot={result['snapshot_rows']:,}".replace(",", "."),
                        f"frota={result['total_units']:,}".replace(",", "."),
                    ]
                )
            )


if __name__ == "__main__":
    app()
