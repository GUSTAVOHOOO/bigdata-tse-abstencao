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
