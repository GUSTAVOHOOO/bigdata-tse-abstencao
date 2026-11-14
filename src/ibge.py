"""Integracao IBGE: populacao, PIB, municipios e de-para TSE -> IBGE.

Cada tabela e' salva em data/bronze/ibge/<nome>.parquet e reaproveitada quando existe.
Execucao: python src/ibge.py (baixa/salva as quatro tabelas e imprime as contagens).
"""
import argparse
import io
import sys
from pathlib import Path

import pandas as pd
import requests

if __package__ in (None, ""):  # execucao direta: python src/ibge.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.coleta import com_retry
from src.config import ANOS, BRONZE

IBGE = BRONZE / "ibge"
TIMEOUT = 120

URL_POP_ESTIMATIVA = ("https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/"
                      "p/2018,2020,2021,2024")
URL_POP_CENSO = "https://apisidra.ibge.gov.br/values/t/4709/n6/all/v/93/p/2022"
URL_PIB = "https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2018,2020,2022,2023"
URL_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
URL_DEPARA = ("https://raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE/"
              "master/municipios_brasileiros_tse.csv")

ANOS_PIB: list[int] = [2018, 2020, 2022, 2023]
ANO_ELEICAO: dict[int, int] = {2023: 2024}  # PIB de 2023 entra no cruzamento da eleicao de 2024
_AUSENTE = ["...", "-", "X"]  # marcadores do SIDRA para dado indisponivel


def _get(url: str) -> requests.Response:
    """GET com o retry da coleta (repete em erro de rede/5xx; 4xx falha de imediato)."""
    def _tentar() -> requests.Response:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r
    return com_retry(_tentar)


def _get_json(url: str) -> list | dict:
    return _get(url).json()


def _cache(nome: str, gerar) -> pd.DataFrame:
    """Le IBGE/<nome>.parquet se existir; senao gera, salva e devolve."""
    caminho = IBGE / f"{nome}.parquet"
    if caminho.exists():
        return pd.read_parquet(caminho)
    df = gerar()
    IBGE.mkdir(parents=True, exist_ok=True)
    df.to_parquet(caminho, index=False)
    return df


def _sidra_valores(url: str) -> pd.DataFrame:
    """Tabela SIDRA em formato 'values' -> cd_municipio_ibge, ano, valor (float; ausente = NaN)."""
    dados = _get_json(url)
    registros = [
        {"cd_municipio_ibge": r["D1C"], "ano": int(r["D3C"]), "valor": r["V"]}
        for r in dados[1:]  # o primeiro elemento e' o cabecalho do SIDRA
    ]
    df = pd.DataFrame(registros, columns=["cd_municipio_ibge", "ano", "valor"])
    df["valor"] = pd.to_numeric(df["valor"].where(~df["valor"].isin(_AUSENTE)))
    return df


def _gerar_populacao_base() -> pd.DataFrame:
    estimativa = _sidra_valores(URL_POP_ESTIMATIVA).assign(fonte_populacao="estimativa_6579")
    censo = _sidra_valores(URL_POP_CENSO).assign(fonte_populacao="censo_4709")
    df = pd.concat([estimativa, censo], ignore_index=True).rename(columns={"valor": "populacao"})
    df["populacao"] = df["populacao"].astype("Int64")
    return df


def _ano_origem(ano: int, disponiveis: list[int]) -> int:
    """Ultimo ano disponivel ate 'ano'; se nao houver, o primeiro depois dele."""
    anteriores = [a for a in disponiveis if a <= ano]
    return max(anteriores) if anteriores else min(disponiveis)


def populacao_municipios(anos: list[int] = ANOS) -> pd.DataFrame:
    """Populacao por municipio e ano de eleicao.

    Fontes diretas: estimativa (6579) para 2018, 2020, 2021 e 2024; Censo 2022 (4709) para 2022.
    Anos sem fonte direta usam o ano disponivel mais proximo, e fonte_populacao registra
    qual ano foi usado (ex.: "censo_4709_2022" para 2023).
    """
    base = _cache("populacao_municipios", _gerar_populacao_base)
    disponiveis = sorted(int(a) for a in base["ano"].unique())
    partes = []
    for ano in anos:
        origem = _ano_origem(ano, disponiveis)
        parte = base[base["ano"] == origem].copy()
        parte["ano"] = ano
        if origem != ano:
            parte["fonte_populacao"] = parte["fonte_populacao"] + f"_{origem}"
        partes.append(parte)
    colunas = ["cd_municipio_ibge", "ano", "populacao", "fonte_populacao"]
    return pd.concat(partes, ignore_index=True)[colunas]


def calcular_pib_per_capita(pib_mil_reais, populacao):
    """PIB em mil reais -> reais por habitante."""
    return pib_mil_reais * 1000 / populacao


def _gerar_pib() -> pd.DataFrame:
    pib = _sidra_valores(URL_PIB).rename(columns={"valor": "pib_mil_reais"})
    populacao = populacao_municipios(ANOS_PIB)[["cd_municipio_ibge", "ano", "populacao"]]
    df = pib.merge(populacao, on=["cd_municipio_ibge", "ano"], how="left")
    df["pib_per_capita"] = calcular_pib_per_capita(df["pib_mil_reais"],
                                                   df["populacao"].astype("float64"))
    df["ano_eleicao"] = df["ano"].map(lambda a: ANO_ELEICAO.get(a, a))
    return df[["cd_municipio_ibge", "ano", "pib_mil_reais", "pib_per_capita", "ano_eleicao"]]


def pib_municipios() -> pd.DataFrame:
    """PIB municipal (tabela 5938) com PIB per capita pela populacao do mesmo ano.

    ano_eleicao: 2023 -> 2024 (PIB do ultimo ano disponivel entra na eleicao seguinte);
    os demais anos ficam iguais. O per capita de 2023 usa o Censo 2022.
    """
    return _cache("pib_municipios", _gerar_pib)


def _gerar_municipios() -> pd.DataFrame:
    linhas = []
    for m in _get_json(URL_LOCALIDADES):
        if m.get("microrregiao"):
            uf = m["microrregiao"]["mesorregiao"]["UF"]
        else:  # alguns municipios vem sem microrregiao; a regiao imediata cobre o mesmo UF
            uf = m["regiao-imediata"]["regiao-intermediaria"]["UF"]
        linhas.append({
            "cd_municipio_ibge": str(m["id"]),
            "nm_municipio": m["nome"],
            "sg_uf": uf["sigla"],
            "nm_regiao": uf["regiao"]["nome"],
        })
    return pd.DataFrame(linhas, columns=["cd_municipio_ibge", "nm_municipio", "sg_uf", "nm_regiao"])


def municipios_ibge() -> pd.DataFrame:
    """Municipios com UF e grande regiao (API de localidades do IBGE)."""
    return _cache("municipios_ibge", _gerar_municipios)


def _gerar_depara() -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(_get(URL_DEPARA).content), dtype=str, encoding="utf-8")
    return pd.DataFrame({
        "cd_municipio_tse": df["codigo_tse"].astype(str).str.zfill(5),
        "cd_municipio_ibge": df["codigo_ibge"].astype(str).str.zfill(7),
    })


def depara_tse_ibge() -> pd.DataFrame:
    """De-para de codigos de municipio: TSE (5 digitos) -> IBGE (7 digitos)."""
    return _cache("depara_tse_ibge", _gerar_depara)


def main(argv: list[str] | None = None) -> None:
    argparse.ArgumentParser(description="Baixa as tabelas do IBGE para data/bronze/ibge").parse_args(argv)
    tabelas = {
        "populacao_municipios": populacao_municipios,
        "pib_municipios": pib_municipios,
        "municipios_ibge": municipios_ibge,
        "depara_tse_ibge": depara_tse_ibge,
    }
    for nome, func in tabelas.items():
        df = func()
        print(f"{nome}: {len(df)} linhas")


if __name__ == "__main__":
    main()
