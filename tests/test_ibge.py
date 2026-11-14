"""Testes da integracao IBGE (sem acesso a rede: requests.get e' substituido por rotas fixas)."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src import ibge

CABECALHO_SIDRA = {"NC": "Nível Territorial (Código)", "V": "Valor",
                   "D1C": "Município (Código)", "D3C": "Ano (Código)"}


@pytest.fixture(autouse=True)
def cache_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(ibge, "IBGE", tmp_path)
    yield tmp_path


def _fake_get(rotas: dict):
    """Devolve um requests.get falso: a primeira chave contida na URL define a resposta."""
    def get(url, timeout=None, **_):
        for trecho, corpo in rotas.items():
            if trecho in url:
                r = MagicMock()
                r.raise_for_status.return_value = None
                r.json.return_value = corpo if not isinstance(corpo, bytes) else None
                r.content = corpo if isinstance(corpo, bytes) else b""
                return r
        raise AssertionError(f"URL sem rota de teste: {url}")
    return get


def test_sidra_parse_populacao():
    dados = [
        CABECALHO_SIDRA,
        {"NC": "6", "V": "23167", "D1C": "1100015", "D3C": "2018"},
        {"NC": "6", "V": "...", "D1C": "5101837", "D3C": "2018"},
    ]
    with patch("src.ibge.requests.get", side_effect=_fake_get({"/t/6579/": dados})):
        df = ibge._sidra_valores("https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/2018")
    assert len(df) == 2
    assert "Município (Código)" not in df["cd_municipio_ibge"].tolist()
    assert df["cd_municipio_ibge"].tolist() == ["1100015", "5101837"]
    assert df["ano"].tolist() == [2018, 2018]
    assert df.loc[0, "valor"] == 23167
    assert pd.isna(df.loc[1, "valor"])


def test_depara_codigos_com_zeros():
    csv = (
        "codigo_tse,uf,nome_municipio,capital,codigo_ibge\n"
        "1120,AC,ACRELANDIA,0,1200013\n"
        "01570,AC,ASSIS BRASIL,0,1200054\n"
    ).encode("utf-8")
    with patch("src.ibge.requests.get", side_effect=_fake_get({"municipios_brasileiros_tse.csv": csv})):
        df = ibge.depara_tse_ibge()
    assert df["cd_municipio_tse"].tolist() == ["01120", "01570"]
    assert df["cd_municipio_ibge"].tolist() == ["1200013", "1200054"]
    assert list(df.columns) == ["cd_municipio_tse", "cd_municipio_ibge"]


def test_municipios_regiao():
    localidades = [
        {"id": 1100015, "nome": "Alta Floresta D'Oeste",
         "microrregiao": {"nome": "Cacoal", "mesorregiao": {"UF": {
             "sigla": "RO", "regiao": {"nome": "Norte"}}}},
         "regiao-imediata": None},
        {"id": 5101837, "nome": "Boa Esperança do Norte", "microrregiao": None,
         "regiao-imediata": {"regiao-intermediaria": {"UF": {
             "sigla": "MT", "regiao": {"nome": "Centro-Oeste"}}}}},
    ]
    with patch("src.ibge.requests.get", side_effect=_fake_get({"localidades/municipios": localidades})):
        df = ibge.municipios_ibge()
    assert df["cd_municipio_ibge"].tolist() == ["1100015", "5101837"]
    assert df["nm_regiao"].tolist() == ["Norte", "Centro-Oeste"]
    assert df["sg_uf"].tolist() == ["RO", "MT"]


def test_municipios_reaproveita_cache():
    localidades = [{"id": 1100015, "nome": "X", "microrregiao": None,
                    "regiao-imediata": {"regiao-intermediaria": {"UF": {
                        "sigla": "RO", "regiao": {"nome": "Norte"}}}}}]
    with patch("src.ibge.requests.get", side_effect=_fake_get({"localidades/municipios": localidades})) as get:
        ibge.municipios_ibge()
        ibge.municipios_ibge()
    assert get.call_count == 1


def test_pib_per_capita():
    assert ibge.calcular_pib_per_capita(1000, 500) == 2000.0


def test_populacao_ano_proximo():
    rotas = {
        "/t/6579/": [CABECALHO_SIDRA,
                     {"V": "100", "D1C": "1100015", "D3C": "2018"},
                     {"V": "120", "D1C": "1100015", "D3C": "2024"}],
        "/t/4709/": [CABECALHO_SIDRA,
                     {"V": "110", "D1C": "1100015", "D3C": "2022"}],
    }
    with patch("src.ibge.requests.get", side_effect=_fake_get(rotas)):
        df = ibge.populacao_municipios([2018, 2023, 2024])
    por_ano = df.set_index("ano")
    assert por_ano.loc[2018, "populacao"] == 100
    assert por_ano.loc[2018, "fonte_populacao"] == "estimativa_6579"
    assert por_ano.loc[2024, "populacao"] == 120
    assert por_ano.loc[2024, "fonte_populacao"] == "estimativa_6579"
    assert por_ano.loc[2023, "populacao"] == 110
    assert por_ano.loc[2023, "fonte_populacao"] == "censo_4709_2022"


def test_pib_ano_eleicao_usa_censo_2022():
    rotas = {
        "/t/5938/": [CABECALHO_SIDRA,
                     {"V": "1000", "D1C": "1100015", "D3C": "2022"},
                     {"V": "1000", "D1C": "1100015", "D3C": "2023"}],
        "/t/6579/": [CABECALHO_SIDRA,
                     {"V": "100", "D1C": "1100015", "D3C": "2018"},
                     {"V": "100", "D1C": "1100015", "D3C": "2020"},
                     {"V": "100", "D1C": "1100015", "D3C": "2024"}],
        "/t/4709/": [CABECALHO_SIDRA,
                     {"V": "500", "D1C": "1100015", "D3C": "2022"}],
    }
    with patch("src.ibge.requests.get", side_effect=_fake_get(rotas)):
        df = ibge.pib_municipios()
    linha_2023 = df[df["ano"] == 2023].iloc[0]
    assert linha_2023["ano_eleicao"] == 2024
    assert linha_2023["pib_per_capita"] == 2000.0
    linha_2022 = df[df["ano"] == 2022].iloc[0]
    assert linha_2022["ano_eleicao"] == 2022
    assert linha_2022["pib_per_capita"] == 2000.0
