# Projeto Big Data – Etapa 1 (TSE: Comparecimento e Abstenção) – Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cumprir as 5 semanas da Etapa 1 (proposta → coleta → EDA → limpeza → visualizações/relatório) com a base `perfil_comparecimento_abstencao` do TSE (eleições 2018, 2020, 2022, 2024), num repositório público e reprodutível no GitHub.

**Architecture:** Pipeline medalhão em Python. `src/coleta.py` baixa os ZIPs do TSE e grava a camada bronze em Parquet particionado por `ano`/`sg_uf`; `src/ibge.py` busca a segunda fonte (população e PIB pela API SIDRA, municípios pela API de localidades, de-para TSE→IBGE); `src/limpeza.py` produz a silver e o log de limpeza; `src/agregacao.py` produz a gold (taxas por município/UF/ano); `src/graficos.py` gera as figuras. O notebook `notebooks/etapa1.ipynb` chama essas funções e narra EDA, limpeza e resultados.

**Tech Stack:** Python 3.11+, pyarrow, duckdb, pandas, requests, matplotlib/seaborn, geobr + geopandas, jupyter, pytest, pypandoc_binary (Markdown → DOCX/PDF), gh CLI.

**Spec:** `Projeto - Descrição da Etapa 1 (2).pdf` (raiz do repositório).

## Global Constraints

- Base com ≥ 5 milhões de linhas e ≥ 3 anos de cobertura (recorte: 2018, 2020, 2022, 2024, todas as UFs + exterior `ZZ`).
- Integração com pelo menos uma segunda fonte (IBGE: população, PIB, malha municipal).
- Estrutura obrigatória: `data/bronze`, `data/silver`, `data/gold`, `notebooks`, `src`, `reports` e um `README.md` explicando a reprodução.
- Dados brutos grandes **não** vão para o Git (`data/**` no `.gitignore`, só `.gitkeep`); `python src/coleta.py` recria tudo.
- Script de coleta: `src/coleta.py`, com repetição em caso de erro e pulando arquivo já baixado.
- Parquet particionado por ano e/ou UF; comparar tamanho em disco e tempo de leitura CSV × Parquet.
- Colunas em `snake_case`, sem acentos.
- Log de limpeza em tabela: `problema · decisao · justificativa · linhas_afetadas`.
- Mínimo de 8 visualizações, cada uma com título que **afirma a resposta** (ex.: "Abstenção dos eleitores com 70+ anos passou de X% para Y%"). Tipos obrigatórios: série temporal, barras ordenadas, distribuição com comparação entre grupos, relação entre duas variáveis, mapa coroplético por **taxa**, antes × depois da limpeza.
- Relatório com no máximo 10 páginas, nesta ordem: contexto e perguntas → fonte e volume → problemas de qualidade e decisões → resultados com visualizações → limitações → próximos passos para a Parte 2.
- Todo texto em prosa (README, ficha, dicionário, log, markdown do notebook, relatório) passa pela skill `humanizer`, **atualizada antes do primeiro uso** (Task 1).
- Delegação: **[Haiku]** = subagente com `model: "haiku"` (tarefas simples e mecânicas); **[Sonnet]** = subagente com `model: "sonnet"` (código com lógica, mas especificação fechada); **[Opus]** = só as tarefas que exigem julgamento analítico (EDA, decisões de limpeza, relatório).

## Review Focus

1. **Layout diferente entre anos** (colunas novas como `CD_IDENTIDADE_GENERO`, `QT_*_TTE`, `CD_QUILOMBOLA` só nos anos recentes): a conversão unifica os esquemas e preenche com nulo, sem quebrar. Teste em Task 3.
2. **Valores sentinela do TSE** (`#NULO#`, `#NE#`, `-1`, `-3`): viram ausentes, nunca categoria ou número válido. Teste em Task 5.
3. **Download interrompido / ZIP corrompido:** o script detecta (`zipfile.BadZipFile`), apaga e baixa de novo. Teste em Task 2.
4. **Dupla contagem por turno:** somar `qt_aptos` de 1º e 2º turno duplica o eleitorado. As taxas anuais usam só o 1º turno; o 2º é analisado à parte. Teste em Task 6.
5. **Município sem par no IBGE** (exterior `ZZ`, código TSE sem correspondência): mantido na silver com `cd_municipio_ibge` nulo, contado no log e fora dos mapas. Teste em Task 4.

---

## Estrutura de arquivos

```
.gitignore  README.md  requirements.txt  pytest.ini
data/bronze/.gitkeep  data/silver/.gitkeep  data/gold/.gitkeep
src/config.py        # anos, URLs, caminhos, sentinelas (constantes únicas)
src/coleta.py        # download TSE + extração + metadados + Parquet bronze + benchmark
src/ibge.py          # SIDRA (população/PIB), localidades, de-para TSE→IBGE
src/limpeza.py       # funções de limpeza + LogLimpeza
src/agregacao.py     # tabelas gold (taxas)
src/graficos.py      # uma função por figura
notebooks/etapa1.ipynb
reports/ficha_proposta.md  reports/dicionario_dados.md  reports/metadados_coleta.csv
reports/benchmark_csv_parquet.csv  reports/log_limpeza.csv  reports/figuras/*.png
reports/relatorio.md  reports/relatorio.docx (+ .pdf)
tests/test_coleta.py  tests/test_ibge.py  tests/test_limpeza.py  tests/test_agregacao.py
tests/fixtures/amostra_tse.csv   # ~30 linhas reais (latin-1, ;) incluindo sentinelas
```

---

### Task 0 [Sonnet]: Verificar a fonte e confirmar volume (antes de qualquer código)

Decide se o recorte atende ≥ 5 M linhas e fixa URLs reais. Nada de código de produção aqui.

- [ ] **Step 1:** Abrir `https://dadosabertos.tse.jus.br/dataset/` → conjuntos "Resultados 20XX" e localizar o recurso *Perfil do eleitorado – comparecimento e abstenção*. Confirmar o padrão de URL esperado `https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_comparecimento_abstencao/perfil_comparecimento_abstencao_{ano}.zip` para 2018, 2020, 2022, 2024 (HEAD de cada URL deve dar 200).
- [ ] **Step 2:** Anotar licença (CC-BY / termos do portal), link do leiaute (PDF "LEIAME" dentro do ZIP) e tamanho de cada ZIP.
- [ ] **Step 3:** Baixar só 2024, contar linhas (`duckdb: SELECT count(*) FROM read_csv(..., delim=';', encoding='latin-1')`). Estimativa total = soma dos 4 anos. **Critério:** ≥ 5.000.000. Se não atingir, acrescentar 2014 e 2016 em `config.ANOS`.
- [ ] **Step 4:** Confirmar as fontes IBGE: SIDRA tabela 6579 (estimativa de população: 2018, 2020, 2021, 2024), tabela 4709 (Censo 2022), tabela 5938 (PIB municipal), API `servicodados.ibge.gov.br/api/v1/localidades/municipios`, e um de-para TSE→IBGE com download direto (candidato: CSV do repositório `betafcc/Municipios-Brasileiros-TSE`; validar que cobre ~5.570 municípios).
- [ ] **Step 5:** Registrar tudo em `reports/fontes.md` (vira insumo de README, dicionário e relatório).

### Task 1 [Haiku]: Repositório, estrutura e atualização do humanizer

**Files:** Create `.gitignore`, `requirements.txt`, `pytest.ini`, `data/{bronze,silver,gold}/.gitkeep`, `notebooks/.gitkeep`, `reports/figuras/.gitkeep`, `src/__init__.py`, `src/config.py`, `README.md` (esqueleto).

**Interfaces – Produces (`src/config.py`):**
`RAIZ: Path`, `BRONZE`, `SILVER`, `GOLD`, `REPORTS`, `FIGURAS: Path`; `ANOS: list[int] = [2018, 2020, 2022, 2024]`; `URL_TSE: str` com `{ano}`; `SENTINELAS: set[str] = {"#NULO#", "#NULO", "#NE#", "#NE", "-1", "-3"}`; `SEP=";"`, `ENCODING="latin-1"`.

- [ ] **Step 1:** `git init`, criar a estrutura, `.gitignore` com `data/**` + `!data/**/.gitkeep`, `.venv/`, `__pycache__/`, `.ipynb_checkpoints/`, ZIP/CSV/Parquet.
- [ ] **Step 2:** `requirements.txt` com versões fixas (pyarrow, duckdb, pandas, requests, matplotlib, seaborn, geobr, geopandas, jupyter, nbconvert, pytest, pypandoc_binary). Criar `.venv`, `pip install -r requirements.txt`, rodar `python -c "import duckdb, pyarrow, geobr"` → sem erro.
- [ ] **Step 3:** Atualizar o humanizer: localizar a skill (`~/.claude/skills/humanizer`); se for clone git, `git -C <dir> pull`; senão, baixar a versão atual do repositório de origem indicado no `SKILL.md` e substituir. Registrar a versão/commit no relatório da tarefa.
- [ ] **Step 4:** `gh auth status` → logado. `gh repo create <nome> --public --source . --remote origin`. Nome sugerido: `bigdata-tse-abstencao`.
- [ ] **Step 5:** Commit `chore: estrutura do projeto` e `git push -u origin main`.

### Task 2 [Sonnet]: Coleta TSE com retry, verificação e metadados

**Files:** Create `src/coleta.py`, `tests/test_coleta.py`, `tests/fixtures/amostra_tse.csv`.

**Interfaces – Produces:**
- `baixar(url: str, destino: Path, tentativas: int = 5, espera: float = 2.0) -> Path` — pula se `destino` existe e é ZIP válido; ZIP inválido é apagado e rebaixado; backoff exponencial; grava em `destino.with_suffix(".part")` e renomeia no fim.
- `extrair_csvs(zip_path: Path, pasta: Path) -> list[Path]` — só os `*.csv` (ignora `_BRASIL` se houver arquivos por UF, para não duplicar; decidir conforme Task 0).
- `registrar_metadados(arquivos: list[Path], url: str, ano: int) -> pd.DataFrame` — colunas `ano, url, arquivo, data_download, n_linhas, n_colunas, tamanho_bytes`; anexa em `reports/metadados_coleta.csv`.
- CLI: `python src/coleta.py [--anos 2018 2020 ...]` executa download → extração → metadados → Task 3.

- [ ] **Step 1: Testes que falham**
  - `test_baixar_pula_arquivo_existente`: ZIP válido já presente → `requests.get` (mock) não é chamado.
  - `test_baixar_refaz_zip_corrompido`: arquivo com bytes lixo → é rebaixado; resultado é ZIP válido.
  - `test_baixar_repete_apos_falha`: mock levanta `ConnectionError` 2× e depois responde → sucesso com 3 chamadas.
  - `test_baixar_desiste_apos_tentativas`: sempre falha → levanta exceção após `tentativas` chamadas.
  - `test_metadados_conta_linhas_colunas`: fixture `amostra_tse.csv` → `n_linhas` = linhas de dados (sem cabeçalho), `n_colunas` correto.
- [ ] **Step 2:** `pytest tests/test_coleta.py -v` → FAIL (funções não existem).
- [ ] **Step 3:** Implementar. Download em streaming (`iter_content`, chunk 1 MiB), `timeout=60`.
- [ ] **Step 4:** `pytest tests/test_coleta.py -v` → PASS.
- [ ] **Step 5:** Rodar de verdade `python src/coleta.py`; conferir `reports/metadados_coleta.csv` com 4 anos e soma de `n_linhas` ≥ 5 M.
- [ ] **Step 6:** Commit `feat: coleta automatizada do TSE com retry e metadados`.

### Task 3 [Sonnet]: CSV → Parquet bronze particionado + benchmark

**Files:** Modify `src/coleta.py`; Test `tests/test_coleta.py`.

**Interfaces – Produces:**
- `csv_para_parquet(csvs: list[Path], ano: int, destino: Path = BRONZE) -> int` — lê com `pyarrow.csv` (`delimiter=";"`, `encoding="latin1"`, **todas as colunas como string** na bronze), adiciona `ano`, grava `pyarrow.dataset.write_dataset` particionado em `ano`/`sg_uf` (hive). Retorna linhas gravadas.
- `ler_bronze() -> pyarrow.dataset.Dataset` com `schema` unificado (`unify_schemas`, colunas ausentes = nulo).
- `benchmark(csv: Path, parquet_dir: Path) -> dict` — `tamanho_csv_mb, tamanho_parquet_mb, reducao_pct, t_leitura_csv_s, t_leitura_parquet_s`; salva `reports/benchmark_csv_parquet.csv`.

- [ ] **Step 1: Testes que falham**
  - `test_parquet_preserva_linhas`: fixture → linhas gravadas == linhas da fixture.
  - `test_parquet_acentos_latin1`: um `NM_MUNICIPIO` com acento (ex.: "SÃO PAULO") sai idêntico do Parquet.
  - `test_esquemas_diferentes_unificam`: duas fixtures, uma sem `QT_COMPARECIMENTO_TTE` → `ler_bronze().to_table()` tem a coluna, nula para o ano antigo (Review Focus 1).
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS.
- [ ] **Step 5:** Rodar sobre os 4 anos; benchmark com o maior CSV. Esperado: Parquet bem menor e leitura mais rápida; registrar números.
- [ ] **Step 6:** Commit `feat: bronze em Parquet particionado e benchmark`.

### Task 4 [Haiku]: Segunda fonte – IBGE

**Files:** Create `src/ibge.py`, `tests/test_ibge.py`.

**Interfaces – Produces** (cada função salva o resultado em `data/bronze/ibge/*.parquet` e reaproveita se já existir):
- `populacao_municipios(anos: list[int]) -> pd.DataFrame` — colunas `cd_municipio_ibge: str(7), ano: int, populacao: int`. 2022 vem do Censo (tabela 4709); os demais da 6579. Para anos sem estimativa, usar o ano mais próximo e registrar a escolha.
- `pib_municipios() -> pd.DataFrame` — `cd_municipio_ibge, ano, pib_per_capita: float` (tabela 5938, ano mais recente disponível).
- `municipios_ibge() -> pd.DataFrame` — `cd_municipio_ibge, nm_municipio, sg_uf, nm_regiao` (API de localidades, JSON).
- `depara_tse_ibge() -> pd.DataFrame` — `cd_municipio_tse: str(5), cd_municipio_ibge: str(7)` (fonte decidida na Task 0).
- Função auxiliar `_get_json(url) -> list|dict` com o mesmo retry da coleta (reutilizar a lógica de `coleta.baixar` ou extrair um helper comum — não duplicar).

- [ ] **Step 1: Testes que falham** (com respostas JSON mockadas, sem rede)
  - `test_sidra_parse_populacao`: JSON SIDRA de exemplo (primeira linha é cabeçalho, valores como string, "..." para ausente) → DataFrame tipado, linha de cabeçalho descartada, "..." vira NaN.
  - `test_depara_codigos_com_zeros`: códigos TSE com zero à esquerda (ex.: `"01120"`) preservados como string de 5 dígitos.
  - `test_municipios_regiao`: JSON de localidades → `nm_regiao` preenchido.
- [ ] **Step 2:** FAIL. **Step 3:** Implementar. **Step 4:** PASS.
- [ ] **Step 5:** Rodar de verdade; conferir ~5.570 municípios em cada tabela.
- [ ] **Step 6:** Commit `feat: integração IBGE (população, PIB, municípios, de-para)`.

### Task 5 [Haiku]: Dicionário de dados + ficha de proposta (Semana 1 e 2)

**Files:** Create `reports/dicionario_dados.md`, `reports/ficha_proposta.md`; Modify `README.md`.

- [ ] **Step 1:** Dicionário em português com uma linha por variável **usada**: `variavel (original) · variavel (snake_case) · tipo · descricao · dominio` (códigos e rótulos de gênero, faixa etária, escolaridade, estado civil, cor/raça; faixa de valores das `qt_*`; sentinelas). Fonte: LEIAME do ZIP + `SELECT DISTINCT` na bronze. Incluir as colunas do IBGE.
- [ ] **Step 2:** Ficha de proposta: tema, fonte (URL + licença), recorte (2018–2024, todas as UFs + exterior), estimativa de volume (número real da Task 2), e as 5 perguntas:
  1. A abstenção cresceu de 2018 a 2024, e como se comportam eleições gerais (2018/2022) × municipais (2020/2024) e 1º × 2º turno?
  2. Quais faixas etárias se abstêm mais, e quanto pesam os grupos de voto facultativo (16–17 e 70+)?
  3. Existe gradiente de abstenção por escolaridade?
  4. Quais UFs e regiões têm as maiores taxas de abstenção, e a eleição de 2020 (pandemia) foi um ponto fora da curva?
  5. Municípios mais populosos ou com maior PIB per capita se abstêm mais ou menos?
- [ ] **Step 3:** Passar ambos os textos pela skill `humanizer`.
- [ ] **Step 4:** Commit `docs: ficha de proposta e dicionário de dados`.

### Task 6 [Opus]: EDA no notebook (Semana 3)

**Files:** Create `notebooks/etapa1.ipynb` (seções 1–2); Create `src/agregacao.py` (parcial); Test `tests/test_agregacao.py`.

**Interfaces – Produces:** `taxa_abstencao(df: pd.DataFrame, por: list[str], turno: int = 1) -> pd.DataFrame` — filtra `nr_turno == turno`, soma `qt_aptos` e `qt_abstencao`, devolve `por + [qt_aptos, qt_abstencao, taxa_abstencao]` (fração 0–1).

- [ ] **Step 1: Teste que falha** `test_taxa_nao_soma_turnos`: 1º turno 100 aptos/20 abst., 2º turno 100/30, mesmo município → `taxa_abstencao(df, ["cd_municipio"])` dá `qt_aptos == 100`, `taxa == 0.20` (Review Focus 4). E `test_taxa_ignora_aptos_zero`: grupo com `qt_aptos == 0` não gera divisão por zero (taxa NaN).
- [ ] **Step 2:** FAIL → implementar → PASS.
- [ ] **Step 3:** Notebook, seção EDA (consultas DuckDB sobre `data/bronze/**/*.parquet`):
  - Visão geral: linhas/colunas por ano, tipos inferidos × esperados (tabela), memória por coluna (`df.memory_usage(deep=True)` numa amostra de 1 M linhas).
  - Qualidade: % ausentes por coluna e por ano (contando sentinelas como ausentes), duplicados exatos, valores fora do domínio do dicionário, consistência `qt_aptos == qt_comparecimento + qt_abstencao`.
  - Univariada: `describe` das `qt_*`, frequências/cardinalidade das categóricas, outliers por IQR e z-score em `taxa_abstencao` por município, com discussão (erro × fenômeno real, ex.: municípios pequenos, exterior).
  - Bivariada/temporal: taxa por ano e turno, por UF/região, faixa etária × escolaridade (tabela cruzada), correlação entre taxas e variáveis IBGE.
  - Respostas preliminares às 5 perguntas.
  - **Fecha com lista priorizada de problemas de qualidade** (numerada; cada item vira linha do log na Task 7).
- [ ] **Step 4:** `jupyter nbconvert --execute --to notebook --inplace notebooks/etapa1.ipynb` roda sem erro.
- [ ] **Step 5:** Markdown do notebook pela `humanizer`. Commit `feat: EDA e diagnóstico de qualidade`.

### Task 7 [Opus]: Limpeza, integração e silver (Semana 4)

**Files:** Create `src/limpeza.py`, `tests/test_limpeza.py`; Modify notebook (seção 3).

**Interfaces – Produces:**
- `class LogLimpeza` com `registrar(problema: str, decisao: str, justificativa: str, antes: int, depois: int) -> None` e `salvar(path=REPORTS/"log_limpeza.csv")`; coluna `linhas_afetadas = antes - depois` (ou contagem de células alteradas quando a decisão marca em vez de remover — campo explícito).
- `padronizar_colunas(df) -> df` — `snake_case`, sem acento (`unicodedata`).
- `tratar_sentinelas(df, log) -> df` — `SENTINELAS` → nulo.
- `tipar(df) -> df` — `qt_*` → `int32`, códigos → `category`, `ano`/`nr_turno` → `int16`/`int8`, `dt_geracao` → data.
- `harmonizar_anos(df, log) -> df` — rótulos que mudaram entre anos mapeados para um vocabulário único (definido a partir da EDA).
- `remover_duplicados(df, log) -> df`; `marcar_inconsistentes(df, log) -> df` (flag `inconsistente` quando `aptos != comp + abst`; outliers recebem flag por regra explícita, não são apagados).
- `derivar(df) -> df` — `nm_regiao`, `faixa_etaria_agrupada` (16–17, 18–24, 25–34, 35–44, 45–59, 60–69, 70+), `voto_facultativo: bool`, `tipo_eleicao` (geral/municipal).
- `integrar_ibge(df, log) -> df` — junta de-para + população + PIB; registra no log quantos registros/municípios não casaram (Review Focus 5).
- `salvar_silver(df)` — Parquet particionado `ano`/`sg_uf` em `data/silver`.

- [ ] **Step 1: Testes que falham**
  - `test_snake_case_sem_acento`: `"DS_GRAU_ESCOLARIDADE"`, `"Nº Seção"` → `"ds_grau_escolaridade"`, `"no_secao"`.
  - `test_sentinelas_viram_nulo`: `"#NULO#"`, `"#NE#"`, `"-3"` → nulo; `"0"` permanece (Review Focus 2).
  - `test_duplicados_registrados_no_log`: 3 linhas, 1 duplicada → 2 linhas, log com `linhas_afetadas == 1`.
  - `test_faixa_facultativa`: 16 anos e 72 anos → `voto_facultativo` True; 30 anos → False.
  - `test_integracao_conta_nao_casados`: município `ZZ` sem par → `cd_municipio_ibge` nulo, linha mantida, log registra 1 não casado.
- [ ] **Step 2:** FAIL → implementar → PASS (`pytest -v` inteiro verde).
- [ ] **Step 3:** Notebook seção Limpeza: pipeline aplicado ano a ano (para caber na memória), tabela `log_limpeza.csv` exibida, linhas antes/depois por etapa. Cada item da lista priorizada da EDA tem uma linha no log.
- [ ] **Step 4:** Texto das justificativas pela `humanizer`. Commit `feat: limpeza, integração IBGE e camada silver`.

### Task 8 [Haiku]: Camada gold

**Files:** Modify `src/agregacao.py`, `tests/test_agregacao.py`.

**Interfaces – Produces** (todas usam `taxa_abstencao`, salvam em `data/gold/*.parquet`):
`gold_municipio_ano()` (+ população, PIB per capita, `abstencoes_por_100k_hab = qt_abstencao / populacao * 100_000`), `gold_uf_ano()`, `gold_perfil_ano()` (faixa etária × escolaridade × gênero), `gold_turnos()`.

- [ ] **Step 1:** Teste `test_taxa_100k`: 50 abstenções, população 10.000 → 500.0. FAIL → implementar → PASS.
- [ ] **Step 2:** Gerar as 4 tabelas. Commit `feat: camada gold`.

### Task 9 [Haiku → revisão Sonnet]: Visualizações (Semana 5)

**Files:** Create `src/graficos.py`; Modify notebook (seção 4). Uma função por figura, `def fig_XX(gold...) -> Path` salvando PNG 150 dpi em `reports/figuras/`. O **título de cada figura é a resposta**, escrita depois de olhar o número (o Sonnet revisa títulos e valores).

| # | Tipo obrigatório | Figura |
|---|---|---|
| 01 | Série temporal | Taxa de abstenção nacional por eleição (2018–2024), 1º e 2º turno |
| 02 | Barras ordenadas | Taxa de abstenção por UF, último ano, ordenada |
| 03 | Barras ordenadas | Taxa por faixa etária, destacando grupos facultativos |
| 04 | Distribuição com grupos | Boxplot/violino da taxa municipal por região |
| 05 | Relação entre variáveis | Dispersão taxa municipal × PIB per capita (log) e/ou população |
| 06 | Mapa de calor | Taxa por faixa etária × escolaridade |
| 07 | Coroplético (taxa) | Mapa municipal da taxa de abstenção (geobr), 1º turno do último ano |
| 08 | Coroplético (taxa) | Mapa por UF da variação 2018→2022 em pontos percentuais |
| 09 | Antes × depois | Linhas/registros por etapa de limpeza e % ausentes antes × depois |

- [ ] **Step 1:** Implementar as 9 funções; notebook chama todas.
- [ ] **Step 2:** `nbconvert --execute` sem erro; 9 PNGs em `reports/figuras/`.
- [ ] **Step 3:** Revisão Sonnet: cada título bate com o número do gráfico; mapas usam taxa, não contagem.
- [ ] **Step 4:** Commit `feat: visualizações`.

### Task 10 [Opus]: Relatório, README final e entrega

**Files:** Create `reports/relatorio.md` → `reports/relatorio.docx` e `.pdf`; Modify `README.md`.

- [ ] **Step 1:** Relatório na ordem exigida: contexto e perguntas → fonte e volume (total coletado, redução do Parquet, dificuldades da fonte: mudança de layout, sentinelas, de-para de municípios) → problemas de qualidade e decisões (resumo do log) → resultados com as figuras, respondendo às 5 perguntas → limitações → próximos passos para a Parte 2.
- [ ] **Step 2:** Converter com `pypandoc` para DOCX e conferir **≤ 10 páginas**; gerar PDF.
- [ ] **Step 3:** README: o que é o projeto, estrutura de pastas, como reproduzir (`python -m venv .venv`, `pip install -r requirements.txt`, `python src/coleta.py`, `python src/ibge.py`, executar o notebook), tempo e espaço em disco esperados, links para os entregáveis.
- [ ] **Step 4:** Relatório e README pela `humanizer` (versão atualizada na Task 1).
- [ ] **Step 5: Verificação final de reprodutibilidade:** clonar o repo numa pasta temporária, rodar o passo a passo do README do zero, `pytest` verde, notebook executa. Commit `docs: relatório final e README`, `git push`.

---

## Mapa semana → tarefas

| Semana | Entregável | Tarefas |
|---|---|---|
| 1 | Ficha da proposta | 0, 1, 5 (ficha) |
| 2 | Coleta + dicionário + bronze Parquet | 2, 3, 4, 5 (dicionário) |
| 3 | EDA com diagnóstico | 6 |
| 4 | Silver + log de limpeza | 7, 8 |
| 5 | Notebook final + relatório | 9, 10 |
