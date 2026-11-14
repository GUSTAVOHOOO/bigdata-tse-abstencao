"""Testes das funções de limpeza, integração IBGE e camada silver."""
import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.config import ANOS
from src.limpeza import (
    DATAS_TURNO,
    LogLimpeza,
    agregar_por_chave,
    derivar,
    harmonizar_anos,
    integrar_ibge,
    marcar_inconsistentes,
    padronizar_colunas,
    remover_perfil_2024,
    salvar_silver,
    tipar,
    tratar_sentinelas,
    valores_ausentes,
)


def _celula(**kw) -> dict:
    """Linha mínima já em snake_case e tipada, com valores padrão sobrescrevíveis."""
    base = {
        "ano": 2022, "nr_turno": 1, "sg_uf": "MG", "cd_municipio": "40134", "nr_zona": 1,
        "cd_genero": 2, "cd_estado_civil": 1, "cd_faixa_etaria": 3034, "cd_grau_escolaridade": 6,
        "qt_aptos": 10, "qt_comparecimento": 8, "qt_abstencao": 2,
    }
    base.update(kw)
    return base


def test_log_calcula_afetadas_e_acumula(tmp_path):
    log = LogLimpeza()
    log.registrar("#2 chave", "agregar", "porque sim", antes=10, depois=7)
    log.registrar("#2 chave", "agregar", "porque sim", antes=5, depois=5)
    log.registrar("#5 sentinelas", "nulo", "LEIAME", antes=5, depois=5, afetadas=3, unidade="celulas")
    df = log.tabela()
    assert list(df.columns) == ["problema", "decisao", "justificativa", "unidade",
                                "linhas_antes", "linhas_depois", "linhas_afetadas"]
    assert df.set_index("problema")["unidade"].to_dict() == {"#2 chave": "linhas", "#5 sentinelas": "celulas"}
    assert df.set_index("problema").loc["#2 chave", "linhas_afetadas"] == 3
    assert df.set_index("problema").loc["#2 chave", "linhas_antes"] == 15
    assert df.set_index("problema").loc["#5 sentinelas", "linhas_afetadas"] == 3
    log.salvar(tmp_path / "log.csv")
    assert len(pd.read_csv(tmp_path / "log.csv")) == 2
    with pytest.raises(ValueError):
        log.registrar("#9", "x", "y", antes=1, depois=1, unidade="metros")


def test_snake_case_sem_acento():
    df = pd.DataFrame(columns=["DS_GRAU_ESCOLARIDADE", "Nº Seção"])
    assert list(padronizar_colunas(df).columns) == ["ds_grau_escolaridade", "no_secao"]


def test_sentinelas_viram_nulo():
    df = pd.DataFrame({
        "cd_faixa_etaria": ["#NULO#", "#NE#", "-3", "0", "3034"],
        "qt_aptos": ["-1", "0", "5", "7", "9"],
    })
    r = tratar_sentinelas(df, LogLimpeza())
    assert r["cd_faixa_etaria"].isna().tolist() == [True, True, True, False, False]
    assert r.loc[3, "cd_faixa_etaria"] == "0"  # "0" não é sentinela nesta coluna
    assert r["qt_aptos"].tolist() == ["-1", "0", "5", "7", "9"]  # qt_* nunca é tocada


def test_codigo_zero_nas_dimensoes_vira_nulo_e_rotulo_unico():
    df = pd.DataFrame({
        "cd_genero": ["0", "2"], "ds_genero": ["NÃO INFORMADO", "MASCULINO"],
        "cd_faixa_etaria": ["-3", "1600"], "ds_faixa_etaria": ["Inválido", "16 anos"],
    })
    log = LogLimpeza()
    r = tratar_sentinelas(df, log)
    assert r["cd_genero"].isna().tolist() == [True, False]
    assert r["ds_genero"].tolist() == ["NÃO INFORMADO", "MASCULINO"]
    assert r["ds_faixa_etaria"].tolist() == ["NÃO INFORMADO", "16 anos"]
    t = log.tabela()
    assert t["unidade"].tolist() == ["celulas"]
    assert t["linhas_afetadas"].sum() == 2  # duas células de código anuladas
    assert t["linhas_antes"].sum() == 4  # 2 linhas × 2 colunas cd_* examinadas


def test_valores_ausentes_compartilhados():
    assert "0" in valores_ausentes("cd_genero") and "0" not in valores_ausentes("cd_faixa_etaria")
    assert "Inválido" in valores_ausentes("ds_faixa_etaria")
    assert {"#NULO#", "-1", "-3", "NÃO INFORMADO"} <= valores_ausentes("cd_cor_raca")


def test_harmonizar_rotulos_maiusculos():
    df = pd.DataFrame({"ds_faixa_etaria": ["16 anos", "21 a 24 anos ", "100 anos ou mais"],
                       "ds_genero": ["MASCULINO", "FEMININO", "FEMININO"]})
    log = LogLimpeza()
    r = harmonizar_anos(df, log)
    assert r["ds_faixa_etaria"].tolist() == ["16 ANOS", "21 A 24 ANOS", "100 ANOS OU MAIS"]
    t = log.tabela()
    assert t["linhas_afetadas"].sum() == 3 and t["unidade"].tolist() == ["celulas"]
    assert t["linhas_antes"].sum() == 6  # 3 linhas × 2 colunas ds_*


def test_tipar():
    df = pd.DataFrame({
        "ano": [2022], "nr_turno": ["1"], "sg_uf": ["MG"], "cd_municipio": ["40134"], "nr_zona": ["12"],
        "cd_genero": [None], "ds_genero": ["NÃO INFORMADO"], "cd_faixa_etaria": ["3034"],
        "qt_aptos": ["10"], "dt_geracao": ["29/04/2025"],
    })
    r = tipar(df)
    assert r["qt_aptos"].dtype == "int32"
    assert r["ano"].dtype == "int16" and r["nr_turno"].dtype == "int8"
    assert r["cd_genero"].dtype == "Int8" and r["cd_genero"].isna().all()
    assert r["cd_faixa_etaria"].dtype == "Int16"
    assert r["cd_municipio"].iloc[0] == "40134"
    assert isinstance(r["ds_genero"].dtype, pd.CategoricalDtype)
    assert pd.api.types.is_datetime64_any_dtype(r["dt_geracao"])


def test_agregar_por_chave_preserva_totais():
    df = pd.DataFrame([_celula(qt_aptos=1, qt_comparecimento=1, qt_abstencao=0),
                       _celula(qt_aptos=4, qt_comparecimento=3, qt_abstencao=1),
                       _celula(cd_genero=4)])
    log = LogLimpeza()
    r = agregar_por_chave(df, log)
    assert len(r) == 2
    assert r["qt_aptos"].sum() == df["qt_aptos"].sum()
    assert r.loc[r.cd_genero == 2, "qt_aptos"].item() == 5
    assert log.tabela()["linhas_afetadas"].tolist() == [1]


def test_agregar_mantem_chave_nula_como_grupo():
    df = pd.DataFrame([_celula(cd_genero=pd.NA), _celula(cd_genero=pd.NA)]).astype({"cd_genero": "Int8"})
    r = agregar_por_chave(df, LogLimpeza())
    assert len(r) == 1 and r["qt_aptos"].item() == 20 and pd.isna(r["cd_genero"].item())


def test_remover_perfil_2024_reagrega():
    df = pd.DataFrame([_celula(ano=2024, cd_cor_raca=1), _celula(ano=2024, cd_cor_raca=3)])
    df["ds_cor_raca"] = ["BRANCA", "PARDA"]
    log = LogLimpeza()
    r = remover_perfil_2024(df, log)
    assert "cd_cor_raca" not in r.columns and "ds_cor_raca" not in r.columns
    assert len(r) == 1 and r["qt_aptos"].item() == 20
    assert log.tabela()["linhas_afetadas"].tolist() == [1]


@pytest.mark.parametrize("faixa, escolaridade, esperado", [
    (1600, 6, True),   # 16 anos
    (7074, 6, True),   # 72 anos cai na faixa 70 a 74
    (3034, 6, False),  # 30 anos, ensino médio completo
    (3034, 1, True),   # 30 anos, analfabeto (CF art. 14, § 1º, II)
])
def test_faixa_facultativa(faixa, escolaridade, esperado):
    df = pd.DataFrame([_celula(cd_faixa_etaria=faixa, cd_grau_escolaridade=escolaridade)])
    r = derivar(df)
    assert bool(r["voto_facultativo"].iloc[0]) is esperado


def test_derivar_grupos_e_regiao():
    df = pd.DataFrame([_celula(cd_faixa_etaria=1700), _celula(cd_faixa_etaria=4549, nr_turno=2),
                       _celula(cd_faixa_etaria=9999, sg_uf="ZZ", cd_municipio="29998")])
    r = derivar(df)
    assert r["grupo_idade"].astype(str).tolist() == ["16–17", "18–69", "70+"]
    assert r["faixa_etaria_agrupada"].astype(str).tolist() == ["16–17", "45–59", "70+"]
    assert r["nm_regiao"].tolist()[:2] == ["Sudeste", "Sudeste"] and pd.isna(r["nm_regiao"].iloc[2])
    assert r["exterior"].tolist() == [False, False, True]
    assert r["tipo_eleicao"].unique().tolist() == ["geral"]
    assert r["tem_2o_turno"].tolist() == [True, True, False]


def test_data_turno_e_mes_ano():
    df = pd.DataFrame([_celula(ano=2020, nr_turno=1), _celula(ano=2020, nr_turno=2),
                       _celula(ano=2018, nr_turno=2), _celula(ano=2024, nr_turno=1)])
    r = derivar(df)
    assert r["data_turno"].dt.strftime("%Y-%m-%d").tolist() == ["2020-11-15", "2020-11-29",
                                                                 "2018-10-28", "2024-10-06"]
    assert r["mes_ano"].astype(str).tolist() == ["2020-11", "2020-11", "2018-10", "2024-10"]


def test_datas_turno_cobrem_todos_os_anos():
    assert sorted(DATAS_TURNO) == ANOS
    assert all(set(t) == {1, 2} and t[1] < t[2] for t in DATAS_TURNO.values())


def test_marcar_inconsistentes_e_implausiveis():
    df = pd.DataFrame([_celula(), _celula(qt_abstencao=5),
                       _celula(cd_faixa_etaria=1700, cd_grau_escolaridade=8)])
    log = LogLimpeza()
    r = marcar_inconsistentes(df, log)
    assert len(r) == 3
    assert r["inconsistente"].tolist() == [False, True, False]
    assert r["perfil_implausivel"].tolist() == [False, False, True]


def test_integracao_conta_nao_casados():
    df = pd.DataFrame([_celula(sg_uf="ZZ", cd_municipio="29998")])
    depara = pd.DataFrame({"cd_municipio_tse": ["40134"], "cd_municipio_ibge": ["3106200"]})
    populacao = pd.DataFrame({"cd_municipio_ibge": ["3106200"], "ano": [2022], "populacao": [100],
                              "fonte_populacao": ["censo_4709"]})
    pib = pd.DataFrame({"cd_municipio_ibge": ["3106200"], "ano": [2022], "pib_mil_reais": [1.0],
                        "pib_per_capita": [10.0], "ano_eleicao": [2022]})
    log = LogLimpeza()
    r = integrar_ibge(df, log, depara=depara, populacao=populacao, pib=pib)
    assert len(r) == 1 and pd.isna(r["cd_municipio_ibge"].iloc[0])
    nao_casados = log.tabela().set_index("problema").filter(like="depois da junção", axis=0)
    assert nao_casados["linhas_afetadas"].tolist() == [1]
    assert nao_casados["linhas_depois"].tolist() == [1]  # medido na tabela juntada


def test_integracao_par_acrescentado_e_variaveis():
    df = pd.DataFrame([_celula(ano=2024, sg_uf="MT", cd_municipio="73709"), _celula()])
    depara = pd.DataFrame({"cd_municipio_tse": ["40134"], "cd_municipio_ibge": ["3106200"]})
    populacao = pd.DataFrame({"cd_municipio_ibge": ["3106200"], "ano": [2022], "populacao": [100],
                              "fonte_populacao": ["censo_4709"]})
    pib = pd.DataFrame({"cd_municipio_ibge": ["3106200"], "ano": [2022], "pib_mil_reais": [1.0],
                        "pib_per_capita": [10.0], "ano_eleicao": [2022]})
    r = integrar_ibge(df, LogLimpeza(), depara=depara, populacao=populacao, pib=pib)
    assert r["cd_municipio_ibge"].tolist() == ["5101837", "3106200"]
    assert r.loc[1, "populacao"] == 100 and r.loc[1, "ano_pib"] == 2022
    assert pd.isna(r.loc[0, "populacao"])


def test_salvar_silver_particiona_e_substitui(tmp_path):
    df = derivar(pd.DataFrame([_celula(), _celula(sg_uf="SP", cd_municipio="71072")]))
    salvar_silver(df, raiz=tmp_path)
    salvar_silver(df, raiz=tmp_path)  # idempotente: não duplica arquivos
    arquivos = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.parquet"))
    assert arquivos == ["ano=2022/sg_uf=MG/parte-0.parquet", "ano=2022/sg_uf=SP/parte-0.parquet"]
    t = pq.read_table(tmp_path / "ano=2022" / "sg_uf=MG" / "parte-0.parquet")
    assert "ano" not in t.column_names and t.num_rows == 1
