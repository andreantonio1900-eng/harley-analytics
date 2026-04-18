from __future__ import annotations

import pandas as pd

from app.db import query_df


def list_competencias(con):
    sql = '''
    SELECT DISTINCT competencia
    FROM frota_harley
    ORDER BY competencia
    '''
    return query_df(con, sql)


def list_years(con):
    sql = '''
    SELECT DISTINCT ano_fabricacao
    FROM frota_harley
    WHERE ano_fabricacao IS NOT NULL
    ORDER BY ano_fabricacao
    '''
    return query_df(con, sql)


def info(con):
    sql = '''
    SELECT
      MIN(competencia) AS primeira_competencia,
      MAX(competencia) AS ultima_competencia,
      COUNT(*) AS linhas,
      COUNT(DISTINCT marca_modelo) AS modelos_distintos
    FROM frota_harley
    '''
    return query_df(con, sql)


def sem_info_my_monthly_series(con, ano_modelo: int):
    sql = '''
    WITH catalogo AS (
      SELECT DISTINCT marca_modelo
      FROM frota_harley
      WHERE ano_fabricacao = ?
    )
    SELECT
      competencia,
      COUNT(DISTINCT marca_modelo) AS modelos,
      SUM(qtd_veiculos) AS total_sem_info
    FROM frota_harley
    WHERE upper(trim(municipio)) = 'SEM INFORMAÇÃO'
      AND marca_modelo IN (SELECT marca_modelo FROM catalogo)
      AND EXTRACT(year FROM competencia) IN (?, ?)
    GROUP BY competencia
    ORDER BY competencia
    '''
    return query_df(con, sql, [ano_modelo, ano_modelo - 1, ano_modelo])


def sem_info_my_snapshot(con, competencia: str, ano_modelo: int):
    sql = '''
    WITH catalogo AS (
      SELECT DISTINCT marca_modelo
      FROM frota_harley
      WHERE ano_fabricacao = ?
    ),
    serie AS (
      SELECT
        competencia,
        COUNT(DISTINCT marca_modelo) AS modelos,
        SUM(qtd_veiculos) AS total_sem_info
      FROM frota_harley
      WHERE upper(trim(municipio)) = 'SEM INFORMAÇÃO'
        AND marca_modelo IN (SELECT marca_modelo FROM catalogo)
        AND EXTRACT(year FROM competencia) IN (?, ?)
      GROUP BY competencia
    ),
    deltas AS (
      SELECT
        competencia,
        modelos,
        total_sem_info,
        total_sem_info - COALESCE(LAG(total_sem_info) OVER (ORDER BY competencia), 0) AS delta_sem_info
      FROM serie
    )
    SELECT
      competencia,
      modelos,
      total_sem_info,
      delta_sem_info
    FROM deltas
    WHERE competencia = ?
    '''
    return query_df(con, sql, [ano_modelo, ano_modelo - 1, ano_modelo, competencia])


def sem_info_my_top_models(con, competencia: str, ano_modelo: int, limit: int = 20):
    sql = '''
    WITH catalogo AS (
      SELECT DISTINCT marca_modelo
      FROM frota_harley
      WHERE ano_fabricacao = ?
    )
    SELECT
      marca_modelo,
      SUM(qtd_veiculos) AS total_sem_info
    FROM frota_harley
    WHERE upper(trim(municipio)) = 'SEM INFORMAÇÃO'
      AND competencia = ?
      AND marca_modelo IN (SELECT marca_modelo FROM catalogo)
      AND EXTRACT(year FROM competencia) IN (?, ?)
    GROUP BY marca_modelo
    ORDER BY total_sem_info DESC, marca_modelo
    LIMIT ?
    '''
    return query_df(con, sql, [ano_modelo, competencia, ano_modelo - 1, ano_modelo, limit])


def sem_info_my_model_series(con, ano_modelo: int):
    sql = '''
    WITH catalogo AS (
      SELECT DISTINCT marca_modelo
      FROM frota_harley
      WHERE ano_fabricacao = ?
    )
    SELECT
      competencia,
      marca_modelo,
      SUM(qtd_veiculos) AS total_sem_info
    FROM frota_harley
    WHERE upper(trim(municipio)) = 'SEM INFORMAÇÃO'
      AND marca_modelo IN (SELECT marca_modelo FROM catalogo)
      AND EXTRACT(year FROM competencia) IN (?, ?)
    GROUP BY competencia, marca_modelo
    ORDER BY competencia, marca_modelo
    '''
    return query_df(con, sql, [ano_modelo, ano_modelo - 1, ano_modelo])

def list_models_by_year(con, ano: int, competencia: str | None = None):
    sql = '''
    SELECT marca_modelo, SUM(qtd_veiculos) AS total
    FROM frota_harley
    WHERE ano_fabricacao = ?
    '''
    params = [ano]
    if competencia:
        sql += ' AND competencia = ?'
        params.append(competencia)
    sql += ' GROUP BY marca_modelo ORDER BY total DESC, marca_modelo'
    return query_df(con, sql, params)


def model_year_monthly_matrix(con, ano: int, competencia: str):
    competencia_ts = pd.Timestamp(competencia)
    ano_competencia = int(competencia_ts.year)
    mes_corte = int(competencia_ts.month)

    sql = '''
    WITH modelos AS (
      SELECT DISTINCT marca_modelo
      FROM frota_harley
      WHERE ano_fabricacao = ?
    ),
    totais AS (
      SELECT
        marca_modelo,
        EXTRACT(month FROM competencia) AS mes,
        SUM(qtd_veiculos) AS total
      FROM frota_harley
      WHERE ano_fabricacao = ?
        AND EXTRACT(year FROM competencia) = ?
        AND competencia <= ?
      GROUP BY marca_modelo, mes
    )
    SELECT
      m.marca_modelo,
      t.mes,
      t.total
    FROM modelos m
    LEFT JOIN totais t ON t.marca_modelo = m.marca_modelo
    '''
    df = query_df(con, sql, [ano, ano, ano_competencia, competencia])

    month_names = {
        1: "jan",
        2: "fev",
        3: "mar",
        4: "abr",
        5: "mai",
        6: "jun",
        7: "jul",
        8: "ago",
        9: "set",
        10: "out",
        11: "nov",
        12: "dez",
    }

    base = df.pivot_table(
        index="marca_modelo",
        columns="mes",
        values="total",
        aggfunc="sum",
    )
    base = base.reindex(columns=list(month_names.keys()))
    base = base.fillna(0)

    for mes in range(mes_corte + 1, 13):
        base[mes] = pd.NA

    base["sort_total"] = base[mes_corte].fillna(0)
    base = base.sort_values(["sort_total"], ascending=False).drop(columns=["sort_total"])
    base = base.rename(columns=month_names).reset_index()

    numeric_cols = [name for month, name in month_names.items() if month <= mes_corte]
    if numeric_cols:
        base[numeric_cols] = base[numeric_cols].astype("Int64")

    return base


def model_year_registrations_matrix(con, ano: int, competencia: str):
    competencia_ts = pd.Timestamp(competencia)
    ano_competencia = int(competencia_ts.year)
    mes_corte = int(competencia_ts.month)

    sql = '''
    WITH modelos AS (
      SELECT DISTINCT marca_modelo
      FROM frota_harley
      WHERE ano_fabricacao = ?
    ),
    serie AS (
      SELECT
        marca_modelo,
        competencia,
        SUM(qtd_veiculos) AS estoque
      FROM frota_harley
      WHERE ano_fabricacao = ?
        AND competencia <= ?
      GROUP BY marca_modelo, competencia
    ),
    deltas AS (
      SELECT
        marca_modelo,
        competencia,
        GREATEST(
          estoque - COALESCE(LAG(estoque) OVER (PARTITION BY marca_modelo ORDER BY competencia), 0),
          0
        ) AS emplacamentos
      FROM serie
    ),
    totais AS (
      SELECT
        marca_modelo,
        EXTRACT(month FROM competencia) AS mes,
        SUM(emplacamentos) AS total
      FROM deltas
      WHERE EXTRACT(year FROM competencia) = ?
      GROUP BY marca_modelo, mes
    )
    SELECT
      m.marca_modelo,
      t.mes,
      t.total
    FROM modelos m
    LEFT JOIN totais t ON t.marca_modelo = m.marca_modelo
    '''
    df = query_df(con, sql, [ano, ano, competencia, ano_competencia])

    month_names = {
        1: "jan",
        2: "fev",
        3: "mar",
        4: "abr",
        5: "mai",
        6: "jun",
        7: "jul",
        8: "ago",
        9: "set",
        10: "out",
        11: "nov",
        12: "dez",
    }

    base = df.pivot_table(
        index="marca_modelo",
        columns="mes",
        values="total",
        aggfunc="sum",
    )
    base = base.reindex(columns=list(month_names.keys()))
    base = base.fillna(0)

    for mes in range(mes_corte + 1, 13):
        base[mes] = pd.NA

    base["sort_total"] = base.loc[:, [mes for mes in range(1, mes_corte + 1)]].fillna(0).sum(axis=1)
    base = base.sort_values(["sort_total"], ascending=False).drop(columns=["sort_total"])
    base = base.rename(columns=month_names).reset_index()

    numeric_cols = [name for month, name in month_names.items() if month <= mes_corte]
    if numeric_cols:
        base[numeric_cols] = base[numeric_cols].astype("Int64")

    return base


def model_snapshot(con, modelo: str, competencia: str):
    sql = '''
    WITH serie AS (
      SELECT
        competencia,
        SUM(qtd_veiculos) AS estoque
      FROM frota_harley
      WHERE marca_modelo = ?
        AND competencia <= ?
      GROUP BY competencia
    ),
    deltas AS (
      SELECT
        competencia,
        estoque,
        estoque - COALESCE(LAG(estoque) OVER (ORDER BY competencia), 0) AS delta
      FROM serie
    )
    SELECT
      competencia,
      estoque,
      delta
    FROM deltas
    WHERE competencia = ?
    '''
    return query_df(con, sql, [modelo, competencia, competencia])


def model_share_by_uf(con, modelo: str, competencia: str):
    sql = '''
    SELECT
      uf,
      SUM(qtd_veiculos) AS total
    FROM frota_harley
    WHERE marca_modelo = ?
      AND competencia = ?
    GROUP BY uf
    ORDER BY total DESC, uf
    '''
    return query_df(con, sql, [modelo, competencia])


def model_share_by_city(con, modelo: str, competencia: str, limit: int = 15):
    sql = '''
    SELECT
      municipio,
      uf,
      SUM(qtd_veiculos) AS total
    FROM frota_harley
    WHERE marca_modelo = ?
      AND competencia = ?
    GROUP BY municipio, uf
    ORDER BY total DESC, municipio, uf
    LIMIT ?
    '''
    return query_df(con, sql, [modelo, competencia, limit])

def fleet_model(con, modelo: str, competencia: str | None = None):
    sql = '''
    SELECT competencia, uf, municipio, marca_modelo, ano_fabricacao, qtd_veiculos
    FROM frota_harley
    WHERE marca_modelo = ?
    '''
    params = [modelo]
    if competencia:
        sql += ' AND competencia = ?'
        params.append(competencia)
    sql += ' ORDER BY competencia, uf, municipio, ano_fabricacao'
    return query_df(con, sql, params)

def share_by_uf(con, competencia: str):
    sql = '''
    WITH base AS (
      SELECT uf, SUM(qtd_veiculos) AS total_hd_uf
      FROM frota_harley
      WHERE competencia = ?
      GROUP BY uf
    ),
    total_brasil AS (
      SELECT SUM(total_hd_uf) AS total_hd_brasil
      FROM base
    )
    SELECT
      b.uf,
      b.total_hd_uf,
      ROUND(100.0 * b.total_hd_uf / t.total_hd_brasil, 2) AS share_percentual
    FROM base b
    CROSS JOIN total_brasil t
    ORDER BY b.total_hd_uf DESC, b.uf
    '''
    return query_df(con, sql, [competencia])

def family_like(con, pattern: str):
    sql = '''
    SELECT competencia, marca_modelo, SUM(qtd_veiculos) AS total
    FROM frota_harley
    WHERE upper(marca_modelo) LIKE upper(?)
    GROUP BY competencia, marca_modelo
    ORDER BY competencia, marca_modelo
    '''
    return query_df(con, sql, [pattern])

def model_variation(con, modelo: str, inicio: str, fim: str):
    sql = '''
    WITH base AS (
      SELECT competencia, SUM(qtd_veiculos) AS estoque
      FROM frota_harley
      WHERE marca_modelo = ?
        AND competencia IN (?, ?)
      GROUP BY competencia
    )
    SELECT
      MAX(CASE WHEN competencia = ? THEN estoque END) AS inicio,
      MAX(CASE WHEN competencia = ? THEN estoque END) AS fim,
      MAX(CASE WHEN competencia = ? THEN estoque END)
        - MAX(CASE WHEN competencia = ? THEN estoque END) AS variacao
    FROM base
    '''
    return query_df(con, sql, [modelo, inicio, fim, inicio, fim, fim, inicio])

def monthly_series(con, modelo: str):
    sql = '''
    SELECT competencia, SUM(qtd_veiculos) AS estoque
    FROM frota_harley
    WHERE marca_modelo = ?
    GROUP BY competencia
    ORDER BY competencia
    '''
    return query_df(con, sql, [modelo])

def monthly_entries_proxy(con, modelo: str, inicio: str | None = None, fim: str | None = None):
    sql = '''
    WITH calendario AS (
      SELECT DISTINCT competencia
      FROM frota_harley
    ),
    base AS (
      SELECT competencia, SUM(qtd_veiculos) AS estoque
      FROM frota_harley
      WHERE marca_modelo = ?
      GROUP BY competencia
    ),
    serie AS (
      SELECT c.competencia, COALESCE(b.estoque, 0) AS estoque
      FROM calendario c
      LEFT JOIN base b ON c.competencia = b.competencia
    ),
    deltas AS (
      SELECT
        competencia,
        estoque,
        estoque - LAG(estoque) OVER (ORDER BY competencia) AS delta_mom
      FROM serie
    )
    SELECT
      competencia,
      estoque,
      COALESCE(delta_mom, 0) AS liquido,
      CASE WHEN delta_mom > 0 THEN delta_mom ELSE 0 END AS emplacamentos_proxy
    FROM deltas
    WHERE 1=1
    '''
    params = [modelo]
    if inicio:
        sql += ' AND competencia >= ?'
        params.append(inicio)
    if fim:
        sql += ' AND competencia <= ?'
        params.append(fim)
    sql += ' ORDER BY competencia'
    return query_df(con, sql, params)
