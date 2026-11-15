# Abstenção eleitoral no Brasil (TSE 2018 a 2024 + IBGE): Etapa 1 de Big Data

Projeto da disciplina de Big Data sobre comparecimento e abstenção nas eleições de 2018, 2020, 2022 e 2024. A base principal é o perfil de comparecimento e abstenção do TSE (31.633.820 linhas, 8,3 GB em CSV), cruzada com população, PIB e lista de municípios do IBGE. O pipeline baixa os dados, converte para Parquet (bronze), limpa e integra (silver), agrega (gold) e gera as nove figuras do relatório. As cinco perguntas de pesquisa estão na [ficha de proposta](reports/ficha_proposta.md), e as respostas, no [relatório](reports/relatorio.pdf).

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `data/bronze/` | Dados brutos: ZIPs e CSVs do TSE (`tse/`), Parquet particionado por `ano` e `SG_UF` (`tse_parquet/`), tabelas do IBGE (`ibge/`) e malhas para os mapas (`geo/`). Não vai para o Git. |
| `data/silver/` | Base tratada do TSE com IBGE integrado, Parquet particionado por `ano` e `sg_uf`. Não vai para o Git. |
| `data/gold/` | Quatro tabelas agregadas (município, UF, perfil e turnos) usadas nas figuras. Não vai para o Git. |
| `notebooks/` | `etapa1.ipynb`: EDA com diagnóstico de qualidade, limpeza e visualizações. |
| `src/` | Código do pipeline: `coleta.py`, `ibge.py`, `limpeza.py`, `agregacao.py`, `graficos.py` e `config.py` (caminhos e constantes). |
| `reports/` | Relatório, ficha, dicionário, metadados, benchmark, log de limpeza, ausentes e figuras. |
| `tests/` | Testes com pytest e uma amostra pequena do TSE em `tests/fixtures/`. |
| `docs/` | Planos de trabalho do projeto. |

## Como reproduzir

Os comandos abaixo usam o Git Bash no Windows, onde o Python do ambiente fica em `.venv/Scripts/python.exe`. No Linux ou no macOS, troque por `.venv/bin/python`. Todos rodam a partir da raiz do repositório.

1. Criar o ambiente com Python 3.11 e instalar as dependências (com [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv venv --python 3.11 .venv
   uv pip install --python .venv/Scripts/python.exe -r requirements.txt
   ```

   Sem o uv, `python -m venv .venv` e `.venv/Scripts/python.exe -m pip install -r requirements.txt` também funcionam, desde que o Python seja 3.11.

2. Baixar o TSE e gerar a bronze em Parquet, mais o benchmark CSV × Parquet:

   ```bash
   .venv/Scripts/python.exe src/coleta.py              # os quatro anos; ou --anos 2024
   .venv/Scripts/python.exe src/coleta.py --benchmark
   ```

3. Baixar as tabelas do IBGE e o de-para de municípios TSE → IBGE:

   ```bash
   .venv/Scripts/python.exe src/ibge.py
   ```

4. Construir a silver e o log de limpeza, depois a gold e as figuras:

   ```bash
   .venv/Scripts/python.exe src/limpeza.py             # os quatro anos; ou --anos 2024
   .venv/Scripts/python.exe src/agregacao.py
   .venv/Scripts/python.exe src/graficos.py
   ```

   `graficos.py` precisa dos quatro anos na silver e na gold: a Figura 1 compara as quatro eleições e a Figura 8 compara 2018 e 2022. Com só um ano processado, ele para com `KeyError`.

5. Registrar o kernel do Jupyter usado pelo notebook e executá-lo:

   ```bash
   .venv/Scripts/python.exe -m ipykernel install --user --name bigdata-tse --display-name "Python (bigdata-tse)"
   .venv/Scripts/python.exe -m jupyter nbconvert --to notebook --execute --inplace notebooks/etapa1.ipynb
   ```

   O notebook lê a bronze, a silver e a gold. Ele só reconstrói a silver se ela não existir (ou com `REFAZER_SILVER = True` na seção 3).

6. Rodar os testes:

   ```bash
   .venv/Scripts/python.exe -m pytest -q
   ```

Todos os passos podem ser repetidos. A coleta pula ZIPs válidos já baixados e repete downloads que falham (até cinco tentativas, com espera crescente). A limpeza apaga e regrava a partição de cada ano.

### Tempo e espaço em disco

Medidos numa máquina com 15,4 GB de RAM e banda larga doméstica:

| Passo | Tempo | Disco gerado |
|---|---|---|
| Ambiente (`uv`) | ~10 s | ~1 GB em `.venv/` |
| `coleta.py`, quatro anos | ~8 a 10 min (2024 sozinho: ~2,5 min) | 666 MB de ZIPs, 8,3 GB de CSVs, 218 MB de Parquet |
| `coleta.py --benchmark` | ~20 s | `reports/benchmark_csv_parquet.csv` |
| `ibge.py` | ~5 s | ~1 MB |
| `limpeza.py`, quatro anos | 7 a 12 min (2024 sozinho: ~2 min) | 198 MB de silver |
| `agregacao.py` | menos de 10 s | 1,9 MB de gold |
| `graficos.py` | ~1 min | nove PNG em `reports/figuras/` e ~21 MB de malhas do IBGE em `data/bronze/geo/` |
| notebook | ~7 min | nada novo (reaproveita a silver) |
| `pytest` | ~3 s | nada |

O total em disco fica perto de 9,4 GB, quase tudo nos CSVs extraídos (fora o ambiente virtual).

## Entregáveis

- Relatório final: [PDF](reports/relatorio.pdf), [DOCX](reports/relatorio.docx) e [fonte em Markdown](reports/relatorio.md)
- Notebook: [notebooks/etapa1.ipynb](notebooks/etapa1.ipynb)
- [Ficha de proposta](reports/ficha_proposta.md) e [fontes verificadas](reports/fontes.md)
- [Dicionário de dados](reports/dicionario_dados.md)
- [Metadados da coleta](reports/metadados_coleta.csv): URL, data, linhas, colunas e bytes de cada arquivo
- [Benchmark CSV × Parquet](reports/benchmark_csv_parquet.csv)
- [Log de limpeza](reports/log_limpeza.csv): problema, decisão, justificativa, unidade e linhas afetadas
- [Ausentes antes e depois da limpeza](reports/ausentes_antes_depois.csv)
- [Figuras](reports/figuras/): nove PNG, uma por pergunta e uma do efeito da limpeza

## Fontes e licenças

TSE, [Portal de Dados Abertos](https://dadosabertos.tse.jus.br), conjunto "Comparecimento e Abstenção" (CC-BY). IBGE, SIDRA (tabelas 6579, 4709 e 5938) e API de localidades. De-para de municípios TSE → IBGE: [betafcc/Municipios-Brasileiros-TSE](https://github.com/betafcc/Municipios-Brasileiros-TSE), com um par acrescentado no código (73709 → 5101837). Detalhes em [reports/fontes.md](reports/fontes.md).
