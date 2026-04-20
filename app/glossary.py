from __future__ import annotations

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GLOSSARY_PATH = PROJECT_ROOT / "data" / "model_glossary.csv"


def load_model_glossary() -> pd.DataFrame:
    if not GLOSSARY_PATH.exists():
        return pd.DataFrame(columns=["codigo_modelo", "nome_amigavel"])

    glossary_df = pd.read_csv(GLOSSARY_PATH).fillna("")
    expected_cols = ["codigo_modelo", "nome_amigavel"]
    for column in expected_cols:
        if column not in glossary_df.columns:
            glossary_df[column] = ""
    return glossary_df[expected_cols]


def lookup_codes_by_friendly_name(model_name: str) -> list[str]:
    glossary_df = load_model_glossary()
    if glossary_df.empty:
        return []

    normalized = model_name.strip().casefold()
    matches = glossary_df[
        glossary_df["nome_amigavel"].astype(str).str.strip().str.casefold() == normalized
    ]["codigo_modelo"].tolist()
    return sorted({code for code in matches if str(code).strip()})


def enrich_models(df: pd.DataFrame, source_col: str = "marca_modelo") -> pd.DataFrame:
    if source_col not in df.columns:
        return df

    glossary_df = load_model_glossary()
    enriched_df = df.merge(
        glossary_df,
        how="left",
        left_on=source_col,
        right_on="codigo_modelo",
    )
    enriched_df["codigo_modelo"] = enriched_df["codigo_modelo"].fillna(enriched_df[source_col])
    enriched_df["nome_amigavel"] = enriched_df["nome_amigavel"].fillna("")
    enriched_df["nome_exibicao"] = enriched_df.apply(
        lambda row: (
            f"{row['codigo_modelo']} | {row['nome_amigavel']}"
            if str(row["nome_amigavel"]).strip()
            else row["codigo_modelo"]
        ),
        axis=1,
    )
    return enriched_df
