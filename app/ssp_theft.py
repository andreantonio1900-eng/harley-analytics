from __future__ import annotations

import os
import re
import unicodedata
import urllib.request
from html import unescape
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from app.ssp_storage import DEFAULT_SSP_DB, list_ssp_loaded_snapshots, read_ssp_rows

HARLEY_ORANGE = "#FF6A13"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SSP_CACHE_DIR = PROJECT_ROOT / "data" / "_ssp_cache"
SSP_SOURCE_ENV = "SSP_VEHICLES_XLSX_SOURCE"
SSP_CONSULTAS_URL = "https://www.ssp.sp.gov.br/estatistica/consultas"
SSP_CLASSIC_CONSULTA_URL = "https://www.ssp.sp.gov.br/transparenciassp/Consulta.aspx"
SSP_REQUEST_TIMEOUT = (30, 600)

MONTH_NAMES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Marco",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}
VEHICLE_QUERY_TARGETS = {
    "Furto de veiculo": "ctl00$cphBody$btnFurtoVeiculo",
    "Roubo de veiculo": "ctl00$cphBody$btnRouboVeiculo",
}
MOTORCYCLE_TERMS = (
    "moto",
    "motocicleta",
    "motociclo",
    "motoneta",
    "ciclomotor",
    "triciclo",
    "quadriciclo",
)


def normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def canonicalize_ssp_columns(columns: list[Any]) -> dict[Any, str]:
    renamed: dict[Any, str] = {}
    for column in columns:
        key = normalize_key(column)
        if not key:
            continue
        if "data" in key and any(token in key for token in ("fato", "ocorrencia", "bo", "registro", "emissao")):
            renamed[column] = "data_fato"
        elif key == "data ocorrencia bo":
            renamed[column] = "data_fato"
        elif "natureza" in key or "delito" in key or "tipificacao" in key:
            renamed[column] = "natureza"
        elif key == "rubrica":
            renamed[column] = "natureza"
        elif "municipio" in key or key == "cidade" or "cidade fato" in key:
            renamed[column] = "municipio"
        elif key in {"nome municipio circ", "nome municipio"} and "municipio" not in renamed.values():
            renamed[column] = "municipio"
        elif key == "cidade":
            renamed[column] = "municipio"
        elif key == "uf" or key.endswith(" uf"):
            renamed[column] = "uf"
        elif "bairro" in key:
            renamed[column] = "bairro"
        elif "delegacia" in key:
            renamed[column] = "delegacia"
        elif key in {"nome delegacia circ", "nome delegacia"} and "delegacia" not in renamed.values():
            renamed[column] = "delegacia"
        elif "placa" in key:
            renamed[column] = "placa"
        elif "ano modelo" in key:
            renamed[column] = "ano_modelo"
        elif "ano fabricacao" in key or "ano fabr" in key:
            renamed[column] = "ano_fabricacao"
        elif ("marca" in key and "modelo" in key) or key == "marca modelo":
            renamed[column] = "marca_modelo"
        elif key == "descr marca veiculo":
            renamed[column] = "marca_modelo"
        elif key == "marca":
            renamed[column] = "marca"
        elif key == "modelo":
            renamed[column] = "modelo"
        elif ("tipo" in key and "veiculo" in key) or ("especie" in key and "veiculo" in key) or key in {
            "tipo",
            "especie",
            "categoria veiculo",
        }:
            renamed[column] = "tipo_veiculo"
        elif key == "descr tipo veiculo":
            renamed[column] = "tipo_veiculo"
        elif "cor" in key:
            renamed[column] = "cor"
        elif key == "desc cor veiculo":
            renamed[column] = "cor"
    return renamed


def infer_sheet_score(columns: list[Any]) -> int:
    renamed = canonicalize_ssp_columns(columns)
    score = 0
    for field, weight in {
        "data_fato": 3,
        "natureza": 3,
        "municipio": 2,
        "marca_modelo": 3,
        "marca": 1,
        "modelo": 1,
        "tipo_veiculo": 2,
        "ano_modelo": 1,
    }.items():
        if field in renamed.values():
            score += weight
    return score


def _best_frame_from_tables(tables: list[pd.DataFrame], prefix: str) -> tuple[pd.DataFrame, str, int] | None:
    best_df: pd.DataFrame | None = None
    best_name = ""
    best_score = -1
    for idx, candidate in enumerate(tables, start=1):
        score = infer_sheet_score(candidate.columns.tolist())
        if score > best_score and not candidate.empty:
            best_df = candidate
            best_name = f"{prefix}_{idx}"
            best_score = score
    if best_df is None:
        return None
    return best_df, best_name, 0


def try_load_structured_vehicle_workbook(source: str | bytes | BytesIO) -> tuple[pd.DataFrame, str, int] | None:
    excel_source = BytesIO(source) if isinstance(source, bytes) else source
    excel_file = pd.ExcelFile(excel_source)
    vehicle_sheets = [sheet for sheet in excel_file.sheet_names if normalize_key(sheet).startswith("veiculos")]
    if not vehicle_sheets:
        return None

    selected_sheet = vehicle_sheets[0]
    preferred_columns = [
        "DATA_OCORRENCIA_BO",
        "RUBRICA",
        "DESCR_OCORRENCIA_VEICULO",
        "DESCR_TIPO_VEICULO",
        "DESCR_MARCA_VEICULO",
        "ANO_FABRICACAO",
        "ANO_MODELO",
        "PLACA_VEICULO",
        "DESC_COR_VEICULO",
        "CIDADE",
        "BAIRRO",
        "NOME_DELEGACIA_CIRC",
        "MES_REGISTRO_BO",
        "ANO_REGISTRO_BO",
    ]
    df = pd.read_excel(excel_file, sheet_name=selected_sheet, usecols=preferred_columns)
    return df, selected_sheet, 0


def detect_best_sheet_frame(source: str | bytes | BytesIO) -> tuple[pd.DataFrame, str, int]:
    excel_error: Exception | None = None
    html_error: Exception | None = None

    try:
        structured = try_load_structured_vehicle_workbook(source)
        if structured is not None:
            return structured
    except Exception:
        pass

    try:
        excel_source = BytesIO(source) if isinstance(source, bytes) else source
        excel_file = pd.ExcelFile(excel_source)
        best_df: pd.DataFrame | None = None
        best_sheet = excel_file.sheet_names[0]
        best_header = 0
        best_score = -1

        for sheet_name in excel_file.sheet_names:
            for header_row in range(4):
                try:
                    candidate = pd.read_excel(excel_file, sheet_name=sheet_name, header=header_row)
                except Exception:
                    continue
                score = infer_sheet_score(candidate.columns.tolist())
                if score > best_score and not candidate.empty:
                    best_df = candidate
                    best_sheet = sheet_name
                    best_header = header_row
                    best_score = score

        if best_df is not None:
            return best_df, best_sheet, best_header
    except Exception as exc:
        excel_error = exc

    try:
        if isinstance(source, bytes):
            html_source = StringIO(source.decode("utf-8", errors="ignore"))
        elif isinstance(source, BytesIO):
            html_source = StringIO(source.getvalue().decode("utf-8", errors="ignore"))
        else:
            html_source = source
        tables = pd.read_html(html_source)
        best = _best_frame_from_tables(tables, "html_table")
        if best is not None:
            return best
    except Exception as exc:
        html_error = exc

    raise ValueError(
        "Nao foi possivel identificar uma aba ou tabela valida dentro do arquivo da SSP. "
        f"Excel error: {excel_error}. HTML error: {html_error}."
    )


def extract_hidden_fields(page_html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for field in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        match = re.search(
            rf'name="{re.escape(field)}" id="{re.escape(field)}" value="([^"]*)"',
            page_html,
        )
        values[field] = match.group(1) if match else ""
    return values


def submit_ssp_post(
    session: requests.Session,
    page_html: str,
    event_target: str,
    extra_fields: dict[str, str] | None = None,
    timeout: tuple[int, int] = SSP_REQUEST_TIMEOUT,
) -> requests.Response:
    payload = extract_hidden_fields(page_html)
    payload["__EVENTTARGET"] = event_target
    payload["__EVENTARGUMENT"] = ""
    if extra_fields:
        payload.update(extra_fields)
    return session.post(SSP_CLASSIC_CONSULTA_URL, data=payload, timeout=timeout)


def parse_ssp_department_options(page_html: str) -> list[tuple[str, str]]:
    options = re.findall(r'<option(?: selected="selected")? value="([^"]+)">(.*?)</option>', page_html)
    return [(value, " ".join(unescape(label).split())) for value, label in options if value]


def parse_ssp_year_targets(page_html: str) -> dict[int, str]:
    matches = re.findall(
        r'id="cphBody_lkAno\d+" class="block" href="javascript:__doPostBack\(&#39;([^&#]+)&#39;.*?>(\d{4})</a>',
        page_html,
    )
    return {int(year): target for target, year in matches}


def parse_ssp_month_targets(page_html: str) -> dict[int, str]:
    matches = re.findall(
        r'id="cphBody_lkMes(\d+)" class="block" href="javascript:__doPostBack\(&#39;([^&#]+)&#39;.*?>(.*?)</a>',
        page_html,
    )
    return {int(month): target for month, target, _label in matches}


def fetch_ssp_official_options(occurrence_kind: str) -> dict[str, Any]:
    session = requests.Session()
    initial = session.get(SSP_CLASSIC_CONSULTA_URL, timeout=SSP_REQUEST_TIMEOUT)
    query_page = submit_ssp_post(session, initial.text, VEHICLE_QUERY_TARGETS[occurrence_kind])
    page_html = query_page.text
    return {
        "departments": parse_ssp_department_options(page_html),
        "years": sorted(parse_ssp_year_targets(page_html).keys(), reverse=True),
        "months": sorted(parse_ssp_month_targets(page_html).keys()),
    }


@st.cache_data(show_spinner=False)
def get_ssp_official_options(occurrence_kind: str) -> dict[str, Any]:
    return fetch_ssp_official_options(occurrence_kind)


def build_ssp_export_cache_path(
    occurrence_kind: str,
    year: int,
    month: int,
    department_value: str,
    extension: str,
) -> Path:
    slug = normalize_key(occurrence_kind).replace(" ", "_")
    SSP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return SSP_CACHE_DIR / f"{slug}_{year}_{month:02d}_{department_value}{extension}"


def download_ssp_official_export(
    occurrence_kind: str,
    year: int,
    month: int,
    department_value: str,
    force_refresh: bool = False,
) -> Path:
    cache_candidates = [
        build_ssp_export_cache_path(occurrence_kind, year, month, department_value, extension)
        for extension in (".xlsx", ".xls", ".html")
    ]
    for candidate in cache_candidates:
        if candidate.exists() and candidate.stat().st_size > 0 and not force_refresh:
            return candidate

    session = requests.Session()
    initial = session.get(SSP_CLASSIC_CONSULTA_URL, timeout=SSP_REQUEST_TIMEOUT)
    query_page = submit_ssp_post(session, initial.text, VEHICLE_QUERY_TARGETS[occurrence_kind])
    page_html = query_page.text

    year_targets = parse_ssp_year_targets(page_html)
    month_targets = parse_ssp_month_targets(page_html)
    if year not in year_targets:
        raise ValueError(f"Ano {year} nao esta disponivel na consulta oficial da SSP.")
    if month not in month_targets:
        raise ValueError(f"Mes {month} nao esta disponivel na consulta oficial da SSP.")

    page_html = submit_ssp_post(
        session,
        page_html,
        VEHICLE_QUERY_TARGETS[occurrence_kind],
        extra_fields={"ctl00$cphBody$filtroDepartamento": department_value},
    ).text
    page_html = submit_ssp_post(
        session,
        page_html,
        year_targets[year],
        extra_fields={"ctl00$cphBody$filtroDepartamento": department_value},
    ).text
    page_html = submit_ssp_post(
        session,
        page_html,
        month_targets[month],
        extra_fields={"ctl00$cphBody$filtroDepartamento": department_value},
    ).text

    token = str(pd.Timestamp.utcnow().value)
    payload = extract_hidden_fields(page_html)
    payload["__EVENTTARGET"] = "ctl00$cphBody$ExportarBOLink"
    payload["__EVENTARGUMENT"] = ""
    payload["ctl00$cphBody$hdfExport"] = token
    payload["ctl00$cphBody$filtroDepartamento"] = department_value

    export_response = session.post(
        SSP_CLASSIC_CONSULTA_URL,
        data=payload,
        timeout=SSP_REQUEST_TIMEOUT,
    )
    if export_response.status_code >= 400:
        raise ValueError(f"A SSP retornou erro HTTP {export_response.status_code} ao exportar a base.")

    content_type = export_response.headers.get("Content-Type", "").lower()
    disposition = export_response.headers.get("Content-Disposition", "").lower()
    content_prefix = export_response.content[:64].lstrip().lower()

    if "spreadsheetml" in content_type or ".xlsx" in disposition:
        extension = ".xlsx"
    elif "excel" in content_type or ".xls" in disposition:
        extension = ".xls"
    elif content_prefix.startswith(b"<!doctype html") or content_prefix.startswith(b"<html"):
        extension = ".html"
    else:
        extension = ".xls"

    cache_path = build_ssp_export_cache_path(
        occurrence_kind=occurrence_kind,
        year=year,
        month=month,
        department_value=department_value,
        extension=extension,
    )
    cache_path.write_bytes(export_response.content)

    if extension == ".html" and "Verifique os erros abaixo" in export_response.text:
        raise ValueError("A SSP respondeu com uma pagina de erro em vez da planilha exportada.")

    return cache_path


def split_brand_model(value: str) -> tuple[str | None, str | None]:
    text = str(value or "").strip().upper()
    if not text:
        return None, None
    if "/" in text:
        brand, model = text.split("/", 1)
        return brand.strip() or None, model.strip() or None
    parts = text.split()
    if not parts:
        return None, None
    return parts[0], text


def classify_occurrence(natureza: str) -> str:
    text = normalize_key(natureza)
    if "roubo" in text:
        return "Roubo"
    if "furto" in text:
        return "Furto"
    if "roubado" in text:
        return "Roubo"
    if "furtado" in text:
        return "Furto"
    return "Outro"


def classify_quick_scope(row: pd.Series) -> str:
    brand = str(row.get("marca", "") or "").upper()
    model = str(row.get("modelo", "") or "").upper()
    brand_model = str(row.get("marca_modelo", "") or "").upper()
    vehicle_type = normalize_key(row.get("tipo_veiculo", ""))

    if "INDIAN" in brand or "INDIAN" in model or "INDIAN" in brand_model:
        return "Indian"
    if any(token in brand_model for token in ("HARLEY", "LIVEWIRE", "X440", "S2 ")):
        return "Harley / LiveWire"
    if any(term in vehicle_type for term in MOTORCYCLE_TERMS):
        return "Somente motocicletas"
    return "Todos os veiculos"


def looks_like_motorcycle(row: pd.Series) -> bool:
    vehicle_type = normalize_key(row.get("tipo_veiculo", ""))
    if any(term in vehicle_type for term in MOTORCYCLE_TERMS):
        return True
    scope = classify_quick_scope(row)
    return scope in {"Harley / LiveWire", "Indian"}


def prepare_ssp_vehicle_dataframe(raw_df: pd.DataFrame) -> pd.DataFrame:
    renamed = raw_df.rename(columns=canonicalize_ssp_columns(raw_df.columns.tolist())).copy()

    if "natureza" not in renamed.columns and "DESCR_OCORRENCIA_VEICULO" in raw_df.columns:
        renamed["natureza"] = raw_df["DESCR_OCORRENCIA_VEICULO"]
    if "data_fato" not in renamed.columns and "DATA_OCORRENCIA_BO" in raw_df.columns:
        renamed["data_fato"] = raw_df["DATA_OCORRENCIA_BO"]
    if "municipio" not in renamed.columns and "CIDADE" in raw_df.columns:
        renamed["municipio"] = raw_df["CIDADE"]
    if "bairro" not in renamed.columns and "BAIRRO" in raw_df.columns:
        renamed["bairro"] = raw_df["BAIRRO"]
    if "delegacia" not in renamed.columns and "NOME_DELEGACIA_CIRC" in raw_df.columns:
        renamed["delegacia"] = raw_df["NOME_DELEGACIA_CIRC"]
    if "tipo_veiculo" not in renamed.columns and "DESCR_TIPO_VEICULO" in raw_df.columns:
        renamed["tipo_veiculo"] = raw_df["DESCR_TIPO_VEICULO"]
    if "marca_modelo" not in renamed.columns and "DESCR_MARCA_VEICULO" in raw_df.columns:
        renamed["marca_modelo"] = raw_df["DESCR_MARCA_VEICULO"]
    if "ano_fabricacao" not in renamed.columns and "ANO_FABRICACAO" in raw_df.columns:
        renamed["ano_fabricacao"] = raw_df["ANO_FABRICACAO"]
    if "ano_modelo" not in renamed.columns and "ANO_MODELO" in raw_df.columns:
        renamed["ano_modelo"] = raw_df["ANO_MODELO"]
    if "placa" not in renamed.columns and "PLACA_VEICULO" in raw_df.columns:
        renamed["placa"] = raw_df["PLACA_VEICULO"]
    if "cor" not in renamed.columns and "DESC_COR_VEICULO" in raw_df.columns:
        renamed["cor"] = raw_df["DESC_COR_VEICULO"]

    if "marca_modelo" not in renamed.columns and {"marca", "modelo"}.issubset(renamed.columns):
        renamed["marca_modelo"] = (
            renamed["marca"].fillna("").astype(str).str.strip()
            + "/"
            + renamed["modelo"].fillna("").astype(str).str.strip()
        ).str.strip("/")

    if "marca_modelo" in renamed.columns and "marca" not in renamed.columns:
        split_values = renamed["marca_modelo"].map(split_brand_model)
        renamed["marca"] = split_values.map(lambda item: item[0] if item else None)
        renamed["modelo"] = split_values.map(lambda item: item[1] if item else None)

    duplicate_columns = [column for column in renamed.columns if isinstance(column, str) and list(renamed.columns).count(column) > 1]
    for column in sorted(set(duplicate_columns)):
        duplicated_frame = renamed.loc[:, renamed.columns == column]
        collapsed = duplicated_frame.bfill(axis=1).iloc[:, 0]
        renamed = renamed.drop(columns=column)
        renamed[column] = collapsed

    required_any = {"data_fato", "natureza", "municipio"}
    if not required_any.issubset(set(renamed.columns)):
        missing = ", ".join(sorted(required_any - set(renamed.columns)))
        raise KeyError(
            "A planilha da SSP nao trouxe as colunas minimas esperadas. "
            f"Ausentes: {missing}. Disponiveis: {', '.join(str(c) for c in renamed.columns)}"
        )

    renamed["data_fato"] = pd.to_datetime(renamed["data_fato"], dayfirst=True, errors="coerce")
    renamed = renamed.dropna(subset=["data_fato"]).copy()
    if renamed.empty:
        raise ValueError("A planilha foi lida, mas nenhuma data valida foi encontrada na base da SSP.")

    for column in ["municipio", "uf", "bairro", "delegacia", "natureza", "placa", "cor", "tipo_veiculo"]:
        if column in renamed.columns:
            renamed[column] = renamed[column].astype(str).str.strip()

    for column in ["marca_modelo", "marca", "modelo"]:
        if column in renamed.columns:
            renamed[column] = renamed[column].astype(str).str.upper().str.strip()

    for column in ["ano_modelo", "ano_fabricacao"]:
        if column in renamed.columns:
            renamed[column] = pd.to_numeric(renamed[column], errors="coerce").astype("Int64")

    if "DESCR_OCORRENCIA_VEICULO" in raw_df.columns:
        renamed["tipo_crime"] = raw_df["DESCR_OCORRENCIA_VEICULO"].map(classify_occurrence)
    else:
        renamed["tipo_crime"] = renamed["natureza"].map(classify_occurrence)
    renamed["ano"] = renamed["data_fato"].dt.year.astype(int)
    renamed["mes"] = renamed["data_fato"].dt.month.astype(int)
    renamed["competencia"] = renamed["data_fato"].dt.to_period("M").dt.to_timestamp()
    renamed["escopo_rapido"] = renamed.apply(classify_quick_scope, axis=1)
    renamed["is_moto"] = renamed.apply(looks_like_motorcycle, axis=1)

    visible_columns = [
        column
        for column in [
            "data_fato",
            "competencia",
            "ano",
            "mes",
            "tipo_crime",
            "natureza",
            "municipio",
            "uf",
            "bairro",
            "delegacia",
            "tipo_veiculo",
            "marca",
            "modelo",
            "marca_modelo",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
            "placa",
            "escopo_rapido",
            "is_moto",
        ]
        if column in renamed.columns
    ]
    return renamed[visible_columns].copy()


def fetch_remote_excel(url: str) -> Path:
    SSP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(url.split("?", 1)[0]).suffix or ".xlsx"
    cache_path = SSP_CACHE_DIR / f"remote_{abs(hash(url))}{suffix}"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/octet-stream,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
    cache_path.write_bytes(payload)
    return cache_path


@st.cache_data(show_spinner=False)
def load_ssp_vehicle_base_from_path(source_path: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    best_df, sheet_name, header_row = detect_best_sheet_frame(source_path)
    prepared = prepare_ssp_vehicle_dataframe(best_df)
    meta = {
        "source_label": source_path,
        "sheet_name": sheet_name,
        "header_row": header_row,
        "row_count": int(len(prepared)),
    }
    return prepared, meta


@st.cache_data(show_spinner=False)
def load_ssp_vehicle_base_from_bytes(source_bytes: bytes, source_label: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    best_df, sheet_name, header_row = detect_best_sheet_frame(source_bytes)
    prepared = prepare_ssp_vehicle_dataframe(best_df)
    meta = {
        "source_label": source_label,
        "sheet_name": sheet_name,
        "header_row": header_row,
        "row_count": int(len(prepared)),
    }
    return prepared, meta


def fetch_ssp_official_export(
    occurrence_kind: str,
    year: int,
    month: int,
    department_value: str,
    force_refresh: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    export_path = download_ssp_official_export(
        occurrence_kind=occurrence_kind,
        year=year,
        month=month,
        department_value=department_value,
        force_refresh=force_refresh,
    )
    df, meta = load_ssp_vehicle_base_from_path(str(export_path))
    meta.update(
        {
            "source_mode": "official_ssp",
            "occurrence_kind": occurrence_kind,
            "query_year": year,
            "query_month": month,
            "department_value": department_value,
        }
    )
    return df, meta


@st.cache_data(show_spinner=False)
def load_ssp_official_export(
    occurrence_kind: str,
    year: int,
    month: int,
    department_value: str,
    force_refresh: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    return fetch_ssp_official_export(
        occurrence_kind=occurrence_kind,
        year=year,
        month=month,
        department_value=department_value,
        force_refresh=force_refresh,
    )


@st.cache_data(show_spinner=False)
def load_ssp_vehicle_base_from_duckdb(db_path: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = read_ssp_rows(db_path)
    snapshots = list_ssp_loaded_snapshots(db_path)
    if df.empty:
        raise ValueError("A base DuckDB da SSP ainda esta vazia.")
    meta = {
        "source_label": db_path,
        "sheet_name": "duckdb",
        "header_row": 0,
        "row_count": int(len(df)),
        "snapshots": int(len(snapshots)),
    }
    return df, meta


def load_ssp_vehicle_base(
    source_mode: str,
    source_value: str,
    uploaded_file,
    official_config: dict[str, Any] | None = None,
    duckdb_path: str | None = None,
) -> tuple[pd.DataFrame | None, dict[str, Any] | None, str | None]:
    try:
        if source_mode == "Base DuckDB SSP":
            if not duckdb_path:
                return None, None, "Banco DuckDB da SSP nao informado."
            df, meta = load_ssp_vehicle_base_from_duckdb(duckdb_path)
            return df, meta, None

        if source_mode == "Fonte oficial SSP (beta)":
            if official_config is None:
                return None, None, "Configuracao oficial ausente."
            df, meta = load_ssp_official_export(
                occurrence_kind=official_config["occurrence_kind"],
                year=int(official_config["year"]),
                month=int(official_config["month"]),
                department_value=str(official_config["department_value"]),
                force_refresh=bool(official_config.get("force_refresh", False)),
            )
            return df, meta, None

        if uploaded_file is not None:
            payload = uploaded_file.getvalue()
            df, meta = load_ssp_vehicle_base_from_bytes(payload, uploaded_file.name)
            return df, meta, None

        if not source_value.strip():
            return None, None, None

        if source_mode == "URL da planilha":
            cached_path = fetch_remote_excel(source_value.strip())
            df, meta = load_ssp_vehicle_base_from_path(str(cached_path))
            meta["remote_url"] = source_value.strip()
            return df, meta, None

        source_path = Path(source_value).expanduser()
        if not source_path.exists():
            return None, None, f"Arquivo nao encontrado: {source_path}"
        df, meta = load_ssp_vehicle_base_from_path(str(source_path.resolve()))
        return df, meta, None
    except Exception as exc:
        return None, None, str(exc)


def apply_ssp_filters(
    df: pd.DataFrame,
    quick_scope: str,
    years: list[int],
    municipalities: list[str],
    search_term: str,
) -> pd.DataFrame:
    filtered = df.copy()
    if quick_scope == "Somente motocicletas":
        filtered = filtered[filtered["is_moto"]]
    elif quick_scope in {"Harley / LiveWire", "Indian"}:
        filtered = filtered[filtered["escopo_rapido"] == quick_scope]

    if years:
        filtered = filtered[filtered["ano"].isin(years)]
    if municipalities:
        filtered = filtered[filtered["municipio"].isin(municipalities)]
    if search_term.strip():
        pattern = search_term.strip().upper()
        brand_model = filtered.get("marca_modelo", pd.Series("", index=filtered.index))
        model = filtered.get("modelo", pd.Series("", index=filtered.index))
        brand = filtered.get("marca", pd.Series("", index=filtered.index))
        filtered = filtered[
            brand_model.astype(str).str.contains(pattern, na=False)
            | model.astype(str).str.contains(pattern, na=False)
            | brand.astype(str).str.contains(pattern, na=False)
        ]
    return filtered


def render_ssp_theft_page():
    st.title("Roubos e Furtos | SSP-SP")
    st.caption(
        "Leitura direta da base de veiculos subtraidos da SSP-SP. "
        "A nova aba tenta buscar a exportacao oficial da SSP automaticamente e mantém fallback manual."
    )
    st.caption(f"Fonte oficial: [Consultas SSP-SP]({SSP_CONSULTAS_URL})")

    with st.sidebar:
        st.header("Fonte SSP")
        source_mode = st.radio(
            "Origem da planilha",
            options=["Base DuckDB SSP", "Fonte oficial SSP (beta)", "Arquivo local", "URL da planilha"],
            index=0,
        )
        default_source = os.getenv(SSP_SOURCE_ENV, "")
        uploaded_file = None
        source_value = ""
        official_config: dict[str, Any] | None = None
        duckdb_path = str(DEFAULT_SSP_DB)

        if source_mode == "Base DuckDB SSP":
            duckdb_path = st.text_input("Banco DuckDB SSP", value=str(DEFAULT_SSP_DB))
            snapshots = list_ssp_loaded_snapshots(duckdb_path)
            if snapshots.empty:
                st.caption("Base ainda vazia. Rode o backfill mensal para popular este banco.")
            else:
                latest = snapshots.iloc[0]
                st.caption(
                    f"Snapshots carregados: {len(snapshots)} | "
                    f"mais recente: {latest['occurrence_kind']} {int(latest['query_month']):02d}/{int(latest['query_year'])}"
                )
        elif source_mode == "Fonte oficial SSP (beta)":
            occurrence_kind = st.selectbox(
                "Natureza consultada",
                options=list(VEHICLE_QUERY_TARGETS.keys()),
                index=0,
            )
            try:
                options = get_ssp_official_options(occurrence_kind)
            except Exception as exc:
                st.error(f"Falha ao consultar a fonte oficial da SSP: {exc}")
                st.stop()

            years = options["years"]
            months = options["months"]
            departments = options["departments"]
            selected_year = st.selectbox("Ano da consulta", options=years, index=0)
            default_month_index = min(len(months), pd.Timestamp.today().month) - 1 if months else 0
            selected_month = st.selectbox(
                "Mes da consulta",
                options=months,
                index=max(default_month_index, 0),
                format_func=lambda month: MONTH_NAMES_PT.get(month, str(month)),
            )
            department_labels = {value: label for value, label in departments}
            department_values = [value for value, _label in departments]
            selected_department = st.selectbox(
                "Circunscricao",
                options=department_values,
                index=0,
                format_func=lambda value: department_labels.get(value, value),
            )
            force_refresh = st.checkbox("Forcar novo download da SSP", value=False)
            official_config = {
                "occurrence_kind": occurrence_kind,
                "year": selected_year,
                "month": selected_month,
                "department_value": selected_department,
                "force_refresh": force_refresh,
            }
        else:
            uploaded_file = st.file_uploader(
                "Upload da planilha (.xlsx/.xls/.html)",
                type=["xlsx", "xls", "html"],
                help="Se preferir, solte aqui a planilha exportada da SSP.",
            )
            source_value = st.text_input(
                "Caminho ou URL",
                value=default_source,
                placeholder=(
                    "/caminho/para/veiculos_subtraidos.xlsx"
                    if source_mode == "Arquivo local"
                    else "https://..."
                ),
            )

    with st.spinner("Carregando base da SSP..."):
        df, meta, error = load_ssp_vehicle_base(
            source_mode,
            source_value,
            uploaded_file,
            official_config=official_config,
            duckdb_path=duckdb_path,
        )

    if error:
        st.error(f"Falha ao carregar a planilha da SSP: {error}")
        st.stop()
    if df is None or meta is None:
        st.info("Informe uma planilha da SSP ou use a fonte oficial para ativar esta aba.")
        st.stop()

    c1, c2, c3 = st.columns((1, 1, 2))
    c1.metric("Linhas lidas", f"{meta['row_count']:,}".replace(",", "."))
    c2.metric("Aba detectada", meta["sheet_name"])
    if meta["sheet_name"] == "duckdb":
        c3.caption(
            f"Fonte carregada: `{meta['source_label']}` | "
            f"snapshots: {meta.get('snapshots', 0)}"
        )
    else:
        c3.caption(
            f"Header detectado na linha {int(meta['header_row']) + 1}. "
            f"Fonte carregada: `{meta['source_label']}`"
        )

    scope_col, year_col, city_col = st.columns((1, 1, 2))
    years = sorted(df["ano"].dropna().astype(int).unique().tolist())
    municipalities = sorted(df["municipio"].dropna().astype(str).unique().tolist())
    with scope_col:
        quick_scope = st.selectbox(
            "Recorte rapido",
            options=["Todos os veiculos", "Somente motocicletas", "Harley / LiveWire", "Indian"],
            index=1,
        )
    with year_col:
        selected_years = st.multiselect(
            "Anos",
            options=years,
            default=years[-3:] if len(years) >= 3 else years,
        )
    with city_col:
        selected_cities = st.multiselect("Municipios", options=municipalities, default=[])

    search_term = st.text_input(
        "Busca por marca/modelo",
        value="",
        placeholder="Ex.: HARLEY, FLHX, SPORTSTER, ROAD GLIDE",
    )

    filtered = apply_ssp_filters(
        df=df,
        quick_scope=quick_scope,
        years=selected_years,
        municipalities=selected_cities,
        search_term=search_term,
    )
    if filtered.empty:
        st.warning("Esse recorte nao retornou ocorrencias na base carregada.")
        st.stop()

    total = len(filtered)
    roubos = int((filtered["tipo_crime"] == "Roubo").sum())
    furtos = int((filtered["tipo_crime"] == "Furto").sum())
    municipios_count = int(filtered["municipio"].nunique())
    top_model = (
        filtered["marca_modelo"]
        .fillna("SEM MODELO")
        .astype(str)
        .value_counts()
        .rename_axis("marca_modelo")
        .reset_index(name="ocorrencias")
    )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Ocorrencias", f"{total:,}".replace(",", "."))
    k2.metric("Roubos", f"{roubos:,}".replace(",", "."))
    k3.metric("Furtos", f"{furtos:,}".replace(",", "."))
    k4.metric("Municipios", f"{municipios_count:,}".replace(",", "."))

    monthly = (
        filtered.groupby(["competencia", "tipo_crime"], as_index=False)
        .size()
        .rename(columns={"size": "ocorrencias"})
        .sort_values(["competencia", "tipo_crime"])
    )
    monthly["competencia"] = pd.to_datetime(monthly["competencia"])

    by_city = (
        filtered.groupby("municipio", as_index=False)
        .size()
        .rename(columns={"size": "ocorrencias"})
        .sort_values(["ocorrencias", "municipio"], ascending=[False, True])
        .head(15)
    )
    by_model = top_model.head(15)

    col_chart, col_rank = st.columns((1.5, 1))
    with col_chart:
        fig_monthly = px.line(
            monthly,
            x="competencia",
            y="ocorrencias",
            color="tipo_crime",
            markers=True,
            title=f"Serie mensal | {quick_scope}",
            color_discrete_map={"Roubo": "#E15759", "Furto": HARLEY_ORANGE, "Outro": "#8F8F8F"},
        )
        fig_monthly.update_layout(
            xaxis_title="Competencia",
            yaxis_title="Ocorrencias",
            legend_title_text="Tipo",
            hovermode="x unified",
        )
        fig_monthly.update_xaxes(tickformat="%b/%y")
        st.plotly_chart(fig_monthly, use_container_width=True)
    with col_rank:
        fig_city = px.bar(
            by_city.sort_values("ocorrencias", ascending=True),
            x="ocorrencias",
            y="municipio",
            orientation="h",
            title="Municipios com mais ocorrencias",
            color_discrete_sequence=[HARLEY_ORANGE],
        )
        fig_city.update_layout(xaxis_title="Ocorrencias", yaxis_title="Municipio")
        st.plotly_chart(fig_city, use_container_width=True)

    left, right = st.columns((1, 1))
    with left:
        st.subheader("Modelos mais citados")
        st.dataframe(
            by_model,
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "marca_modelo": "Marca / modelo",
                "ocorrencias": "Ocorrencias",
            },
        )
    with right:
        breakdown = (
            filtered.groupby(["tipo_crime", "municipio"], as_index=False)
            .size()
            .rename(columns={"size": "ocorrencias"})
            .sort_values(["ocorrencias", "municipio"], ascending=[False, True])
            .head(20)
        )
        st.subheader("Quebra por tipo e municipio")
        st.dataframe(
            breakdown,
            use_container_width=True,
            hide_index=True,
            height=420,
            column_config={
                "tipo_crime": "Tipo",
                "municipio": "Municipio",
                "ocorrencias": "Ocorrencias",
            },
        )

    display_columns = [
        column
        for column in [
            "data_fato",
            "tipo_crime",
            "natureza",
            "municipio",
            "uf",
            "delegacia",
            "tipo_veiculo",
            "marca_modelo",
            "ano_fabricacao",
            "ano_modelo",
            "cor",
        ]
        if column in filtered.columns
    ]
    st.subheader("Base exploratoria")
    st.caption("Leitura operacional da base da SSP para auditoria do recorte filtrado.")
    st.dataframe(
        filtered[display_columns].sort_values("data_fato", ascending=False),
        use_container_width=True,
        hide_index=True,
        height=520,
    )
