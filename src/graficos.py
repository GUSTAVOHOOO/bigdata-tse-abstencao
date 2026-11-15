"""Figuras da Etapa 1 (abstenção eleitoral, TSE 2018–2024 + IBGE).

Uma função `fig_NN_*` por figura. Cada uma lê as tabelas gold (data/gold/) e os relatórios
(reports/), calcula os números que o título afirma e salva um PNG de 150 dpi em
reports/figuras/. O título é a resposta: os números dele vêm das funções puras deste
módulo (`taxas_por`, `taxa_agregada`, `resumo_*`), testadas em tests/test_graficos.py.

Taxas são frações (0–1) nas tabelas gold; as colunas pct_ausente_* do relatório de ausentes
estão em porcentagem (0,75 = 0,75%). Os textos usam vírgula decimal e ponto de milhar.

Execução (gera as 9 figuras):
    .venv/Scripts/python.exe src/graficos.py
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

if __package__ in (None, ""):  # execução direta: src/graficos.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import geopandas as gpd  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
from matplotlib.cm import ScalarMappable  # noqa: E402
from matplotlib.colors import TwoSlopeNorm  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from src.config import BRONZE, FIGURAS, GOLD, REPORTS  # noqa: E402

GEO = BRONZE / "geo"
ANO_ULTIMO = 2024           # figuras de corte transversal (UF, faixa, região, heatmap, mapa)
ANO_COBERTURA_TOTAL = 2022  # eleição geral com todos os municípios (dispersão, fig. 05)
MALHA_ANO = 2020            # malha de referência do geobr / IBGE
MIN_APTOS_CELULA = 10_000   # heatmap: células menores ficam em cinza
DPI = 150

# Paleta de dataviz/references/palette.md (tema claro). Texto usa tokens de tinta, nunca a cor da série.
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TINTA_3 = "#898781"
GRADE = "#e1e0d9"
BASE = "#c3c2b7"
AZUL = "#2a78d6"       # categórica 1; sequencial e pólo azul do divergente
LARANJA = "#eb6834"    # categórica 2
VERMELHO = "#e34948"   # pólo vermelho do divergente
CINZA_DIV = "#f0efec"  # ponto neutro do divergente
SEQ = {100: "#cde2fb", 150: "#b7d3f6", 200: "#9ec5f4", 250: "#86b6ef", 300: "#6da7ec", 350: "#5598e7",
       400: "#3987e5", 450: "#2a78d6", 500: "#256abf", 550: "#1c5cab", 600: "#184f95", 650: "#104281",
       700: "#0d366b"}
CMAP_SEQ = mcolors.LinearSegmentedColormap.from_list("azul_seq", [SEQ[s] for s in sorted(SEQ)[:-1]])
CMAP_DIV = mcolors.LinearSegmentedColormap.from_list("azul_cinza_vermelho", [AZUL, CINZA_DIV, VERMELHO])

ORDEM_FAIXA = ["16–17", "18–24", "25–34", "35–44", "45–59", "60–69", "70+"]
ORDEM_ESCOLARIDADE = ["ANALFABETO", "LÊ E ESCREVE", "ENSINO FUNDAMENTAL INCOMPLETO", "ENSINO FUNDAMENTAL COMPLETO",
                      "ENSINO MÉDIO INCOMPLETO", "ENSINO MÉDIO COMPLETO", "SUPERIOR INCOMPLETO", "SUPERIOR COMPLETO"]
NAO_INFORMADO = "NÃO INFORMADO"
GRUPOS_FACULTATIVOS = ["16–17", "70+"]  # CF art. 14 §1º II: 16–17 anos e 70 anos ou mais
GRUPO_OBRIGATORIO = "18–69"
CAMPOS_PERFIL = {"cd_grau_escolaridade": "Escolaridade", "cd_genero": "Gênero",
                 "cd_estado_civil": "Estado civil", "cd_faixa_etaria": "Faixa etária"}
UF_SIGLA = {11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO", 21: "MA", 22: "PI", 23: "CE",
            24: "RN", 25: "PB", 26: "PE", 27: "AL", 28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP",
            41: "PR", 42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF"}


# ---------------------------------------------------------------------------------------------
# Formatação pt-BR
# ---------------------------------------------------------------------------------------------

def _num(valor: float, casas: int = 1, sinal: bool = False) -> str:
    """0,217 -> '0,2'. Negativo usa o sinal de menos (−); `sinal` põe + nos positivos."""
    texto = f"{abs(valor):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if valor < 0:
        return "−" + texto
    return ("+" + texto) if sinal and valor > 0 else texto


def _pct(fracao: float, casas: int = 1) -> str:
    """Fração 0–1 em porcentagem: 0,2172 -> '21,7%'."""
    return _num(100 * fracao, casas) + "%"


def _pct_do_relatorio(valor: float, casas: int = 2) -> str:
    """Valor já em porcentagem (relatório de ausentes): 0,7548 -> '0,75%'."""
    return _num(valor, casas) + "%"


def _inteiro(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", ".")


def _pp(valor: float) -> str:
    """Diferença já em pontos percentuais: 3,44 -> '+3,4 p.p.'."""
    return _num(valor, 1, sinal=True) + " p.p."


# ---------------------------------------------------------------------------------------------
# Funções puras (testadas)
# ---------------------------------------------------------------------------------------------

def taxa_agregada(df: pd.DataFrame) -> float:
    """Taxa de abstenção de um conjunto de linhas: soma as contagens e só então divide.
    A média das taxas dá outro número quando os grupos têm eleitorados de tamanhos diferentes."""
    aptos = df["qt_aptos"].sum()
    return float(df["qt_abstencao"].sum() / aptos) if aptos else float("nan")


def taxas_por(df: pd.DataFrame, por: list[str]) -> pd.DataFrame:
    """Reagrega as contagens por `por` e calcula a taxa: sum(qt_abstencao) / sum(qt_aptos)."""
    g = df.groupby(por, observed=True)[["qt_aptos", "qt_abstencao"]].sum()
    g["taxa"] = g["qt_abstencao"] / g["qt_aptos"]
    return g.reset_index()


def resumo_mudanca_uf(uf: pd.DataFrame, ano_ini: int, ano_fim: int) -> dict:
    """Variação da taxa por UF entre dois anos, em pontos percentuais (só UFs presentes nos dois anos)."""
    p = uf.pivot(index="sg_uf", columns="ano", values="taxa_abstencao")
    d = ((p[ano_fim] - p[ano_ini]) * 100).dropna()
    return {
        "ufs": int(len(d)),
        "subiram": int((d > 0).sum()),
        "maior_alta_uf": d.idxmax(), "maior_alta_pp": float(d.max()),
        "maior_queda_uf": d.idxmin(), "maior_queda_pp": float(d.min()),
        "variacao": d.sort_values(),
    }


def resumo_uf(uf_ano: pd.DataFrame, n_extremos: int = 10) -> dict:
    """Ranking de UFs de um ano: taxa nacional agregada e quantos dos `n_extremos` menores são do Nordeste."""
    ordenado = uf_ano.sort_values("taxa_abstencao").reset_index(drop=True)
    menores = ordenado.head(n_extremos)
    return {
        "nacional": taxa_agregada(uf_ano),
        "ordenado": ordenado,
        "menor": ordenado.iloc[0], "maior": ordenado.iloc[-1],
        "menores_nordeste": int((menores["nm_regiao"] == "Nordeste").sum()),
        "n_menores": len(menores),
    }


def correlacao_spearman(df: pd.DataFrame, x: str, y: str) -> float:
    """Correlação de Spearman entre duas colunas, sem as linhas em que alguma é nula."""
    return float(df[[x, y]].dropna().corr(method="spearman").iloc[0, 1])


def resumo_perfil(perfil: pd.DataFrame) -> dict:
    """Células faixa × escolaridade (sem NÃO INFORMADO), com taxa agregada e máximos para o título."""
    base = perfil[(perfil["faixa_etaria_agrupada"] != NAO_INFORMADO)
                  & (perfil["ds_grau_escolaridade"] != NAO_INFORMADO)]
    celulas = taxas_por(base, ["faixa_etaria_agrupada", "ds_grau_escolaridade"])
    adultos = taxas_por(base[base["grupo_idade"] == GRUPO_OBRIGATORIO], ["ds_grau_escolaridade"])
    analf_70 = celulas[(celulas["faixa_etaria_agrupada"] == "70+") & (celulas["ds_grau_escolaridade"] == "ANALFABETO")]
    return {
        "celulas": celulas,
        "max_70_analfabeto": float(analf_70["taxa"].iloc[0]),
        "max_18_69": float(adultos["taxa"].max()),
    }


def resumo_municipios(mun: pd.DataFrame) -> dict:
    """Mediana e quartis municipais por região (linhas já sem exterior)."""
    por_regiao = (mun.groupby("nm_regiao")["taxa_abstencao"]
                  .agg(mediana="median", q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75), n="size")
                  .sort_values("mediana", ascending=False))
    return {"por_regiao": por_regiao,
            "maior_mediana": por_regiao.index[0], "menor_mediana": por_regiao.index[-1]}


def etapas_de_linhas(log: pd.DataFrame) -> dict:
    """Etapas do log que mudam o número de linhas (unidade 'linhas'), com bronze e silver.
    Confere que bronze − soma das etapas = silver: se não fechar, a figura não é gerada."""
    linhas = log[log["unidade"] == "linhas"]
    bronze = int(linhas["linhas_antes"].max())
    mudam = linhas[linhas["linhas_antes"] != linhas["linhas_depois"]].sort_values("linhas_antes", ascending=False)
    etapas = [(r.problema, int(r.linhas_antes - r.linhas_depois)) for r in mudam.itertuples()]
    silver = bronze - sum(delta for _, delta in etapas)
    assert silver == int(linhas["linhas_depois"].min()), "log de linhas não fecha: bronze − etapas ≠ silver"
    return {"bronze": bronze, "silver": silver, "etapas": etapas}


def resumo_ausentes(aus: pd.DataFrame) -> dict:
    """Colunas de perfil presentes antes e depois (cd_*), em porcentagem; maior ausente depois."""
    ambos = aus.dropna(subset=["pct_ausente_antes", "pct_ausente_depois"])
    perfil = ambos[ambos["coluna"].isin(CAMPOS_PERFIL)].reset_index(drop=True)
    return {"perfil": perfil, "maior_depois": float(perfil["pct_ausente_depois"].max())}


# ---------------------------------------------------------------------------------------------
# Dados e geometria
# ---------------------------------------------------------------------------------------------

def _gold(nome: str) -> pd.DataFrame:
    return pd.read_parquet(GOLD / f"{nome}.parquet")


def _municipios(ano: int) -> pd.DataFrame:
    m = _gold("municipio_ano")
    return m[(m["ano"] == ano) & (~m["exterior"])].copy()


def _malha_geobr(tipo: str) -> gpd.GeoDataFrame:
    """Malha 2020 via geobr. Usa output='duckdb' e converte aqui: a saída 'gpd' do geobr falha com o duckdb atual."""
    import geobr
    if tipo == "municipios":
        rel = geobr.read_municipality(code_muni="all", year=MALHA_ANO, output="duckdb", show_progress=False)
        df = rel.select("* EXCLUDE(geometry), ST_AsWKB(geometry) AS wkb").df()
        codigo = {"cd_municipio_ibge": df["code_muni"].astype("int64").astype(str).values}
    else:
        rel = geobr.read_state(code_state="all", year=MALHA_ANO, output="duckdb", show_progress=False)
        df = rel.select("* EXCLUDE(geometry), ST_AsWKB(geometry) AS wkb").df()
        codigo = {"cd_uf": df["code_state"].astype("int64").values}
    return gpd.GeoDataFrame(codigo, geometry=gpd.GeoSeries.from_wkb(df["wkb"].map(bytes)).values, crs="EPSG:4674")


def _malha_ibge(nivel: str) -> gpd.GeoDataFrame:
    """Malha da API de malhas do IBGE (plano B, quando o geobr falha). `codarea` é o código IBGE."""
    url = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
           f"?formato=application/vnd.geo+json&qualidade=minima&intrarregiao={nivel}")
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    g = gpd.GeoDataFrame.from_features(resp.json()["features"], crs="EPSG:4674")
    if nivel == "municipio":
        codigo = {"cd_municipio_ibge": g["codarea"].astype(str).values}
    else:
        codigo = {"cd_uf": g["codarea"].astype(int).values}
    return gpd.GeoDataFrame(codigo, geometry=g.geometry.values, crs="EPSG:4674")


def _malhas() -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Malhas municipal e de UF em GeoParquet, em data/bronze/geo (com cache: reruns sem rede)."""
    GEO.mkdir(parents=True, exist_ok=True)
    arquivos = {"municipios": GEO / f"municipios_{MALHA_ANO}.parquet", "ufs": GEO / f"ufs_{MALHA_ANO}.parquet"}
    if all(c.exists() for c in arquivos.values()):
        return gpd.read_parquet(arquivos["municipios"]), gpd.read_parquet(arquivos["ufs"])
    try:
        mun, uf = _malha_geobr("municipios"), _malha_geobr("ufs")
        print("malhas: geobr")
    except Exception as erro:  # noqa: BLE001 - qualquer falha do geobr cai no plano B
        print(f"malhas: geobr falhou ({type(erro).__name__}: {erro}); usando a API de malhas do IBGE")
        mun, uf = _malha_ibge("municipio"), _malha_ibge("UF")
    mun.to_parquet(arquivos["municipios"])
    uf.to_parquet(arquivos["ufs"])
    return mun, uf


# ---------------------------------------------------------------------------------------------
# Moldura comum: título (resposta), subtítulo (como ler) e rodapé (fonte e observações)
# ---------------------------------------------------------------------------------------------

def _moldura(fig: Figure, titulo: str, subtitulo: str = "") -> float:
    """Escreve título e subtítulo no topo. Devolve a altura (fração) onde os eixos podem começar.
    A quebra de linha acompanha a largura da figura (em polegadas), para o texto não sair da área."""
    largura = fig.get_figwidth()
    linhas_titulo = "\n".join(textwrap.wrap(titulo, int(largura * 8.3)))
    fig.text(0.03, 0.965, linhas_titulo, ha="left", va="top", fontsize=13, fontweight="bold", color=TINTA,
             linespacing=1.3)
    y = 0.965 - 0.047 * (linhas_titulo.count("\n") + 1) - 0.01
    if subtitulo:
        linhas_sub = "\n".join(textwrap.wrap(subtitulo, int(largura * 11)))
        fig.text(0.03, y, linhas_sub, ha="left", va="top", fontsize=9.5, color=TINTA_2, linespacing=1.35)
        y -= 0.027 * (linhas_sub.count("\n") + 1) + 0.012
    return y


def _rodape(fig: Figure, texto: str) -> None:
    fig.text(0.03, 0.02, "\n".join(textwrap.wrap(texto, int(fig.get_figwidth() * 13.5))), ha="left", va="bottom",
             fontsize=8, color=TINTA_3, linespacing=1.3)


def _eixos_limpos(ax, grade: str | None = "y") -> None:
    """Sem moldura superior/direita, linha de base discreta e grade de 1 px só no eixo indicado."""
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(BASE)
    ax.tick_params(colors=TINTA_2, labelsize=9, length=0)
    ax.set_facecolor(SUPERFICIE)
    ax.grid(False)
    if grade:
        ax.grid(axis=grade, color=GRADE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)


def _fmt_pct(casas: int = 0) -> FuncFormatter:
    return FuncFormatter(lambda v, _: _pct(v, casas))


def _salvar(fig: Figure, nome: str) -> Path:
    FIGURAS.mkdir(parents=True, exist_ok=True)
    caminho = FIGURAS / f"{nome}.png"
    fig.savefig(caminho, dpi=DPI, facecolor=SUPERFICIE)
    return caminho


# ---------------------------------------------------------------------------------------------
# Figuras
# ---------------------------------------------------------------------------------------------

def fig_01_abstencao_por_eleicao() -> Path:
    serie = taxas_por(_gold("turnos"), ["conjunto", "nr_turno", "ano"])
    t1 = serie[(serie["conjunto"] == "todos") & (serie["nr_turno"] == 1)].set_index("ano")["taxa"]
    t2 = serie[(serie["conjunto"] == "com_2o_turno") & (serie["nr_turno"] == 2)].set_index("ano")["taxa"]
    t1_cidades_2o = serie[(serie["conjunto"] == "com_2o_turno") & (serie["nr_turno"] == 1)].set_index("ano")["taxa"]

    titulo = (f"No 1º turno a abstenção ficou entre {_pct(t1.min())} e {_pct(t1.max())} em 2018–2024; "
              f"no 2º turno das municipais chegou a {_pct(t2[2020])} em 2020 e a {_pct(t2[2024])} em 2024")
    subtitulo = ("Taxa = abstenções ÷ eleitores aptos, sem exterior. Linha laranja: só as cidades que tiveram 2º turno "
                 f"(no 1º turno delas a taxa foi {_pct(t1_cidades_2o[2020])} em 2020 e "
                 f"{_pct(t1_cidades_2o[2024])} em 2024).")

    fig = Figure(figsize=(10, 6.2), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    ax = fig.add_axes([0.08, 0.14, 0.86, topo - 0.14 - 0.03])
    _eixos_limpos(ax, "y")
    anos = list(t1.index)
    for serie_taxa, outra, cor, rotulo in [
        (t1, t2, AZUL, "1º turno (todos os municípios)"),
        (t2, t1, LARANJA, "2º turno (municípios com 2º turno)"),
    ]:
        ys = [serie_taxa[a] for a in anos]
        ax.plot(anos, ys, color=cor, linewidth=2, label=rotulo, zorder=3)
        ax.scatter(anos, ys, s=70, color=cor, edgecolor=SUPERFICIE, linewidth=2, zorder=4)
        for x, y in zip(anos, ys):
            lado = 1 if y > outra[x] else -1  # rótulo do lado oposto ao da outra linha, para não colidir
            ax.annotate(_pct(y), (x, y), textcoords="offset points", xytext=(0, 10 * lado), ha="center",
                        va="bottom" if lado > 0 else "top", fontsize=9, color=TINTA)
    ax.set_xticks(anos)
    ax.set_xticklabels([f"{a}\n{'geral' if a in (2018, 2022) else 'municipal'}" for a in anos])
    ax.yaxis.set_major_formatter(_fmt_pct(0))
    ax.set_ylim(0.14, 0.34)
    ax.set_xlim(anos[0] - 0.4, anos[-1] + 0.4)
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=TINTA_2)
    _rodape(fig, "Fonte: TSE, perfil de comparecimento e abstenção (2018–2024), tabela gold turnos. Em 2018 e 2022 "
                 "(eleições gerais) as duas linhas usam os mesmos municípios.")
    return _salvar(fig, "fig_01_abstencao_por_eleicao")


def fig_02_abstencao_por_uf() -> Path:
    r = resumo_uf(_gold("uf_ano").query("ano == @ANO_ULTIMO"))
    o = r["ordenado"]
    titulo = (f"Em {ANO_ULTIMO}, {r['menores_nordeste']} dos {r['n_menores']} estados com menor abstenção são do "
              f"Nordeste; a mais alta é a de {r['maior']['sg_uf']} ({_pct(r['maior']['taxa_abstencao'])}) "
              f"e a mais baixa, a de {r['menor']['sg_uf']} ({_pct(r['menor']['taxa_abstencao'])})")
    subtitulo = (f"Taxa de abstenção do 1º turno por UF, sem exterior. Brasil: {_pct(r['nacional'])}. "
                 f"Em {ANO_ULTIMO} não há eleição geral, então o DF não entra ({len(o)} UFs).")

    fig = Figure(figsize=(10, 9), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    ax = fig.add_axes([0.1, 0.07, 0.84, topo - 0.07 - 0.02])
    _eixos_limpos(ax, "x")
    y = np.arange(len(o))
    ax.barh(y, o["taxa_abstencao"], height=0.62, color=AZUL, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels(o["sg_uf"], fontsize=9)
    ax.xaxis.set_major_formatter(_fmt_pct(0))
    ax.set_xlim(0, 0.30)
    for i in list(range(3)) + list(range(len(o) - 3, len(o))):
        v = o["taxa_abstencao"].iloc[i]
        ax.text(v + 0.004, i, _pct(v), va="center", fontsize=9, color=TINTA)
    ax.axvline(r["nacional"], color=TINTA_2, linewidth=1, zorder=4)
    ax.text(r["nacional"] + 0.004, len(o) - 0.4, f"Brasil {_pct(r['nacional'])}", fontsize=9, color=TINTA_2,
            va="bottom")
    ax.set_ylim(-0.6, len(o) - 0.1)
    _rodape(fig, f"Fonte: TSE ({ANO_ULTIMO}), tabela gold uf_ano. Ordem da menor para a maior taxa, de baixo para cima; "
                 "rótulos só nos três extremos de cada lado.")
    return _salvar(fig, "fig_02_abstencao_por_uf_2024")


def fig_03_abstencao_por_faixa_etaria() -> Path:
    p = _gold("perfil_ano").query("ano == @ANO_ULTIMO and faixa_etaria_agrupada != @NAO_INFORMADO")
    faixas = taxas_por(p, ["faixa_etaria_agrupada", "grupo_idade"]).set_index("faixa_etaria_agrupada").loc[ORDEM_FAIXA]
    por_grupo = taxas_por(p, ["grupo_idade"]).set_index("grupo_idade")["taxa"]
    t70, tob = por_grupo["70+"], por_grupo[GRUPO_OBRIGATORIO]
    t1617 = faixas.loc["16–17", "taxa"]

    titulo = (f"Em {ANO_ULTIMO}, os eleitores de 70 anos ou mais (voto facultativo) se abstiveram em {_pct(t70)}, "
              f"{_num(t70 / tob)} vezes a taxa dos obrigatórios de 18 a 69 anos ({_pct(tob)})")
    subtitulo = ("Taxa de abstenção por faixa etária, 1º turno, sem exterior. Facultativos (16–17 e 70+) em azul. "
                 f"Os de 16–17 anos, também facultativos, se abstêm em {_pct(t1617)}.")

    fig = Figure(figsize=(10, 6.2), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    ax = fig.add_axes([0.08, 0.14, 0.88, topo - 0.14 - 0.03])
    _eixos_limpos(ax, "y")
    x = np.arange(len(faixas))
    cores = [AZUL if g in GRUPOS_FACULTATIVOS else TINTA_3 for g in faixas["grupo_idade"]]
    ax.bar(x, faixas["taxa"], width=0.6, color=cores, zorder=3)
    for xi, v in zip(x, faixas["taxa"]):
        ax.text(xi, v + 0.01, _pct(v), ha="center", va="bottom", fontsize=9, color=TINTA)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{f} anos" for f in faixas.index], fontsize=9)
    ax.yaxis.set_major_formatter(_fmt_pct(0))
    ax.set_ylim(0, 0.6)
    ax.legend(handles=[Patch(color=AZUL, label="Voto facultativo (16–17 e 70+)"),
                       Patch(color=TINTA_3, label="Voto obrigatório (18–69)")],
              loc="upper left", frameon=False, fontsize=9, labelcolor=TINTA_2)
    _rodape(fig, f"Fonte: TSE ({ANO_ULTIMO}), tabela gold perfil_ano. Faixas agrupadas conforme a regra de voto "
                 "facultativo. 'NÃO INFORMADO' fica fora do gráfico.")
    return _salvar(fig, "fig_03_abstencao_por_faixa_etaria")


def fig_04_distribuicao_por_regiao() -> Path:
    mun = _municipios(ANO_ULTIMO)
    r = resumo_municipios(mun)
    pr = r["por_regiao"]
    titulo = (f"Em {ANO_ULTIMO}, a mediana municipal vai de {_pct(pr.loc[r['menor_mediana'], 'mediana'])} no "
              f"{r['menor_mediana']} a {_pct(pr.loc[r['maior_mediana'], 'mediana'])} no {r['maior_mediana']}; "
              f"as regiões se sobrepõem bastante")
    subtitulo = (f"Um ponto por município ({_inteiro(len(mun))} municípios, 1º turno, sem exterior). Caixa = 25º a 75º "
                 "percentil; linha = mediana; bigodes sem valores extremos.")

    fig = Figure(figsize=(10, 6.2), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    ax = fig.add_axes([0.08, 0.16, 0.88, topo - 0.16 - 0.03])
    _eixos_limpos(ax, "y")
    ordem = list(pr.index)
    dados = [mun.loc[mun["nm_regiao"] == reg, "taxa_abstencao"].dropna().values for reg in ordem]
    caixas = ax.boxplot(dados, positions=range(len(ordem)), widths=0.5, patch_artist=True, showfliers=False,
                        medianprops={"color": TINTA, "linewidth": 2},
                        whiskerprops={"color": TINTA_2, "linewidth": 1},
                        capprops={"color": TINTA_2, "linewidth": 1})
    for caixa in caixas["boxes"]:
        caixa.set(facecolor=AZUL, alpha=0.18, edgecolor=AZUL, linewidth=1.5)
    rng = np.random.default_rng(42)  # jitter fixo: a figura é reproduzível
    for i, valores in enumerate(dados):
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(valores)), valores, s=8, color=TINTA_3, alpha=0.35,
                   linewidths=0, zorder=2)
    ax.set_xticks(range(len(ordem)))
    ax.set_xticklabels([f"{reg}\nmediana {_pct(pr.loc[reg, 'mediana'])}" for reg in ordem], fontsize=9)
    ax.yaxis.set_major_formatter(_fmt_pct(0))
    ax.set_ylim(0, 0.5)
    _rodape(fig, f"Fonte: TSE ({ANO_ULTIMO}) e IBGE, tabela gold municipio_ano. Região segundo o IBGE; a mediana é "
                 "calculada sobre municípios, não sobre eleitores.")
    return _salvar(fig, "fig_04_distribuicao_por_regiao")


def fig_05_taxa_x_pib_populacao() -> Path:
    mun = _municipios(ANO_COBERTURA_TOTAL)
    rho_pib = correlacao_spearman(mun, "taxa_abstencao", "pib_per_capita")
    rho_pop = correlacao_spearman(mun, "taxa_abstencao", "populacao")
    titulo = (f"Relações fracas ({ANO_COBERTURA_TOTAL}): ρ = {_num(rho_pib, 2, sinal=True)} entre abstenção e PIB per "
              f"capita, e ρ = {_num(rho_pop, 2, sinal=True)} entre abstenção e população")
    subtitulo = (f"Cada ponto é um município ({ANO_COBERTURA_TOTAL}, eleição geral, 1º turno, sem exterior). Linha "
                 "azul: mediana da taxa em decis da variável no eixo x. ρ = correlação de Spearman.")

    fig = Figure(figsize=(11, 6), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    paineis = [("pib_per_capita", "PIB per capita (R$, escala log)", rho_pib),
               ("populacao", "População (escala log)", rho_pop)]
    for k, (var, rotulo_x, rho) in enumerate(paineis):
        ax = fig.add_axes([0.08 + k * 0.48, 0.19, 0.40, topo - 0.19 - 0.03])
        _eixos_limpos(ax, "y")
        d = mun.dropna(subset=[var, "taxa_abstencao"])
        ax.scatter(d[var], d["taxa_abstencao"], s=10, color=TINTA_3, alpha=0.35, linewidths=0, zorder=2)
        ax.set_xscale("log")
        decis = pd.qcut(d[var], 10, labels=False, duplicates="drop")
        medianas = d.groupby(decis, observed=True).agg(x=(var, "median"), y=("taxa_abstencao", "median"))
        ax.plot(medianas["x"], medianas["y"], color=AZUL, linewidth=2, marker="o", markersize=7,
                markeredgecolor=SUPERFICIE, markeredgewidth=2, zorder=4)
        ax.yaxis.set_major_formatter(_fmt_pct(0))
        ax.set_ylim(0, 0.5)
        ax.set_xlabel(rotulo_x, fontsize=9, color=TINTA_2)
        if k == 0:
            ax.set_ylabel("Taxa de abstenção municipal", fontsize=9, color=TINTA_2)
        ax.text(0.98, 0.97, f"ρ = {_num(rho, 2, sinal=True)}", transform=ax.transAxes, ha="right", va="top",
                fontsize=10, color=TINTA, fontweight="bold")
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _inteiro(v)))
    _rodape(fig, "Fonte: TSE (2022), IBGE (população e PIB municipais; PIB per capita conforme tabela gold). Municípios "
                 "sem população ou PIB ficam fora do painel correspondente.")
    return _salvar(fig, "fig_05_taxa_x_pib_populacao")


def fig_06_faixa_x_escolaridade() -> Path:
    r = resumo_perfil(_gold("perfil_ano").query("ano == @ANO_ULTIMO"))
    celulas = r["celulas"]
    titulo = (f"Em {ANO_ULTIMO}, a abstenção chega a {_pct(r['max_70_analfabeto'])} entre analfabetos de 70 anos ou "
              f"mais; entre 18 e 69 anos, nenhum nível de escolaridade passa de {_pct(r['max_18_69'])}")
    subtitulo = (f"Taxa de abstenção (1º turno, sem exterior) por faixa etária e escolaridade, somando gênero. Células "
                 f"com menos de {_inteiro(MIN_APTOS_CELULA)} aptos ficam cinzas. 'NÃO INFORMADO' fica fora do gráfico.")

    linhas = ORDEM_FAIXA
    M = np.full((len(linhas), len(ORDEM_ESCOLARIDADE)), np.nan)
    for _, c in celulas.iterrows():
        if c["faixa_etaria_agrupada"] in linhas and c["ds_grau_escolaridade"] in ORDEM_ESCOLARIDADE:
            i = linhas.index(c["faixa_etaria_agrupada"])
            j = ORDEM_ESCOLARIDADE.index(c["ds_grau_escolaridade"])
            if c["qt_aptos"] >= MIN_APTOS_CELULA:
                M[i, j] = c["taxa"]

    fig = Figure(figsize=(11, 6.6), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    ax = fig.add_axes([0.2, 0.18, 0.6, topo - 0.18 - 0.04])
    cmap = CMAP_SEQ.copy()
    cmap.set_bad(GRADE)
    ax.imshow(np.ma.masked_invalid(M), cmap=cmap, vmin=0.0, vmax=0.7, aspect="auto")
    for i in range(len(linhas)):
        for j in range(len(ORDEM_ESCOLARIDADE)):
            if np.isnan(M[i, j]):
                ax.text(j, i, "—", ha="center", va="center", fontsize=8, color=TINTA_3)
                continue
            ax.text(j, i, _num(100 * M[i, j]), ha="center", va="center", fontsize=9,
                    color="#ffffff" if M[i, j] > 0.40 else TINTA)
    ax.set_xticks(range(len(ORDEM_ESCOLARIDADE)))
    ax.set_xticklabels(["\n".join(textwrap.wrap(c.capitalize(), 13)) for c in ORDEM_ESCOLARIDADE],
                       fontsize=8, color=TINTA_2)
    ax.set_yticks(range(len(linhas)))
    ax.set_yticklabels([f"{f} anos" if f != "70+" else "70 anos ou mais" for f in linhas], fontsize=9, color=TINTA_2)
    for lado in ax.spines.values():
        lado.set_visible(False)
    ax.tick_params(length=0)
    cax = fig.add_axes([0.84, 0.3, 0.02, 0.4])
    cb = fig.colorbar(ScalarMappable(norm=mcolors.Normalize(0, 0.7), cmap=cmap), cax=cax)
    cb.set_ticks([0, 0.2, 0.4, 0.6])
    cb.set_ticklabels(["0%", "20%", "40%", "60%"])
    cb.set_label("abstenção", fontsize=8, color=TINTA_2)
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8, colors=TINTA_2, length=0)
    _rodape(fig, f"Fonte: TSE ({ANO_ULTIMO}), tabela gold perfil_ano. Escolaridade em ordem crescente, da esquerda para a "
                 "direita. Células com menos de 10 mil aptos (inclusive 16–17 anos com ensino superior, implausível) "
                 "ficam cinzas.")
    return _salvar(fig, "fig_06_faixa_x_escolaridade_2024")


def fig_07_mapa_municipal() -> Path:
    mun = _municipios(ANO_ULTIMO)
    gmun, _ = _malhas()
    j = gmun.merge(mun[["cd_municipio_ibge", "taxa_abstencao", "nm_regiao"]], on="cd_municipio_ibge", how="left")
    tse = set(mun["cd_municipio_ibge"])
    malha = set(gmun["cd_municipio_ibge"])
    sem_malha = len(tse - malha)   # município do TSE sem polígono
    sem_dado = len(malha - tse)    # polígono sem linha do TSE
    print(f"fig 07: {sem_malha} municípios do TSE sem malha; {sem_dado} malhas sem dado do TSE")

    alto = j[j["taxa_abstencao"] >= 0.25]
    por_regiao = alto["nm_regiao"].value_counts()
    n_ne, n_se = int(por_regiao.get("Nordeste", 0)), int(por_regiao.get("Sudeste", 0))
    titulo = (f"Em {ANO_ULTIMO}, só {n_ne} dos {len(alto)} municípios com abstenção de 25% ou mais são do Nordeste; "
              f"{n_se} são do Sudeste")
    subtitulo = (f"Taxa de abstenção do 1º turno por município ({_inteiro(len(mun))} municípios com dado), de "
                 f"{_pct(mun['taxa_abstencao'].min())} a {_pct(mun['taxa_abstencao'].max())}. Cinza: sem dado. "
                 "Cor pela taxa, não pelo número de eleitores.")

    fig = Figure(figsize=(9, 9.4), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    ax = fig.add_axes([0.02, 0.1, 0.8, topo - 0.1 - 0.02])
    norm = mcolors.Normalize(vmin=0.0, vmax=0.45)
    j.plot(column="taxa_abstencao", cmap=CMAP_SEQ, norm=norm, ax=ax, linewidth=0.05, edgecolor=SUPERFICIE,
           missing_kwds={"color": GRADE, "edgecolor": SUPERFICIE, "linewidth": 0.05})
    ax.set_axis_off()
    cax = fig.add_axes([0.84, 0.25, 0.02, 0.45])
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=CMAP_SEQ), cax=cax)
    cb.set_ticks([0, 0.1, 0.2, 0.3, 0.4])
    cb.set_ticklabels(["0%", "10%", "20%", "30%", "40%"])
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8, colors=TINTA_2, length=0)
    cb.set_label("abstenção", fontsize=8, color=TINTA_2)
    _rodape(fig, f"Fonte: TSE ({ANO_ULTIMO}), IBGE (malha municipal de {MALHA_ANO}). Municípios do TSE sem polígono: "
                 f"{sem_malha}; polígonos sem dado do TSE: {sem_dado}.")
    return _salvar(fig, "fig_07_mapa_municipal_2024")


def fig_08_mapa_uf_variacao() -> Path:
    r = resumo_mudanca_uf(_gold("uf_ano"), 2018, 2022)
    _, guf = _malhas()
    guf = guf.assign(sg_uf=guf["cd_uf"].map(UF_SIGLA))
    d = r["variacao"].rename("variacao_pp").reset_index()
    j = guf.merge(d, on="sg_uf", how="left")
    sem_dado = int(j["variacao_pp"].isna().sum())
    print(f"fig 08: {sem_dado} UF(s) do mapa sem dado")
    vmax = float(np.nanmax(np.abs(j["variacao_pp"])))
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    titulo = (f"Entre 2018 e 2022, a abstenção subiu em {r['subiram']} das {r['ufs']} UFs; a maior alta foi a do "
              f"{r['maior_alta_uf']} ({_pp(r['maior_alta_pp'])}) e a maior queda, a do {r['maior_queda_uf']} "
              f"({_pp(r['maior_queda_pp'])})")
    subtitulo = ("Variação da taxa de abstenção do 1º turno por UF, em pontos percentuais (2022 menos 2018). Vermelho: "
                 "subiu. Azul: caiu. Ambas são eleições gerais e incluem o DF.")
    fig = Figure(figsize=(9, 8.6), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)
    ax = fig.add_axes([0.02, 0.1, 0.8, topo - 0.1 - 0.02])
    j.plot(column="variacao_pp", cmap=CMAP_DIV, norm=norm, ax=ax, linewidth=0.4, edgecolor=SUPERFICIE,
           missing_kwds={"color": GRADE, "edgecolor": SUPERFICIE})
    ax.set_axis_off()
    # Rótulo dentro do polígono; UFs pequenas (área em graus², borda de 1 px ilegível) ganham rótulo fora do
    # mapa, à direita, ligado ao polígono por uma linha fina.
    pontos = j.dropna(subset=["variacao_pp"]).copy()
    pontos["ponto"] = pontos.geometry.representative_point()
    pequenas = pontos[pontos.geometry.map(lambda g: g.area) < 6.0].assign(y=lambda d: d["ponto"].map(lambda p: p.y))
    pequenas = pequenas.sort_values("y", ascending=False)
    minx, _, maxx, _ = j.total_bounds
    x_lab = maxx + 2.0
    ys_lab = np.linspace(pequenas["y"].max() + 0.6, pequenas["y"].min() - 0.6, len(pequenas))
    for (_, linha), y_lab in zip(pequenas.iterrows(), ys_lab):
        p = linha["ponto"]
        ax.plot([p.x, x_lab - 0.2], [p.y, y_lab], color=TINTA_3, linewidth=0.6, zorder=2)
        ax.text(x_lab, y_lab, f"{linha['sg_uf']} {_num(linha['variacao_pp'], 1, sinal=True)}", va="center",
                fontsize=7, color=TINTA, zorder=3)
    for _, linha in pontos.drop(pequenas.index).iterrows():
        ponto = linha["ponto"]
        escuro = abs(linha["variacao_pp"]) > 0.55 * vmax
        ax.text(ponto.x, ponto.y, f"{linha['sg_uf']}\n{_num(linha['variacao_pp'], 1, sinal=True)}", ha="center",
                va="center", fontsize=6.5, color="#ffffff" if escuro else TINTA, linespacing=1.0, zorder=3)
    ax.set_xlim(minx - 0.5, x_lab + 7.0)
    cax = fig.add_axes([0.84, 0.25, 0.02, 0.45])
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=CMAP_DIV), cax=cax)
    cb.set_ticks([-vmax, 0, vmax])
    cb.set_ticklabels([_num(-vmax, 1, True), "0", _num(vmax, 1, True)])
    cb.outline.set_visible(False)
    cb.ax.tick_params(labelsize=8, colors=TINTA_2, length=0)
    cb.set_label("p.p.", fontsize=8, color=TINTA_2)
    _rodape(fig, "Fonte: TSE (2018 e 2022), IBGE (malha estadual de 2020). Taxa, não contagem. Rótulo em cada UF: "
                 "variação em pontos percentuais.")
    return _salvar(fig, "fig_08_mapa_uf_variacao_2018_2022")


def fig_09_limpeza_antes_depois() -> Path:
    e = etapas_de_linhas(pd.read_csv(REPORTS / "log_limpeza.csv"))
    a = resumo_ausentes(pd.read_csv(REPORTS / "ausentes_antes_depois.csv"))
    perfil = a["perfil"]

    titulo = (f"A limpeza reduziu a base de {_inteiro(e['bronze'])} para {_inteiro(e['silver'])} linhas; nas colunas "
              f"de perfil que existem antes e depois, nenhum ausente passa de {_pct_do_relatorio(a['maior_depois'])}")
    subtitulo = ("Esquerda: linhas, só nas etapas que mudam o número de linhas. Direita: % de linhas com valor ausente "
                 "antes (bronze) e depois (silver). Cada painel tem a sua unidade.")

    fig = Figure(figsize=(12.5, 6), facecolor=SUPERFICIE)
    topo = _moldura(fig, titulo, subtitulo)

    # (a) linhas: cascata da bronze à silver
    axa = fig.add_axes([0.27, 0.13, 0.30, topo - 0.13 - 0.05])
    _eixos_limpos(axa, "x")
    rotulos = (["Bronze (base bruta)"]
               + ["\n".join(textwrap.wrap(p.split(" ", 1)[1], 26)) for p, _ in e["etapas"]]
               + ["Silver (após a limpeza)"])
    y = np.arange(len(rotulos))[::-1]
    axa.barh(y[0], e["bronze"], height=0.6, color=TINTA_3, zorder=3)
    axa.text(e["bronze"] * 1.01, y[0], _inteiro(e["bronze"]), va="center", fontsize=9, color=TINTA)
    nivel = e["bronze"]
    for k, (_, delta) in enumerate(e["etapas"], start=1):
        axa.barh(y[k], delta, left=nivel - delta, height=0.6, color=AZUL, zorder=3)
        axa.text(nivel * 1.01, y[k], f"−{_inteiro(delta)}", va="center", fontsize=9, color=TINTA)
        nivel -= delta
    axa.barh(y[-1], e["silver"], height=0.6, color=TINTA_3, zorder=3)
    axa.text(e["silver"] * 1.01, y[-1], _inteiro(e["silver"]), va="center", fontsize=9, color=TINTA)
    axa.set_yticks(y)
    axa.set_yticklabels(rotulos, fontsize=8.5, color=TINTA_2)
    axa.set_xlim(0, e["bronze"] * 1.25)
    axa.set_ylim(-0.6, len(rotulos) - 0.4)
    axa.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{_num(v / 1e6, 0)} mi"))
    axa.set_title("Linhas", loc="left", fontsize=10, color=TINTA, fontweight="bold")

    # (b) ausentes (%): antes × depois por coluna de perfil
    axb = fig.add_axes([0.70, 0.13, 0.26, topo - 0.13 - 0.05])
    _eixos_limpos(axb, "x")
    yb = np.arange(len(perfil))[::-1]
    for yi, (_, lin) in zip(yb, perfil.iterrows()):
        axb.plot([lin["pct_ausente_antes"], lin["pct_ausente_depois"]], [yi, yi], color=BASE, linewidth=2, zorder=2)
    axb.scatter(perfil["pct_ausente_antes"], yb, s=70, color=TINTA_3, edgecolor=SUPERFICIE, linewidth=2, zorder=3,
                label="Antes (bronze)")
    axb.scatter(perfil["pct_ausente_depois"], yb, s=70, color=AZUL, edgecolor=SUPERFICIE, linewidth=2, zorder=4,
                label="Depois (silver)")
    for yi, (_, lin) in zip(yb, perfil.iterrows()):
        axb.text(max(lin["pct_ausente_antes"], lin["pct_ausente_depois"]) + 0.05, yi,
                 f"{_pct_do_relatorio(lin['pct_ausente_antes'])} → {_pct_do_relatorio(lin['pct_ausente_depois'])}",
                 va="center", fontsize=8, color=TINTA)
    axb.set_yticks(yb)
    axb.set_yticklabels([CAMPOS_PERFIL[c] for c in perfil["coluna"]], fontsize=9, color=TINTA_2)
    axb.set_xlim(0, 1.5)
    axb.set_ylim(-0.6, len(perfil) - 0.4)
    axb.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{_num(v, 1)}%"))
    axb.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=TINTA_2)
    axb.set_title("Ausentes por coluna (% das linhas)", loc="left", fontsize=10, color=TINTA, fontweight="bold")
    _rodape(fig, "Fonte: reports/log_limpeza.csv e reports/ausentes_antes_depois.csv. A medida conta linhas, e a "
                 "reagregação de 2024 reduziu as linhas desse ano; por isso o peso dos outros anos cresce. Colunas "
                 "que existem só antes ou só depois (cor/raça, Libras etc.) ficam fora de (b). Ausente = nulo ou "
                 "sentinela (bronze) e nulo ou NÃO INFORMADO (silver).")
    return _salvar(fig, "fig_09_limpeza_antes_depois")


# ---------------------------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------------------------

FUNCOES_FIGURAS = [fig_01_abstencao_por_eleicao, fig_02_abstencao_por_uf, fig_03_abstencao_por_faixa_etaria,
                   fig_04_distribuicao_por_regiao, fig_05_taxa_x_pib_populacao, fig_06_faixa_x_escolaridade,
                   fig_07_mapa_municipal, fig_08_mapa_uf_variacao, fig_09_limpeza_antes_depois]


def gerar_todas() -> list[Path]:
    return [f() for f in FUNCOES_FIGURAS]


def main() -> None:
    for caminho in gerar_todas():
        print(caminho)


if __name__ == "__main__":
    main()
