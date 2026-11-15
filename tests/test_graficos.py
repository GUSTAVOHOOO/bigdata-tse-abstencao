"""Testes das funções puras que calculam os números dos títulos das figuras (src/graficos.py)."""
import pandas as pd
import pytest

import src.graficos as gr


def test_taxa_agregada_soma_contagens_antes_de_dividir():
    # Média das taxas daria (0,10 + 0,333) / 2 = 0,2167; a taxa certa pondera pelos aptos.
    df = pd.DataFrame({"qt_aptos": [100, 900], "qt_abstencao": [10, 300]})
    assert gr.taxa_agregada(df) == pytest.approx(0.31)

    por_grupo = gr.taxas_por(df.assign(g=["a", "b"]), ["g"]).set_index("g")["taxa"]
    assert por_grupo["a"] == pytest.approx(0.10)
    assert por_grupo["b"] == pytest.approx(1 / 3)


def test_resumo_mudanca_uf_conta_altas_e_extremos_em_pontos_percentuais():
    uf = pd.DataFrame({
        "ano": [2018, 2022, 2018, 2022, 2018, 2022],
        "sg_uf": ["AC", "AC", "BA", "BA", "SP", "SP"],
        "taxa_abstencao": [0.10, 0.13, 0.20, 0.19, 0.25, 0.25],
    })
    r = gr.resumo_mudanca_uf(uf, 2018, 2022)

    assert r["ufs"] == 3
    assert r["subiram"] == 1  # só o AC subiu; SP ficou igual
    assert r["maior_alta_uf"] == "AC" and r["maior_alta_pp"] == pytest.approx(3.0)
    assert r["maior_queda_uf"] == "BA" and r["maior_queda_pp"] == pytest.approx(-1.0)


def test_etapas_de_linhas_fecham_bronze_menos_etapas_igual_a_silver():
    log = pd.DataFrame({
        "problema": ["#2 chave", "#4 colunas", "#8 tipos", "#7 par"],
        "unidade": ["linhas", "linhas", "linhas", "linhas"],
        "linhas_antes": [1000, 900, 700, 700],
        "linhas_depois": [900, 700, 700, 700],
    })
    e = gr.etapas_de_linhas(log)
    assert e["bronze"] == 1000 and e["silver"] == 700
    assert e["etapas"] == [("#2 chave", 100), ("#4 colunas", 200)]

    # Log que não fecha (1000 − 100 − 250 = 650, mas a última etapa termina em 700) deve falhar.
    log_ruim = log.copy()
    log_ruim.loc[1, ["linhas_antes", "linhas_depois"]] = [950, 700]
    with pytest.raises(AssertionError):
        gr.etapas_de_linhas(log_ruim)
