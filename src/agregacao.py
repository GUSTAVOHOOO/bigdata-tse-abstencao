"""Agregações de comparecimento e abstenção sobre tabelas com nomes em snake_case.

Camada gold: cada função `gold_*` lê a silver com DuckDB, pré-agrega até o grão necessário
(mantendo `nr_turno`, para que a regra de turno fique só em `taxa_abstencao`), e chama uma
função pura `_calc_*` em pandas. As `_calc_*` são testadas em `tests/test_agregacao.py`.

Execução (gera as quatro tabelas em data/gold/):
    .venv/Scripts/python.exe src/agregacao.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # execução direta: src/agregacao.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from src.config import GOLD, SILVER  # noqa: E402

SILVER_TSE_GLOB = (SILVER / "tse" / "**" / "*.parquet").as_posix()
NAO_INFORMADO = "NÃO INFORMADO"
IDADE_16_17 = "16–17"
IDADE_70_MAIS = "70+"
ESCOLARIDADE_SUPERIOR = "SUPERIOR COMPLETO"
ATRIBUTOS_MUNICIPIO = ["cd_municipio_ibge", "nm_municipio", "nm_regiao", "tipo_eleicao", "exterior",
                       "populacao", "fonte_populacao", "pib_per_capita"]
ROTULOS_PERFIL = ["faixa_etaria_agrupada", "grupo_idade", "ds_grau_escolaridade", "ds_genero"]


def taxa_abstencao(df: pd.DataFrame, por: list[str], turno: int = 1) -> pd.DataFrame:
    """Taxa de abstenção (fração 0–1) por grupo, num único turno.

    Filtra `nr_turno == turno` antes de somar: em 2018 e 2022 o mesmo eleitorado aparece
    nos dois turnos, e somar `qt_aptos` entre turnos duplicaria o denominador.
    Grupos com `qt_aptos == 0` recebem taxa NaN (sem divisão por zero).
    """
    turnos = pd.to_numeric(df["nr_turno"], errors="coerce")
    sub = df.loc[turnos == int(turno), por + ["qt_aptos", "qt_abstencao"]]
    r = sub.groupby(por, as_index=False, observed=True)[["qt_aptos", "qt_abstencao"]].sum()
    aptos = r["qt_aptos"].astype("float64")
    r["taxa_abstencao"] = r["qt_abstencao"] / aptos.where(aptos > 0)
    return r[por + ["qt_aptos", "qt_abstencao", "taxa_abstencao"]]


def abstencao_por_100k(qt_abstencao: pd.Series, populacao: pd.Series) -> pd.Series:
    """Abstenções por 100 mil habitantes; NaN quando a população é nula ou zero."""
    pop = pd.to_numeric(populacao, errors="coerce")
    return qt_abstencao / pop.where(pop > 0) * 100_000


def _marcar_outliers(df: pd.DataFrame) -> pd.Series:
    """Marca municípios com taxa fora de [Q1 − 1,5·IQR; Q3 + 1,5·IQR], calculada por ano.

    Os quartis usam só municípios não exteriores com taxa definida, no método linear do pandas.
    Exterior (ZZ) e taxa NaN ficam sem marca (NA), fora da referência.
    """
    exterior = df["exterior"].astype(bool).to_numpy()
    taxa = df["taxa_abstencao"].to_numpy(dtype=float)
    valido = ~exterior & np.isfinite(taxa)
    ref = df.loc[valido, ["ano", "taxa_abstencao"]]
    q = ref.groupby("ano")["taxa_abstencao"].quantile([0.25, 0.75]).unstack()
    q.columns = ["q1", "q3"]
    lim = q.reindex(df["ano"].to_numpy())
    q1, q3 = lim["q1"].to_numpy(dtype=float), lim["q3"].to_numpy(dtype=float)
    amp = 1.5 * (q3 - q1)
    fora = (taxa < q1 - amp) | (taxa > q3 + amp)
    return pd.Series(pd.array(np.where(valido, fora, pd.NA), dtype="boolean"), index=df.index)


def _calc_municipio_ano(pre: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por ano × UF × município, no 1º turno.

    `pre` tem uma linha por (ano, nr_turno, sg_uf, cd_municipio) com as somas
    `qt_aptos`, `qt_abstencao`, `aptos_16_17`, `aptos_70_mais` e `aptos_superior`.
    Atributos do município (população, PIB, região) são tomados uma vez por grupo, nunca somados.
    """
    chave = ["ano", "sg_uf", "cd_municipio"]
    taxa = taxa_abstencao(pre, chave, turno=1)
    grupo = pre.groupby(chave, as_index=False, observed=True, dropna=False)
    extras = grupo[["aptos_16_17", "aptos_70_mais", "aptos_superior"]].sum()
    atributos = grupo[ATRIBUTOS_MUNICIPIO].first()
    out = taxa.merge(extras, on=chave).merge(atributos, on=chave)

    aptos = out["qt_aptos"].astype("float64").where(lambda s: s > 0)
    out["pct_16_17"] = out.pop("aptos_16_17") / aptos
    out["pct_70_mais"] = out.pop("aptos_70_mais") / aptos
    out["pct_superior"] = out.pop("aptos_superior") / aptos
    out["abstencoes_por_100k_hab"] = abstencao_por_100k(out["qt_abstencao"], out["populacao"])
    out["outlier_iqr"] = _marcar_outliers(out)
    return out[["ano", "sg_uf", "cd_municipio", "cd_municipio_ibge", "nm_municipio", "nm_regiao",
                "tipo_eleicao", "exterior", "populacao", "fonte_populacao", "pib_per_capita",
                "qt_aptos", "qt_abstencao", "taxa_abstencao", "abstencoes_por_100k_hab",
                "pct_16_17", "pct_70_mais", "pct_superior", "outlier_iqr"]].reset_index(drop=True)


def _calc_uf_ano(pre: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por ano × UF × região × tipo de eleição, no 1º turno, sem exterior."""
    pre = pre.loc[~pre["exterior"].astype(bool)]
    return taxa_abstencao(pre, ["ano", "sg_uf", "nm_regiao", "tipo_eleicao"], turno=1)


def _calc_perfil_ano(pre: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por ano × faixa etária × grupo de idade × escolaridade × gênero × exterior, 1º turno.

    Rótulos nulos viram NÃO INFORMADO e permanecem; os gráficos decidem se os filtram.
    """
    pre = pre.copy()
    pre[ROTULOS_PERFIL] = pre[ROTULOS_PERFIL].fillna(NAO_INFORMADO)
    chave = ["ano", *ROTULOS_PERFIL, "exterior"]
    return taxa_abstencao(pre, chave, turno=1)


def _calc_turnos(pre: pd.DataFrame) -> pd.DataFrame:
    """Taxas por turno (ano × nr_turno × tipo de eleição), sem exterior.

    `com_2o_turno`: só municípios com 2º turno no ano, nos dois turnos, para o mesmo conjunto.
    `todos`: 1º turno de todos os municípios (comparação com o conjunto acima).
    """
    pre = pre.loc[~pre["exterior"].astype(bool)]
    chave = ["ano", "nr_turno", "tipo_eleicao"]
    com = pre.loc[pre["tem_2o_turno"].astype(bool)]
    partes = [taxa_abstencao(com, chave, turno=t).assign(conjunto="com_2o_turno") for t in (1, 2)]
    partes.append(taxa_abstencao(pre, chave, turno=1).assign(conjunto="todos"))
    r = pd.concat(partes, ignore_index=True)
    return r[["conjunto", "ano", "nr_turno", "tipo_eleicao", "qt_aptos", "qt_abstencao",
              "taxa_abstencao"]]


def _consultar(sql: str) -> pd.DataFrame:
    return duckdb.sql(sql).df()


def _silver(colunas: str, filtro: str = "TRUE") -> str:
    return (f"SELECT {colunas} FROM read_parquet('{SILVER_TSE_GLOB}', hive_partitioning = true) "
            f"WHERE {filtro} GROUP BY ALL")


def _salvar(df: pd.DataFrame, nome: str) -> pd.DataFrame:
    GOLD.mkdir(parents=True, exist_ok=True)
    df.to_parquet(GOLD / nome, index=False)
    return df


def gold_municipio_ano() -> pd.DataFrame:
    sql = f"""
        SELECT ano, nr_turno, sg_uf, cd_municipio,
               ANY_VALUE(cd_municipio_ibge) AS cd_municipio_ibge,
               ANY_VALUE(nm_municipio) AS nm_municipio,
               ANY_VALUE(nm_regiao) AS nm_regiao,
               ANY_VALUE(tipo_eleicao) AS tipo_eleicao,
               ANY_VALUE(exterior) AS exterior,
               ANY_VALUE(populacao) AS populacao,
               ANY_VALUE(fonte_populacao) AS fonte_populacao,
               ANY_VALUE(pib_per_capita) AS pib_per_capita,
               SUM(qt_aptos) AS qt_aptos,
               SUM(qt_abstencao) AS qt_abstencao,
               SUM(qt_aptos) FILTER (WHERE grupo_idade = '{IDADE_16_17}') AS aptos_16_17,
               SUM(qt_aptos) FILTER (WHERE grupo_idade = '{IDADE_70_MAIS}') AS aptos_70_mais,
               SUM(qt_aptos) FILTER (WHERE ds_grau_escolaridade = '{ESCOLARIDADE_SUPERIOR}')
                   AS aptos_superior
        FROM read_parquet('{SILVER_TSE_GLOB}', hive_partitioning = true)
        WHERE nr_turno = 1
        GROUP BY ALL
    """
    df = _calc_municipio_ano(_consultar(sql))
    return _salvar(df, "municipio_ano.parquet")


def gold_uf_ano() -> pd.DataFrame:
    df = _calc_uf_ano(_consultar(_silver(
        "ano, nr_turno, sg_uf, nm_regiao, tipo_eleicao, exterior, "
        "SUM(qt_aptos) AS qt_aptos, SUM(qt_abstencao) AS qt_abstencao",
        "nr_turno = 1")))
    return _salvar(df, "uf_ano.parquet")


def gold_perfil_ano() -> pd.DataFrame:
    colunas = ("ano, nr_turno, faixa_etaria_agrupada, grupo_idade, ds_grau_escolaridade, "
               "ds_genero, exterior, SUM(qt_aptos) AS qt_aptos, SUM(qt_abstencao) AS qt_abstencao")
    df = _calc_perfil_ano(_consultar(_silver(colunas, "nr_turno = 1")))
    return _salvar(df, "perfil_ano.parquet")


def gold_turnos() -> pd.DataFrame:
    colunas = ("ano, nr_turno, sg_uf, cd_municipio, ANY_VALUE(tipo_eleicao) AS tipo_eleicao, "
               "ANY_VALUE(tem_2o_turno) AS tem_2o_turno, ANY_VALUE(exterior) AS exterior, "
               "SUM(qt_aptos) AS qt_aptos, SUM(qt_abstencao) AS qt_abstencao")
    df = _calc_turnos(_consultar(_silver(colunas)))
    return _salvar(df, "turnos.parquet")


def main() -> None:
    geracao = {
        "municipio_ano": gold_municipio_ano,
        "uf_ano": gold_uf_ano,
        "perfil_ano": gold_perfil_ano,
        "turnos": gold_turnos,
    }
    for nome, gerar in geracao.items():
        df = gerar()
        print(f"{nome}: {len(df):,} linhas -> {GOLD / (nome + '.parquet')}")


if __name__ == "__main__":
    main()
