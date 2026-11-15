"""Limpeza da bronze do TSE, integração com o IBGE e gravação da camada silver.

O pipeline roda uma partição (ano × UF) por vez: a chave completa da linha inclui a UF,
então agregar dentro de cada UF dá o mesmo resultado que agregar o ano inteiro, e a maior
partição (SP 2024, 1,7 milhão de linhas) cabe folgada na memória.

Ordem por partição (`limpar_particao`):
    padronizar_colunas -> tratar_sentinelas -> harmonizar_anos -> tipar -> remover_redundantes
    -> agregar_por_chave -> remover_perfil_2024 -> derivar -> marcar_inconsistentes -> integrar_ibge

Cada etapa registra no `LogLimpeza` o problema da EDA que trata (numerado como na lista
priorizada da seção 2.6 do notebook) e as linhas antes/depois. Execução completa:
    python -m src.limpeza [--anos 2018 2022]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

if __package__ in (None, ""):  # execução direta: src/limpeza.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.dataset as ds  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from src.config import ANOS, REPORTS, SENTINELAS, SILVER  # noqa: E402

SILVER_TSE = SILVER / "tse"
LOG_PATH = REPORTS / "log_limpeza.csv"
AUSENTES_PATH = REPORTS / "ausentes_antes_depois.csv"
METADADOS_PATH = SILVER / "tse_metadados.json"

NAO_INFORMADO = "NÃO INFORMADO"
COLUNAS_LOG = ["problema", "decisao", "justificativa", "unidade", "linhas_antes", "linhas_depois",
               "linhas_afetadas"]
UNIDADES = ("linhas", "celulas")

# Dimensões de perfil que só têm valor informado em 2024 (EDA, item 4).
PERFIL_2024 = ["cor_raca", "quilombola", "interprete_libras", "identidade_genero",
               "idioma_indigena", "grupo_indigena"]
COLUNAS_2024 = [f"{p}_{v}" for v in PERFIL_2024 for p in ("cd", "ds")]
# Código 0 = não informado, fora do LEIAME (EDA, item 5).
CODIGO_ZERO = "0"
CODIGO_ZERO_SENTINELA = {"cd_genero", "cd_estado_civil", "cd_grau_escolaridade"}
# Rótulos que acompanham um código sentinela e não estão em SENTINELAS (faixa -3 = "Inválido").
ROTULOS_SENTINELA = {"ds_faixa_etaria": {"Inválido"}}
ANALFABETO = 1  # cd_grau_escolaridade (dicionário de dados)
SUPERIOR_COMPLETO = 8
# Par ausente do de-para: mesmo nome e UF no TSE 2024 e na API de localidades do IBGE (EDA, item 7).
DEPARA_EXTRA = {"73709": "5101837"}  # Boa Esperança do Norte (MT)

TIPOS_CODIGO = {
    "cd_genero": "Int8", "cd_estado_civil": "Int8", "cd_faixa_etaria": "Int16",
    "cd_grau_escolaridade": "Int8", "cd_cor_raca": "Int8", "cd_quilombola": "Int8",
    "cd_interprete_libras": "Int8", "cd_identidade_genero": "Int8", "cd_idioma_indigena": "Int8",
    "cd_grupo_indigena": "Int32",
}
CHAVE_BASE = ["ano", "nr_turno", "sg_uf", "cd_municipio", "nr_zona"]

REGIAO_UF = {
    **dict.fromkeys(["AC", "AM", "AP", "PA", "RO", "RR", "TO"], "Norte"),
    **dict.fromkeys(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"], "Nordeste"),
    **dict.fromkeys(["DF", "GO", "MS", "MT"], "Centro-Oeste"),
    **dict.fromkeys(["ES", "MG", "RJ", "SP"], "Sudeste"),
    **dict.fromkeys(["PR", "RS", "SC"], "Sul"),
}
# Datas oficiais dos turnos (calendários eleitorais do TSE). Em 2020 a eleição foi adiada de outubro
# para novembro pela Emenda Constitucional 107/2020, por causa da pandemia de covid-19.
DATAS_TURNO: dict[int, dict[int, date]] = {
    2018: {1: date(2018, 10, 7), 2: date(2018, 10, 28)},
    2020: {1: date(2020, 11, 15), 2: date(2020, 11, 29)},
    2022: {1: date(2022, 10, 2), 2: date(2022, 10, 30)},
    2024: {1: date(2024, 10, 6), 2: date(2024, 10, 27)},
}
FAIXAS_AGRUPADAS = ["16–17", "18–24", "25–34", "35–44", "45–59", "60–69", "70+"]
GRUPOS_IDADE = ["16–17", "18–69", "70+"]

# Texto do log: (problema, decisão, justificativa, unidade). Passou pela revisão de estilo (humanizer).
# unidade "linhas": linhas_antes/depois/afetadas contam linhas; "celulas": contam células das colunas
# examinadas (linhas × colunas). Etapas que não removem nem marcam registram 0 afetadas.
TEXTOS = {
    "1": ("#1 Eleitorado repetido entre turnos",
          "Manter nr_turno e criar tem_2o_turno (município teve 2º turno no ano). Toda taxa é calculada dentro de um turno.",
          "Nas gerais o 2º turno repete os aptos do 1º em todos os municípios (147.306.275 em 2018). "
          "Somar aptos entre turnos dobraria o denominador. Afetadas = linhas marcadas com tem_2o_turno.",
          "linhas"),
    "2": ("#2 Chave da linha não é única (células partidas)",
          "Somar todas as qt_* pela chave completa (ano, turno, UF, município, zona e códigos de perfil). Nenhum duplicado é apagado.",
          "Os 1.979 duplicados exatos da EDA são pedaços de uma mesma célula, quase sempre com 1 eleitor. "
          "Apagá-los tiraria eleitores reais; somar devolve uma linha por chave com os mesmos totais. "
          "Afetadas = linhas absorvidas pela soma.",
          "linhas"),
    "3": ("#3 Exterior (ZZ) misturado aos municípios",
          "Criar a coluna exterior e manter as linhas na silver, sem código IBGE e sem região.",
          "Abstenção de 59,1% (2018) e 51,7% (2022) contra cerca de 20% no país. Fica no total nacional e sai das "
          "análises por município, UF e IBGE. Afetadas = linhas marcadas como exterior.",
          "linhas"),
    "4a": ("#4 Colunas de perfil que só existem em 2024 (-1 vira nulo)",
           "Converter o código -1 em nulo nas seis dimensões de 2024, em vez de tratá-lo como uma categoria. "
           "Afetadas = células de código anuladas, sobre as células das seis colunas.",
           "O LEIAME usa -1 para não informado, e em 2018–2022 essas colunas trazem -1 em todas as linhas. "
           "Viés: em 2024 só 10,2% dos aptos declararam cor/raça, e eles se abstêm menos (16,6% contra 22,3% dos "
           "que não declararam). Uma taxa por cor/raça feita só com os informados descreve esse grupo menor e "
           "não o eleitorado.",
           "celulas"),
    "4b": ("#4 Colunas de perfil que só existem em 2024 (remoção e reagregação)",
           "Tirar da silver as 12 colunas de cor/raça, quilombola, Libras, identidade de gênero, idioma e grupo indígena e reagregar pela chave comum aos quatro anos.",
           "Não há série histórica: cor/raça não é informada para 89,8% dos aptos de 2024. As colunas partem as "
           "células (as de 1 eleitor passam de 24% para 44%) e impedem uma chave comum entre os anos. "
           "Viés: a silver não permite analisar 2024 por cor/raça, quilombolas, Libras, identidade de gênero ou "
           "povos indígenas. Quem precisar disso volta à bronze de 2024, sabendo que o resultado vale para os "
           "10% de aptos que declararam. Afetadas = linhas absorvidas pela reagregação.",
           "linhas"),
    "5": ("#5 Sentinelas nas dimensões de perfil (código 0 e faixa -3)",
          "Código 0 em gênero, estado civil e escolaridade e faixa -3 viram nulo no cd_*; o ds_* recebe o rótulo "
          "único NÃO INFORMADO. As linhas ficam nos totais e saem das análises por perfil. Afetadas = células de "
          "código anuladas, sobre as células das quatro dimensões.",
          "O código 0 não consta no LEIAME e a faixa -3 é idade inválida. Somam no máximo 0,065% dos aptos por ano. "
          "Viés: esses eleitores se abstêm muito mais que os demais (38% a 59% no 1º turno, contra 20% a 23%), então "
          "as taxas por gênero, estado civil, escolaridade e idade descrevem os cadastros completos e ficam um pouco "
          "abaixo da taxa geral. Pelo tamanho do grupo, a diferença é de no máximo 0,02 ponto percentual.",
          "celulas"),
    "6": ("#6 Abstenção muito alta nas faixas mais velhas (cadastro desatualizado?)",
          "Manter os dados oficiais e criar grupo_idade (16–17, 18–69, 70+) e faixa_etaria_agrupada. Afetadas = "
          "linhas de 90 anos ou mais, o conjunto que a análise de sensibilidade exclui (nenhum valor muda).",
          "Abstenção de 88% a 95% aos 90–94 anos e acima de 96% a partir dos 95. O voto facultativo explica parte; "
          "a hipótese de cadastro desatualizado não foi testada e entra como limitação.",
          "linhas"),
    "7a": ("#7 Município sem par no de-para TSE → IBGE (par acrescentado)",
           "Acrescentar o par 73709 → 5101837 (Boa Esperança do Norte, MT). Afetadas = linhas casadas só por esse par.",
           "Mesmo nome e mesma UF no arquivo do TSE de 2024 e na API de localidades do IBGE "
           "(servicodados.ibge.gov.br/api/v1/localidades/municipios). O IBGE ainda não publica população nem PIB do município.",
           "linhas"),
    "7b": ("#7 Linhas sem par no IBGE depois da junção",
           "Manter as linhas com cd_municipio_ibge nulo e contá-las. linhas_depois é medido na tabela já juntada. "
           "Afetadas = linhas sem código IBGE.",
           "Na execução de referência sobraram só as linhas do exterior (ZZ), que não têm município no IBGE. "
           "As junções usam apenas o código.",
           "linhas"),
    "8": ("#8 Todas as colunas em texto",
          "Renomear para snake_case e tipar: qt_* int32, códigos Int8/Int16, nr_zona int16, ds_*, sg_uf e nome do "
          "município category, cd_municipio texto de 5 caracteres. Afetadas = 0: a conversão muda o tipo das 43 "
          "colunas, sem remover linhas nem mudar valores.",
          "A base em texto ocuparia 85,6 GB no pandas contra 9,0 GB tipada, e a máquina tem 15,4 GB de RAM. "
          "Tipar também evita comparar '08' com '8'. A conversão não perdeu valor em nenhuma linha.",
          "linhas"),
    "9": ("#9 Falta o tipo de eleição; colunas redundantes",
          "Derivar tipo_eleicao (geral em 2018 e 2022, municipal em 2020 e 2024). Descartar ano_eleicao depois de "
          "conferir que é igual à partição e levar dt_geracao e hh_geracao para tse_metadados.json. Afetadas = 0: "
          "a etapa acrescenta uma coluna e tira três, sem mudar linhas.",
          "As perguntas 1 e 4 comparam eleições gerais e municipais. ano_eleicao repete a partição em 100% das linhas "
          "e a data de geração tem um valor por ano.",
          "linhas"),
    "10": ("#10 Rótulos em forma inconsistente",
           "Passar os ds_* para maiúsculas e tirar espaços extras. Junções só por código. Afetadas = células de "
           "rótulo alteradas, sobre as células de todas as colunas ds_*.",
           "A faixa etária vinha em minúsculas (\"16 anos\") e as colunas de 2024 misturavam caixa. "
           "Há 5.751 códigos de município para 5.466 nomes, então juntar por nome trocaria homônimos.",
           "celulas"),
    "11": ("#11 Municípios com abstenção extrema",
           "Não remover. A marca outlier_iqr é por município e ano, no 1º turno, e não cabe no grão da silver (célula de perfil): será calculada na camada gold (Task 8).",
           "A EDA achou 21, 4, 63 e 22 outliers pelo IQR, concentrados no Jequitinhonha (MG) e no interior do AM. "
           "São casos reais (emigração, distância) e o objeto da análise. Nenhuma linha muda nesta etapa.",
           "linhas"),
    "12": ("#12 Combinações implausíveis de perfil",
           "Manter e marcar perfil_implausivel (16–17 anos com superior completo). A escolaridade não é corrigida.",
           "A EDA contou 246, 128, 1.074 e 159 linhas. Não há fonte para corrigir o valor e o peso nas taxas é pequeno. "
           "Afetadas = linhas marcadas.",
           "linhas"),
    "13": ("#13 Variáveis do IBGE de fontes diferentes",
           "Guardar fonte_populacao e ano_pib em cada linha integrada. Usar log10 e Spearman nas correlações. "
           "Afetadas = linhas com população do Censo ou PIB de outro ano (nenhum valor muda).",
           "A população de 2022 vem do Censo e a dos outros anos da estimativa; o PIB de 2024 é o de 2023. "
           "O PIB per capita chega a R$ 842 mil, com distribuição muito assimétrica.",
           "linhas"),
    "facultativo": ("(derivação) voto_facultativo sem idade ou escolaridade",
                    "voto_facultativo = 16–17 anos, 70 anos ou mais ou analfabeto (CF, art. 14, § 1º, II). Fica nulo "
                    "quando a idade ou a escolaridade é desconhecida e a regra não decide. Afetadas = linhas com "
                    "voto_facultativo nulo.",
                    "São 11 mil a 34 mil aptos por ano (0,007% a 0,023%), quase todos com escolaridade não informada. "
                    "O TSE conta todos como obrigatórios. Viés: um analfabeto sem escolaridade registrada seria "
                    "facultativo e entra como obrigatório na conta do TSE, o que subestima um pouco os facultativos. "
                    "O grupo se abstém de 15% a 19%, perto dos obrigatórios, e somá-lo a eles não muda a taxa dos "
                    "obrigatórios na segunda casa decimal.",
                    "linhas"),
    "mes_ano": ("(derivação) Mês e ano da eleição",
                "Criar data_turno (data oficial de cada turno no calendário do TSE) e mes_ano (AAAA-MM). Afetadas = 0: "
                "as colunas novas não mudam linhas.",
                "As perguntas comparam anos e tipos de eleição, e a data situa cada turno. Em 2020 a eleição foi em "
                "novembro (15 e 29), adiada pela Emenda Constitucional 107/2020 por causa da pandemia; nos outros "
                "anos foi em outubro.",
                "linhas"),
    "taxa_100k": ("(derivação) Abstenções por 100 mil habitantes",
                  "Não calcular na silver. A gold calcula abstencoes_por_100k_hab por município, ano e turno.",
                  "A taxa usa a população do município, e a silver tem uma linha por célula de perfil (zona, gênero, "
                  "idade, escolaridade). Dividir a abstenção de uma célula pela população do município inteiro não "
                  "mede nada. A conta só faz sentido depois de somar as células do município. Nenhuma linha muda.",
                  "linhas"),
    "consistencia": ("(validação) Aptos diferente de comparecimento + abstenção",
                     "Marcar inconsistente quando qt_aptos ≠ qt_comparecimento + qt_abstencao, sem remover. "
                     "Afetadas = linhas marcadas.",
                     "Regra contábil do arquivo. A EDA não achou nenhuma violação, e a marca confirma isso na silver.",
                     "linhas"),
}


# --------------------------------------------------------------------------- log
class LogLimpeza:
    """Log de limpeza. Registros com o mesmo problema e decisão se acumulam (somam linhas),
    o que permite registrar partição a partição e obter uma linha por problema no final."""

    def __init__(self) -> None:
        self._linhas: dict[tuple[str, str], dict] = {}
        self.metadados: dict[int, dict] = {}

    def registrar(self, problema: str, decisao: str, justificativa: str, antes: int, depois: int,
                  afetadas: int | None = None, unidade: str = "linhas") -> None:
        """`afetadas` padrão = antes - depois; quando a decisão marca em vez de remover,
        passe a contagem marcada (ou 0, se nada muda). `unidade` diz se antes/depois/afetadas
        contam linhas ou células (linhas × colunas examinadas)."""
        if unidade not in UNIDADES:
            raise ValueError(f"unidade deve ser uma de {UNIDADES}: {unidade!r}")
        afetadas = int(antes) - int(depois) if afetadas is None else int(afetadas)
        chave = (problema, decisao)
        if chave not in self._linhas:
            self._linhas[chave] = {"problema": problema, "decisao": decisao, "justificativa": justificativa,
                                   "unidade": unidade, "linhas_antes": 0, "linhas_depois": 0,
                                   "linhas_afetadas": 0}
        elif self._linhas[chave]["unidade"] != unidade:
            raise ValueError(f"unidade diferente para o mesmo problema: {problema}")
        linha = self._linhas[chave]
        linha["linhas_antes"] += int(antes)
        linha["linhas_depois"] += int(depois)
        linha["linhas_afetadas"] += afetadas

    def _texto(self, chave: str, antes: int, depois: int, afetadas: int | None = None) -> None:
        problema, decisao, justificativa, unidade = TEXTOS[chave]
        self.registrar(problema, decisao, justificativa, antes=antes, depois=depois, afetadas=afetadas,
                       unidade=unidade)

    def tabela(self) -> pd.DataFrame:
        df = pd.DataFrame(list(self._linhas.values()), columns=COLUNAS_LOG)
        ordem = df["problema"].str.extract(r"^#(\d+)", expand=False).astype(float).fillna(99)
        return df.assign(_o=ordem).sort_values("_o", kind="stable").drop(columns="_o").reset_index(drop=True)

    def salvar(self, path: Path = LOG_PATH) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.tabela().to_csv(path, index=False, encoding="utf-8")
        return path


# --------------------------------------------------------------------------- etapas
def _sem_acento(texto: str) -> str:
    texto = texto.replace("º", "o").replace("ª", "a")
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def padronizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Nomes em snake_case, minúsculos e sem acento."""
    def snake(nome: str) -> str:
        nome = _sem_acento(str(nome)).strip().lower()
        return re.sub(r"[^a-z0-9]+", "_", nome).strip("_")
    return df.rename(columns={c: snake(c) for c in df.columns})


def _e_codigo(col: str) -> bool:
    return col.startswith("cd_") and col != "cd_municipio"


def tratar_sentinelas(df: pd.DataFrame, log: LogLimpeza) -> pd.DataFrame:
    """Sentinelas viram nulo nos códigos (cd_*) e o rótulo correspondente (ds_*) vira NÃO INFORMADO.

    `SENTINELAS` vale para todo cd_*/ds_*; o código 0 só é sentinela em gênero, estado civil e
    escolaridade. As colunas qt_* nunca são tocadas.
    """
    df = df.copy()
    anulados = {"4a": 0, "5": 0}
    examinadas = {"4a": 0, "5": 0}  # células (linhas × colunas cd_*) de cada grupo
    for col in [c for c in df.columns if _e_codigo(c)]:
        s = df[col]
        sentinela = s.isin(list(valores_ausentes(col)))
        n = int(sentinela.sum())
        if n:
            df[col] = s.where(~sentinela)
        grupo = "4a" if col in COLUNAS_2024 else "5"
        anulados[grupo] += n
        examinadas[grupo] += len(df)
        ds_col = "ds_" + col[3:]
        if ds_col in df.columns:
            rotulo = df[ds_col]
            trocar = (sentinela | rotulo.isin(valores_ausentes(ds_col))) & rotulo.ne(NAO_INFORMADO)
            if trocar.any():
                rotulo = rotulo.astype(object).where(~trocar, NAO_INFORMADO)
                df[ds_col] = rotulo
    if examinadas["4a"]:
        log._texto("4a", examinadas["4a"], examinadas["4a"], anulados["4a"])
    log._texto("5", examinadas["5"], examinadas["5"], anulados["5"])
    return df


def _normalizar_rotulo(valor):
    if not isinstance(valor, str):
        return valor
    return re.sub(r"\s+", " ", valor).strip().upper()


def harmonizar_anos(df: pd.DataFrame, log: LogLimpeza) -> pd.DataFrame:
    """Rótulos ds_* num vocabulário único para os quatro anos: maiúsculas, sem espaços extras.

    Na bronze os rótulos só diferem na forma (ex.: "16 anos" em minúsculas, "Branca" em 2024);
    a faixa -3 ("Inválido") já virou NÃO INFORMADO em `tratar_sentinelas`.
    """
    df = df.copy()
    alteradas = 0
    for col in [c for c in df.columns if c.startswith("ds_")]:
        s = df[col]
        if isinstance(s.dtype, pd.CategoricalDtype):  # trabalha nas categorias, não nas linhas
            cats = list(s.cat.categories)
            novo = [_normalizar_rotulo(v) for v in cats]
            codigos = s.cat.codes.to_numpy()
            contagem = np.bincount(codigos[codigos >= 0], minlength=len(cats))
            alteradas += int(sum(n for n, a, b in zip(contagem, cats, novo) if a != b))
            df[col] = s.map(dict(zip(cats, novo)))
        else:
            novo = s.map(_normalizar_rotulo)
            alteradas += int((novo.ne(s) & s.notna()).sum())
            df[col] = novo
    celulas = len(df) * sum(c.startswith("ds_") for c in df.columns)
    log._texto("10", celulas, celulas, alteradas)
    return df


def _inteiro(s: pd.Series, dtype: str) -> pd.Series:
    if isinstance(s.dtype, pd.CategoricalDtype):  # converte só as categorias
        valores = pd.to_numeric(pd.Series(s.cat.categories.astype(str))).to_numpy()
        codigos = s.cat.codes.to_numpy()
        saida = pd.array(valores[np.where(codigos >= 0, codigos, 0)], dtype="Int64")
        saida[codigos < 0] = pd.NA
        return pd.Series(saida, index=s.index).astype(dtype)
    return pd.to_numeric(s).astype(dtype)


def tipar(df: pd.DataFrame) -> pd.DataFrame:
    """Tipos alvo do dicionário de dados (conversão sem perda verificada na EDA)."""
    df = df.copy()
    for col in df.columns:
        if col.startswith("qt_"):
            df[col] = _inteiro(df[col], "int32")
        elif col in TIPOS_CODIGO or _e_codigo(col):
            df[col] = _inteiro(df[col], TIPOS_CODIGO.get(col, "Int32"))
        elif col in ("ano", "ano_eleicao"):
            df[col] = _inteiro(df[col], "int16")
        elif col == "nr_turno":
            df[col] = _inteiro(df[col], "int8")
        elif col == "nr_zona":
            df[col] = _inteiro(df[col], "int16")
        elif col == "cd_municipio":
            df[col] = df[col].astype(str).str.zfill(5).astype("string")
        elif col.startswith("ds_") or col in ("sg_uf", "nm_municipio"):
            df[col] = df[col].astype("category")
        elif col == "dt_geracao":
            df[col] = pd.to_datetime(df[col].astype(str), format="%d/%m/%Y")
    return df


def remover_redundantes(df: pd.DataFrame, log: LogLimpeza) -> pd.DataFrame:
    """Confere ano_eleicao = ano e descarta ano_eleicao, dt_geracao e hh_geracao
    (data e hora de geração ficam em `log.metadados`, gravado em tse_metadados.json)."""
    if "ano_eleicao" in df.columns and "ano" in df.columns:
        diferentes = int((df["ano_eleicao"] != df["ano"]).sum())
        if diferentes:
            raise ValueError(f"ano_eleicao difere da partição em {diferentes} linhas")
    if {"ano", "dt_geracao", "hh_geracao"} <= set(df.columns) and len(df):
        for ano, g in df.groupby("ano", observed=True):
            self_meta = log.metadados.setdefault(int(ano), {"dt_geracao": set(), "hh_geracao": set()})
            self_meta["dt_geracao"].update(g["dt_geracao"].dt.strftime("%Y-%m-%d").unique())
            self_meta["hh_geracao"].update(map(str, g["hh_geracao"].unique()))
    return df.drop(columns=[c for c in ("ano_eleicao", "dt_geracao", "hh_geracao") if c in df.columns])


def _somar_por_chave(df: pd.DataFrame) -> pd.DataFrame:
    """Soma qt_* pela chave (CHAVE_BASE + códigos de perfil). Rótulos (ds_*, nm_municipio) vão
    junto na chave: são função do código, então não criam grupos novos. Nulos formam grupo."""
    qt = [c for c in df.columns if c.startswith("qt_")]
    chave = [c for c in df.columns if c not in qt]
    r = df.groupby(chave, dropna=False, observed=True, sort=False, as_index=False)[qt].sum()
    for c in qt:
        r[c] = r[c].astype("int32")
    for c in chave:  # o groupby pode perder o dtype nullable/categórico
        if r[c].dtype != df[c].dtype:
            r[c] = r[c].astype(df[c].dtype)
    return r[list(df.columns)]


def agregar_por_chave(df: pd.DataFrame, log: LogLimpeza) -> pd.DataFrame:
    """Junta as células partidas (EDA, item 2) somando todas as qt_* pela chave completa."""
    r = _somar_por_chave(df)
    log._texto("2", len(df), len(r))
    return r


def remover_perfil_2024(df: pd.DataFrame, log: LogLimpeza) -> pd.DataFrame:
    """Tira as 12 colunas de perfil exclusivas de 2024 e reagrega pela chave comum (EDA, item 4)."""
    cols = [c for c in COLUNAS_2024 if c in df.columns]
    if not cols:
        return df
    r = _somar_por_chave(df.drop(columns=cols))
    log._texto("4b", len(df), len(r))
    return r


def _idade_inicial(faixa: pd.Series) -> pd.Series:
    return pd.to_numeric(faixa, errors="coerce").astype("Int16") // 100


def derivar(df: pd.DataFrame) -> pd.DataFrame:
    """Colunas derivadas: região, faixas e grupos de idade, voto facultativo, tipo de eleição,
    exterior, tem_2o_turno, data_turno (data oficial do turno, DATAS_TURNO) e mes_ano (AAAA-MM).

    voto_facultativo segue a CF, art. 14, § 1º, II: 16–17 anos, 70 anos ou mais, ou analfabeto.
    É booleano nullable: com idade e escolaridade desconhecidas, fica nulo.
    """
    df = df.copy()
    idade = _idade_inicial(df["cd_faixa_etaria"])
    uf = df["sg_uf"].astype(str)
    df["nm_regiao"] = pd.Categorical(uf.map(REGIAO_UF), categories=sorted(set(REGIAO_UF.values())))
    df["exterior"] = uf.eq("ZZ").to_numpy()
    ano = pd.to_numeric(df["ano"])
    df["tipo_eleicao"] = pd.Categorical(np.where(ano.isin([2018, 2022]), "geral", "municipal"),
                                        categories=["geral", "municipal"])
    df["faixa_etaria_agrupada"] = pd.cut(idade.astype("float"), [15, 17, 24, 34, 44, 59, 69, 200],
                                         labels=FAIXAS_AGRUPADAS)
    df["grupo_idade"] = pd.cut(idade.astype("float"), [15, 17, 69, 200], labels=GRUPOS_IDADE)
    idade_fac = ((idade <= 17) | (idade >= 70)).astype("boolean")
    analfabeto = pd.to_numeric(df["cd_grau_escolaridade"]).astype("Int8").eq(ANALFABETO).astype("boolean")
    df["voto_facultativo"] = idade_fac | analfabeto
    turno = pd.to_numeric(df["nr_turno"])
    com_2o = set(zip(ano[turno == 2], df.loc[turno == 2, "cd_municipio"].astype(str)))
    df["tem_2o_turno"] = [(a, m) in com_2o for a, m in zip(ano, df["cd_municipio"].astype(str))]
    datas = {(a, t): pd.Timestamp(d) for a, turnos in DATAS_TURNO.items() for t, d in turnos.items()}
    df["data_turno"] = pd.to_datetime(pd.Series(list(zip(ano, turno)), index=df.index).map(datas))         .astype("datetime64[s]")
    df["mes_ano"] = df["data_turno"].dt.strftime("%Y-%m").astype("category")
    return df


def marcar_inconsistentes(df: pd.DataFrame, log: LogLimpeza) -> pd.DataFrame:
    """Marca, sem remover: `inconsistente` (aptos ≠ comparecimento + abstenção) e
    `perfil_implausivel` (16–17 anos com superior completo, EDA item 12)."""
    df = df.copy()
    df["inconsistente"] = (df["qt_aptos"] != df["qt_comparecimento"] + df["qt_abstencao"]).to_numpy()
    idade = _idade_inicial(df["cd_faixa_etaria"])
    escolaridade = pd.to_numeric(df["cd_grau_escolaridade"]).astype("Int8")
    df["perfil_implausivel"] = ((idade <= 17) & escolaridade.eq(SUPERIOR_COMPLETO)).fillna(False).astype(bool)
    n = len(df)
    log._texto("consistencia", n, n, int(df["inconsistente"].sum()))
    log._texto("12", n, n, int(df["perfil_implausivel"].sum()))
    return df


@lru_cache(maxsize=1)
def _tabelas_ibge() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from src.ibge import depara_tse_ibge, pib_municipios, populacao_municipios
    return depara_tse_ibge(), populacao_municipios(ANOS), pib_municipios()


def integrar_ibge(df: pd.DataFrame, log: LogLimpeza, depara: pd.DataFrame | None = None,
                  populacao: pd.DataFrame | None = None, pib: pd.DataFrame | None = None) -> pd.DataFrame:
    """Junta código IBGE (de-para + DEPARA_EXTRA), população (mesmo ano) e PIB (ano_eleicao).

    Exterior fica com cd_municipio_ibge nulo. Registra no log as linhas casadas só pelo par
    acrescentado e as linhas que continuam sem par.
    """
    if depara is None or populacao is None or pib is None:
        depara_p, pop_p, pib_p = _tabelas_ibge()
        depara = depara_p if depara is None else depara
        populacao = pop_p if populacao is None else populacao
        pib = pib_p if pib is None else pib
    mapa = dict(zip(depara["cd_municipio_tse"].astype(str), depara["cd_municipio_ibge"].astype(str)))
    extra = {k: v for k, v in DEPARA_EXTRA.items() if k not in mapa}
    mapa.update(extra)

    df = df.copy()
    cd = df["cd_municipio"].astype(str)
    exterior = df["sg_uf"].astype(str).eq("ZZ").to_numpy()
    ibge = cd.map(mapa).where(~exterior)
    df["cd_municipio_ibge"] = ibge.astype("string")
    n = len(df)

    pop = populacao[["cd_municipio_ibge", "ano", "populacao", "fonte_populacao"]].copy()
    pop["cd_municipio_ibge"] = pop["cd_municipio_ibge"].astype("string")
    pop["ano"] = pop["ano"].astype("int16")
    pib = pib.rename(columns={"ano": "ano_pib"})[["cd_municipio_ibge", "ano_eleicao", "ano_pib",
                                                  "pib_mil_reais", "pib_per_capita"]].copy()
    pib["cd_municipio_ibge"] = pib["cd_municipio_ibge"].astype("string")
    pib["ano_eleicao"] = pib["ano_eleicao"].astype("int16")

    ano_original = df["ano"].dtype
    chave = pd.DataFrame({"cd_municipio_ibge": df["cd_municipio_ibge"],
                          "ano": pd.to_numeric(df["ano"]).astype("int16").to_numpy()})
    m = chave.merge(pop, on=["cd_municipio_ibge", "ano"], how="left", validate="many_to_one")
    m = m.merge(pib, left_on=["cd_municipio_ibge", "ano"], right_on=["cd_municipio_ibge", "ano_eleicao"],
                how="left", validate="many_to_one")
    df["populacao"] = m["populacao"].astype("Int32").to_numpy()
    df["fonte_populacao"] = pd.Categorical(m["fonte_populacao"])
    df["ano_pib"] = m["ano_pib"].astype("Int16").to_numpy()
    df["pib_mil_reais"] = m["pib_mil_reais"].astype("Float64").round().astype("Int64").to_numpy()
    df["pib_per_capita"] = m["pib_per_capita"].astype("float64").to_numpy()
    df["ano"] = df["ano"].astype(ano_original)

    depois = len(m)  # validate="many_to_one" garante que a junção não duplica linhas
    log._texto("7a", n, depois, int(cd.isin(list(extra)).sum()))
    log._texto("7b", n, depois, int(m["cd_municipio_ibge"].isna().sum()))
    quebra = (m["fonte_populacao"].astype(str).str.startswith("censo")
              | (m["ano_pib"].notna() & (m["ano_pib"] != m["ano"]))).to_numpy()
    log._texto("13", n, depois, int(quebra.sum()))
    return df


# --------------------------------------------------------------------------- silver
SCHEMA_SILVER = pa.schema([
    ("nr_turno", pa.int8()),
    ("cd_municipio", pa.string()),
    ("cd_municipio_ibge", pa.string()),
    ("nm_municipio", pa.dictionary(pa.int32(), pa.string())),
    ("nr_zona", pa.int16()),
    ("cd_genero", pa.int8()), ("ds_genero", pa.dictionary(pa.int32(), pa.string())),
    ("cd_estado_civil", pa.int8()), ("ds_estado_civil", pa.dictionary(pa.int32(), pa.string())),
    ("cd_faixa_etaria", pa.int16()), ("ds_faixa_etaria", pa.dictionary(pa.int32(), pa.string())),
    ("cd_grau_escolaridade", pa.int8()), ("ds_grau_escolaridade", pa.dictionary(pa.int32(), pa.string())),
    *[(c, pa.int32()) for c in [
        "qt_aptos", "qt_comparecimento", "qt_abstencao", "qt_comparecimento_deficiencia",
        "qt_abstencao_deficiencia", "qt_comparecimento_tte", "qt_abstencao_tte", "qt_comparec_facultativo",
        "qt_abst_facultativo", "qt_comparec_obrigatorio", "qt_abst_obrigatorio",
        "qt_comparec_defic_facultativo", "qt_abst_defic_facultativo", "qt_comparec_defic_obrigatorio",
        "qt_abst_defic_obrigatorio"]],
    ("tipo_eleicao", pa.dictionary(pa.int32(), pa.string())),
    ("nm_regiao", pa.dictionary(pa.int32(), pa.string())),
    ("exterior", pa.bool_()),
    ("tem_2o_turno", pa.bool_()),
    ("data_turno", pa.date32()),
    ("mes_ano", pa.dictionary(pa.int32(), pa.string())),
    ("faixa_etaria_agrupada", pa.dictionary(pa.int32(), pa.string(), ordered=True)),
    ("grupo_idade", pa.dictionary(pa.int32(), pa.string(), ordered=True)),
    ("voto_facultativo", pa.bool_()),
    ("inconsistente", pa.bool_()),
    ("perfil_implausivel", pa.bool_()),
    ("populacao", pa.int32()),
    ("fonte_populacao", pa.dictionary(pa.int32(), pa.string())),
    ("ano_pib", pa.int16()),
    ("pib_mil_reais", pa.int64()),
    ("pib_per_capita", pa.float64()),
])


def salvar_silver(df: pd.DataFrame, raiz: Path = SILVER_TSE) -> int:
    """Grava cada (ano, sg_uf) de `df` em raiz/ano=AAAA/sg_uf=XX/parte-0.parquet (zstd),
    substituindo o que houver na partição. Colunas fora de SCHEMA_SILVER são ignoradas e as
    que faltam (ex.: num teste) são omitidas. Retorna as linhas gravadas."""
    raiz = Path(raiz)
    campos = [f for f in SCHEMA_SILVER if f.name in df.columns]
    schema = pa.schema(campos)
    total = 0
    for (ano, uf), parte in df.groupby(["ano", "sg_uf"], observed=True, sort=True):
        pasta = raiz / f"ano={int(ano)}" / f"sg_uf={uf}"
        shutil.rmtree(pasta, ignore_errors=True)
        pasta.mkdir(parents=True)
        tabela = pa.Table.from_pandas(parte[schema.names], schema=schema, preserve_index=False)
        pq.write_table(tabela, pasta / "parte-0.parquet", compression="zstd")
        total += tabela.num_rows
    return total


def limpar_particao(bronze: pd.DataFrame, log: LogLimpeza) -> pd.DataFrame:
    """Pipeline completo de uma partição (ano × UF) da bronze."""
    df = padronizar_colunas(bronze)
    df = tratar_sentinelas(df, log)
    df = harmonizar_anos(df, log)
    df = tipar(df)
    log._texto("8", len(df), len(df), 0)
    df = remover_redundantes(df, log)
    df = agregar_por_chave(df, log)
    df = remover_perfil_2024(df, log)
    df = derivar(df)
    n = len(df)
    log._texto("1", n, n, int(df["tem_2o_turno"].sum()))
    log._texto("3", n, n, int(df["exterior"].sum()))
    log._texto("6", n, n, int((df["cd_faixa_etaria"] >= 9094).fillna(False).sum()))
    log._texto("9", n, n, 0)
    log._texto("mes_ano", n, n, 0)
    log._texto("facultativo", n, n, int(df["voto_facultativo"].isna().sum()))
    log._texto("11", n, n, 0)
    log._texto("taxa_100k", n, n, 0)
    df = marcar_inconsistentes(df, log)
    return integrar_ibge(df, log)


def _particoes_bronze(raiz: Path) -> list[tuple[int, str]]:
    return sorted((int(a.name.split("=")[1]), u.name.split("=")[1])
                  for a in Path(raiz).glob("ano=*") for u in a.glob("SG_UF=*"))


def construir_silver(anos: list[int] = ANOS, log: LogLimpeza | None = None, raiz_bronze: Path | None = None,
                     destino: Path = SILVER_TSE, verbose: bool = True) -> LogLimpeza:
    """Roda `limpar_particao` em cada ano × UF da bronze e grava a silver.

    Idempotente por ano: a pasta ano=AAAA da silver é apagada antes de reprocessar o ano.
    """
    from src.coleta import PARQUET, ler_bronze
    raiz_bronze = PARQUET if raiz_bronze is None else Path(raiz_bronze)
    log = LogLimpeza() if log is None else log
    dataset = ler_bronze(raiz_bronze)
    colunas = [c for c in dataset.schema.names]
    particoes = [(a, u) for a, u in _particoes_bronze(raiz_bronze) if a in anos]
    for ano in sorted({a for a, _ in particoes}):
        shutil.rmtree(Path(destino) / f"ano={ano}", ignore_errors=True)
        t0, lidas, gravadas = time.time(), 0, 0
        for _, uf in [p for p in particoes if p[0] == ano]:
            filtro = (ds.field("ano") == ano) & (ds.field("SG_UF") == uf)
            bronze = dataset.to_table(columns=colunas, filter=filtro).to_pandas(strings_to_categorical=True)
            lidas += len(bronze)
            gravadas += salvar_silver(limpar_particao(bronze, log), destino)
            del bronze
        if verbose:
            print(f"{ano}: {lidas:,} linhas bronze -> {gravadas:,} silver ({time.time() - t0:.0f} s)")
    METADADOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    anteriores = json.loads(METADADOS_PATH.read_text(encoding="utf-8")) if METADADOS_PATH.exists() else {}
    anteriores.update({str(a): {k: sorted(v) for k, v in m.items()} for a, m in log.metadados.items()})
    METADADOS_PATH.write_text(json.dumps(anteriores, indent=2, ensure_ascii=False), encoding="utf-8")
    return log


# --------------------------------------------------------------------------- ausentes
def valores_ausentes(coluna: str) -> set[str]:
    """Valores de texto da bronze que `tratar_sentinelas` trata como ausentes nesta coluna (cd_*/ds_*)."""
    valores = set(SENTINELAS) | ROTULOS_SENTINELA.get(coluna, set())
    if coluna in CODIGO_ZERO_SENTINELA:
        valores.add(CODIGO_ZERO)
    return valores


def _sql_lista(valores) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in sorted(valores))


def ausentes_antes_depois(raiz_bronze: Path | None = None, raiz_silver: Path = SILVER_TSE,
                          path: Path | None = AUSENTES_PATH) -> pd.DataFrame:
    """% de linhas ausentes por coluna na bronze (nulo ou sentinela) e na silver (nulo ou
    NÃO INFORMADO). Coluna removida na silver: pct_ausente_depois vazio; coluna nova: antes vazio."""
    from src.coleta import PARQUET
    raiz_bronze = PARQUET if raiz_bronze is None else Path(raiz_bronze)
    con = duckdb.connect()
    con.execute("SET enable_progress_bar = false")
    bronze = f"read_parquet('{(Path(raiz_bronze) / '**' / '*.parquet').as_posix()}', hive_partitioning = true, union_by_name = true)"
    silver = f"read_parquet('{(Path(raiz_silver) / '**' / '*.parquet').as_posix()}', hive_partitioning = true)"

    def medir(fonte: str, regra) -> pd.Series:
        cols = [c for c in con.sql(f"DESCRIBE SELECT * FROM {fonte}").df()["column_name"]]
        exprs = [f'avg(CASE WHEN {regra(c)} THEN 100.0 ELSE 0 END) AS "{c}"' for c in cols]
        return con.sql(f"SELECT {', '.join(exprs)} FROM {fonte}").df().iloc[0]

    def regra_bronze(c: str) -> str:
        nome = padronizar_colunas(pd.DataFrame(columns=[c])).columns[0]
        if nome.startswith(("cd_", "ds_")) and nome != "cd_municipio":
            return f"{c} IS NULL OR {c} IN ({_sql_lista(valores_ausentes(nome))})"
        return f"{c} IS NULL"

    def regra_silver(c: str) -> str:
        if c.startswith("ds_"):
            return f"{c} IS NULL OR {c} = '{NAO_INFORMADO}'"
        return f"{c} IS NULL"

    antes = medir(bronze, regra_bronze)
    antes.index = padronizar_colunas(pd.DataFrame(columns=antes.index)).columns
    depois = medir(silver, regra_silver)
    r = (pd.DataFrame({"pct_ausente_antes": antes}).join(pd.DataFrame({"pct_ausente_depois": depois}), how="outer")
         .rename_axis("coluna").reset_index())
    ordem = {c: i for i, c in enumerate(list(antes.index) + [c for c in depois.index if c not in antes.index])}
    r = r.sort_values("coluna", key=lambda s: s.map(ordem)).reset_index(drop=True)
    r[["pct_ausente_antes", "pct_ausente_depois"]] = r[["pct_ausente_antes", "pct_ausente_depois"]].round(4)
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        r.to_csv(path, index=False, encoding="utf-8")
    return r


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Constrói a camada silver do TSE e o log de limpeza")
    p.add_argument("--anos", type=int, nargs="+", default=ANOS)
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # console do Windows (cp1252) não imprime "→"
        sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    log = construir_silver(args.anos)
    log.salvar()
    print(log.tabela()[["problema", "linhas_antes", "linhas_depois", "linhas_afetadas"]].to_string())
    print(ausentes_antes_depois().to_string())
    print(f"total: {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
