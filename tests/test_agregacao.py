"""Testes da agregação de taxas de abstenção."""
import math

import pandas as pd

from src.agregacao import taxa_abstencao


def test_taxa_nao_soma_turnos():
    df = pd.DataFrame({
        "cd_municipio": ["00001", "00001"],
        "nr_turno": [1, 2],
        "qt_aptos": [100, 100],
        "qt_abstencao": [20, 30],
    })
    r = taxa_abstencao(df, ["cd_municipio"])
    assert list(r.columns) == ["cd_municipio", "qt_aptos", "qt_abstencao", "taxa_abstencao"]
    assert len(r) == 1
    assert r.loc[0, "qt_aptos"] == 100
    assert r.loc[0, "taxa_abstencao"] == 0.20


def test_taxa_segundo_turno_e_turno_como_texto():
    df = pd.DataFrame({
        "cd_municipio": ["00001", "00001", "00001"],
        "nr_turno": ["1", "2", "2"],
        "qt_aptos": [100, 60, 40],
        "qt_abstencao": [20, 15, 15],
    })
    r = taxa_abstencao(df, ["cd_municipio"], turno=2)
    assert r.loc[0, "qt_aptos"] == 100
    assert r.loc[0, "taxa_abstencao"] == 0.30


def test_taxa_ignora_aptos_zero():
    df = pd.DataFrame({
        "cd_municipio": ["00001", "00002"],
        "nr_turno": [1, 1],
        "qt_aptos": [0, 50],
        "qt_abstencao": [0, 5],
    })
    r = taxa_abstencao(df, ["cd_municipio"]).set_index("cd_municipio")
    assert math.isnan(r.loc["00001", "taxa_abstencao"])
    assert r.loc["00002", "taxa_abstencao"] == 0.10


# ---------------------------------------------------------------- camada gold
from src import agregacao as ag  # noqa: E402

PADRAO_MUN = dict(
    ano=2022, nr_turno=1, sg_uf="SP", cd_municipio_ibge="3500001", nm_municipio="MUNICIPIO",
    nm_regiao="Sudeste", tipo_eleicao="geral", exterior=False, populacao=10_000,
    fonte_populacao="IBGE", pib_per_capita=10.0, aptos_16_17=0, aptos_70_mais=0,
    aptos_superior=0,
)


def _pre_mun(linhas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{**PADRAO_MUN, **linha} for linha in linhas])


def test_taxa_100k():
    pre = _pre_mun([{"cd_municipio": "00001", "qt_aptos": 100, "qt_abstencao": 50,
                     "populacao": 10_000}])
    r = ag._calc_municipio_ano(pre)
    assert r.loc[0, "abstencoes_por_100k_hab"] == 500.0


def test_outlier_iqr_marca_extremo():
    taxas = [0.20, 0.21, 0.19, 0.20, 0.22, 0.60]
    linhas = [{"cd_municipio": f"0000{i}", "qt_aptos": 1000, "qt_abstencao": round(t * 1000)}
              for i, t in enumerate(taxas, start=1)]
    linhas.append({"cd_municipio": "ZZ", "sg_uf": "ZZ", "exterior": True, "nm_regiao": None,
                   "cd_municipio_ibge": None, "qt_aptos": 1000, "qt_abstencao": 590})
    r = ag._calc_municipio_ano(_pre_mun(linhas)).set_index("cd_municipio")
    internos = r.drop(index="ZZ")
    assert list(internos.index[internos["outlier_iqr"].astype(bool)]) == ["00006"]
    assert pd.isna(r.loc["ZZ", "outlier_iqr"])


def test_municipio_nao_soma_populacao():
    pre = _pre_mun([
        {"cd_municipio": "00001", "qt_aptos": 500, "qt_abstencao": 50, "populacao": 1000},
        {"cd_municipio": "00001", "qt_aptos": 500, "qt_abstencao": 100, "populacao": 1000},
    ])
    r = ag._calc_municipio_ano(pre)
    assert len(r) == 1
    assert r.loc[0, "populacao"] == 1000
    assert r.loc[0, "qt_aptos"] == 1000
    assert r.loc[0, "taxa_abstencao"] == 0.15


def test_turnos_mesmo_conjunto_de_municipios():
    base = dict(ano=2020, sg_uf="SP", tipo_eleicao="municipal", exterior=False)
    pre = pd.DataFrame([
        {**base, "nr_turno": 1, "cd_municipio": "00001", "tem_2o_turno": True,
         "qt_aptos": 100, "qt_abstencao": 20},
        {**base, "nr_turno": 2, "cd_municipio": "00001", "tem_2o_turno": True,
         "qt_aptos": 100, "qt_abstencao": 30},
        {**base, "nr_turno": 1, "cd_municipio": "00002", "tem_2o_turno": False,
         "qt_aptos": 100, "qt_abstencao": 10},
    ])
    r = ag._calc_turnos(pre)
    com = r[r["conjunto"] == "com_2o_turno"].set_index("nr_turno")
    assert com.loc[1, "qt_aptos"] == 100 and com.loc[1, "taxa_abstencao"] == 0.20
    assert com.loc[2, "qt_aptos"] == 100 and com.loc[2, "taxa_abstencao"] == 0.30
    todos = r[r["conjunto"] == "todos"]
    assert list(todos["nr_turno"]) == [1]
    assert todos["qt_aptos"].iloc[0] == 200 and todos["taxa_abstencao"].iloc[0] == 0.15


def test_perfil_mantem_rotulo_nulo():
    pre = pd.DataFrame([
        {"ano": 2024, "nr_turno": 1, "sg_uf": "SP", "cd_municipio": "00001",
         "faixa_etaria_agrupada": None, "grupo_idade": None, "ds_grau_escolaridade": "SUPERIOR COMPLETO",
         "ds_genero": "FEMININO", "exterior": False, "qt_aptos": 10, "qt_abstencao": 4},
        {"ano": 2024, "nr_turno": 1, "sg_uf": "SP", "cd_municipio": "00002",
         "faixa_etaria_agrupada": "16–17", "grupo_idade": "16–17", "ds_grau_escolaridade": "SUPERIOR COMPLETO",
         "ds_genero": "FEMININO", "exterior": False, "qt_aptos": 10, "qt_abstencao": 1},
    ])
    r = ag._calc_perfil_ano(pre)
    assert len(r) == 2
    assert r["grupo_idade"].notna().all()
    assert (r["grupo_idade"] == "NÃO INFORMADO").sum() == 1
