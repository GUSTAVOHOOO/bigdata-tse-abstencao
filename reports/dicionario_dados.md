# Dicionário de dados: abstenção eleitoral (TSE) e IBGE

Este dicionário descreve as tabelas da camada bronze (`data/bronze/tse_parquet/` e `data/bronze/ibge/`). Os nomes originais vêm do cabeçalho dos CSVs do TSE. O tipo indicado é o tipo alvo da camada silver. Na bronze, todas as colunas do TSE são texto.

Convenções:
- `usada`: ✓ quando a variável entra em alguma das cinco perguntas de pesquisa (ver `reports/ficha_proposta.md`); ✗ quando é só descritiva ou fica fora do recorte.
- `variavel_snake_case`: o nome original em minúsculas.
- Cada linha do TSE é uma célula agregada (município × zona × turno × perfil do eleitor), não um eleitor.

## Sentinelas

| Valor | Onde aparece | Significado | Ocorrências |
|---|---|---|---|
| `-1` | Códigos `CD_COR_RACA`, `CD_QUILOMBOLA`, `CD_INTERPRETE_LIBRAS`, `CD_IDENTIDADE_GENERO`, `CD_IDIOMA_INDIGENA`, `CD_GRUPO_INDIGENA` | Não informado. O LEIAME usa `-1` para `#NULO` em campos numéricos. | Todas as linhas em 2018, 2020 e 2022. Em 2024, de 4,3 milhões a 9,7 milhões de linhas, conforme a variável. |
| `-3` | `CD_FAIXA_ETARIA` (rótulo `Inválido`) | Idade inválida. O LEIAME usa `-3` para `#NE`. | 5.558 (2018); 2.467 (2020); 3.868 (2022); 1.686 (2024) |
| `#NULO#` / `#NE#` | Qualquer coluna de texto | Texto que o LEIAME descreve para campos em branco ou não registrados. | Nenhuma ocorrência em 2018–2024 |
| `NÃO INFORMADO` | Todas as colunas `DS_*` com código sentinela | Rótulo do valor `-1` ou `0`. | Ver linhas por variável |
| `0` | `CD_GENERO`, `CD_ESTADO_CIVIL`, `CD_GRAU_ESCOLARIDADE` | Não informado. Não consta no LEIAME. | `CD_GENERO=0`: 63.998 (2018); 29.678 (2020); 41.372 (2022); 18.529 (2024) |

Nas análises por perfil, as linhas com sentinela devem ser tratadas de forma explícita (categoria própria ou exclusão), e o critério deve ficar registrado na camada silver.

## Fonte 1: TSE, perfil de comparecimento e abstenção

Arquivos: `perfil_comparecimento_abstencao_{ano}_{UF}.csv`, extraídos dos ZIPs de 2018, 2020, 2022 e 2024. O arquivo `_BRASIL.csv` repete todas as linhas das UFs e não é usado inteiro: a coleta o lê em fluxo e tira dele só as linhas de DF e `ZZ`, que não existem nos arquivos por UF. Leiaute: `leiame.pdf` (dentro de cada ZIP). Total: 31.633.820 linhas.

| variavel_original | variavel_snake_case | tipo | usada | descricao | dominio |
|---|---|---|---|---|---|
| DT_GERACAO | dt_geracao | date | ✗ | Data da extração dos dados para geração do arquivo. | Uma data por ano: 30/04/2025 (2018, 2020); 29/04/2025 (2022, 2024). |
| HH_GERACAO | hh_geracao | time | ✗ | Hora da extração, no horário de Brasília. | Um valor por ano (ex.: 07:09:09 em 2018). |
| ANO_ELEICAO | ano_eleicao | int16 | ✓ | Ano de referência da eleição. | 2018, 2020, 2022, 2024 |
| NR_TURNO | nr_turno | int8 | ✓ | Número do turno. | 1 e 2. Em 2018 e 2022, toda célula aparece nos dois turnos com o mesmo eleitorado. Em 2020 e 2024, o 2º turno só existe para municípios com mais de 200 mil eleitores (383.161 e 861.020 linhas). |
| CD_MUNICIPIO | cd_municipio | string | ✓ | Código TSE do município, com 5 caracteres e zeros à esquerda. Não é o código IBGE. | 5.568 (2020) a 5.751 (2022) códigos distintos. Inclui códigos `99xxx`: 4 municípios de MT e os códigos do exterior (`ZZ`). |
| NM_MUNICIPIO | nm_municipio | string | ✗ | Nome do município. | 5.295 (2020) a 5.466 (2022) nomes distintos. Nomes se repetem entre UFs; use o código. |
| NR_ZONA | nr_zona | int16 | ✗ | Número da zona eleitoral. | 1 a 427 (2018–2022); 1 a 428 (2024); 421 valores distintos no total. |
| CD_GENERO | cd_genero | int8 | ✗ | Código do gênero. | 2 = Masculino; 4 = Feminino; 0 = não informado (sentinela). |
| DS_GENERO | ds_genero | category | ✗ | Descrição do gênero. | FEMININO, MASCULINO, NÃO INFORMADO |
| CD_ESTADO_CIVIL | cd_estado_civil | int8 | ✗ | Código do estado civil. | 1 = Solteiro(a); 3 = Casado(a); 5 = Viúvo(a); 7 = Separado(a) judicialmente; 9 = Divorciado(a); 0 = não informado (sentinela). |
| DS_ESTADO_CIVIL | ds_estado_civil | category | ✗ | Descrição do estado civil. | SOLTEIRO, CASADO, VIÚVO, SEPARADO JUDICIALMENTE, DIVORCIADO, NÃO INFORMADO |
| CD_FAIXA_ETARIA | cd_faixa_etaria | int16 | ✓ | Código da faixa etária: idade inicial e final em dois dígitos cada (ex.: 4044 = 40 a 44 anos). | 1600 a 2000 (16 a 20 anos, idade simples); 2124 (21 a 24); 2529 a 9599 (faixas de 5 anos); 9999 (100 anos ou mais); -3 (inválido). Mesmos códigos nos quatro anos. |
| DS_FAIXA_ETARIA | ds_faixa_etaria | category | ✓ | Rótulo da faixa etária. | 23 valores iguais nos quatro anos: "16 anos" a "20 anos", "21 a 24 anos", "25 a 29 anos" até "95 a 99 anos", "100 anos ou mais", "Inválido". |
| CD_GRAU_ESCOLARIDADE | cd_grau_escolaridade | int8 | ✓ | Código do grau de instrução (o LEIAME usa o nome `CD_GRAU_INSTRUCAO`). | 1 = Analfabeto; 2 = Lê e escreve; 3 = Fundamental incompleto; 4 = Fundamental completo; 5 = Médio incompleto; 6 = Médio completo; 7 = Superior incompleto; 8 = Superior completo; 0 = não informado (sentinela). |
| DS_GRAU_ESCOLARIDADE | ds_grau_escolaridade | category | ✓ | Rótulo do grau de instrução. | ANALFABETO, LÊ E ESCREVE, ENSINO FUNDAMENTAL INCOMPLETO, ENSINO FUNDAMENTAL COMPLETO, ENSINO MÉDIO INCOMPLETO, ENSINO MÉDIO COMPLETO, SUPERIOR INCOMPLETO, SUPERIOR COMPLETO, NÃO INFORMADO. Mesmos valores nos quatro anos. |
| CD_COR_RACA | cd_cor_raca | int8 | ✗ | Código de raça/cor. | 2024: 1 = Branca; 2 = Preta; 3 = Parda; 4 = Amarela; 5 = Indígena; -1 = não informado. O LEIAME lista 01 a 05 e 06 = Não Informado. Em 2018, 2020 e 2022, só `-1`. |
| DS_COR_RACA | ds_cor_raca | category | ✗ | Rótulo de raça/cor. | 2024: Branca, Preta, Parda, Amarela, Indígena, NÃO INFORMADO. Em 2018–2022, só NÃO INFORMADO. |
| CD_QUILOMBOLA | cd_quilombola | int8 | ✗ | Código que indica origem quilombola. | 1 = Sim; 2 = Não; -1 = não informado. Em 2018–2022, só `-1`. |
| DS_QUILOMBOLA | ds_quilombola | category | ✗ | Rótulo de origem quilombola. | SIM, NÃO, NÃO INFORMADO. Em 2018–2022, só NÃO INFORMADO. |
| CD_INTERPRETE_LIBRAS | cd_interprete_libras | int8 | ✗ | Código que indica intérprete de Libras. | 1 = Sim; 2 = Não; -1 = não informado. Em 2018–2022, só `-1`. |
| DS_INTERPRETE_LIBRAS | ds_interprete_libras | category | ✗ | Rótulo de intérprete de Libras. | SIM, NÃO, NÃO INFORMADO. Em 2018–2022, só NÃO INFORMADO. |
| CD_IDENTIDADE_GENERO | cd_identidade_genero | int8 | ✗ | Código da identidade de gênero autodeclarada. | 1 = Cisgênero; 2 = Transgênero; 3 = Prefere não informar; -1 = não informado. Em 2018–2022, só `-1`. |
| DS_IDENTIDADE_GENERO | ds_identidade_genero | category | ✗ | Rótulo da identidade de gênero. | Cisgênero, Transgênero, Prefere não informar, NÃO INFORMADO. Em 2018–2022, só NÃO INFORMADO. |
| CD_IDIOMA_INDIGENA | cd_idioma_indigena | int8 | ✗ | Código que indica domínio de língua indígena. | 1 = Sim; 2 = Não; -1 = não informado. Em 2018–2022, só `-1`. |
| DS_IDIOMA_INDIGENA | ds_idioma_indigena | category | ✗ | Rótulo de domínio de língua indígena. | SIM, NÃO, NÃO INFORMADO. Em 2018–2022, só NÃO INFORMADO. |
| CD_GRUPO_INDIGENA | cd_grupo_indigena | int32 | ✗ | Código da etnia, povo ou grupo indígena. | 2024: 298 códigos distintos, incluindo `-1`. Em 2018–2022, só `-1`. |
| DS_GRUPO_INDIGENA | ds_grupo_indigena | category | ✗ | Nome da etnia, povo ou grupo indígena. | 2024: 298 valores, incluindo NÃO INFORMADO. Em 2018–2022, só NÃO INFORMADO. |
| QT_APTOS | qt_aptos | int32 | ✓ | Eleitores aptos a votar na célula. | Mín. 1; máx. 7.187 (todos os anos). |
| QT_COMPARECIMENTO | qt_comparecimento | int32 | ✓ | Aptos que compareceram para votar. | 0 a 5.443 |
| QT_ABSTENCAO | qt_abstencao | int32 | ✓ | Aptos que não compareceram. | 0 a 2.812 |
| QT_COMPARECIMENTO_DEFICIENCIA | qt_comparecimento_deficiencia | int32 | ✗ | Aptos com deficiência ou mobilidade reduzida que compareceram. O LEIAME usa `QT_COMPAREC_DEFICIENTES`. | 0 a 346 |
| QT_ABSTENCAO_DEFICIENCIA | qt_abstencao_deficiencia | int32 | ✗ | Aptos com deficiência ou mobilidade reduzida que não compareceram. O LEIAME usa `QT_ABST_DEFICIENTES`. | 0 a 167 |
| QT_COMPARECIMENTO_TTE | qt_comparecimento_tte | int32 | ✗ | Aptos com transferência temporária de eleitor (TTE) que compareceram. O LEIAME usa `QT_COMPAREC_TTE`. | 0 a 920 |
| QT_ABSTENCAO_TTE | qt_abstencao_tte | int32 | ✗ | Aptos com TTE que não compareceram. O LEIAME usa `QT_ABST_TTE`. | 0 a 486 |
| QT_COMPAREC_FACULTATIVO | qt_comparec_facultativo | int32 | ✓ | Eleitores com voto facultativo que compareceram. | 0 a 2.012 |
| QT_ABST_FACULTATIVO | qt_abst_facultativo | int32 | ✓ | Eleitores com voto facultativo que não compareceram. | 0 a 980 |
| QT_COMPAREC_OBRIGATORIO | qt_comparec_obrigatorio | int32 | ✗ | Eleitores com voto obrigatório que compareceram. | 0 a 5.443 |
| QT_ABST_OBRIGATORIO | qt_abst_obrigatorio | int32 | ✗ | Eleitores com voto obrigatório que não compareceram. | 0 a 2.812 |
| QT_COMPAREC_DEFIC_FACULTATIVO | qt_comparec_defic_facultativo | int32 | ✗ | Aptos com deficiência, voto facultativo, que compareceram. | 0 a 250 |
| QT_ABST_DEFIC_FACULTATIVO | qt_abst_defic_facultativo | int32 | ✗ | Aptos com deficiência, voto facultativo, que não compareceram. | 0 a 167 |
| QT_COMPAREC_DEFIC_OBRIGATORIO | qt_comparec_defic_obrigatorio | int32 | ✗ | Aptos com deficiência, voto obrigatório, que compareceram. | 0 a 346 |
| QT_ABST_DEFIC_OBRIGATORIO | qt_abst_defic_obrigatorio | int32 | ✗ | Aptos com deficiência, voto obrigatório, que não compareceram. | 0 a 119 |
| SG_UF | sg_uf | category | ✓ | Sigla da unidade da federação. | 26 UFs em 2020 e 2024. Em 2018 e 2022, mais DF e `ZZ` (exterior). Não aparecem `BR` nem `VT`, que o LEIAME prevê. |

Os intervalos de `QT_*` são o mínimo e o máximo nos quatro anos, lidos com `TRY_CAST` para `BIGINT`. Nenhuma coluna `QT_*` tem texto ou sentinela.

### Diferenças entre anos

A faixa etária tem o mesmo domínio nos quatro anos: 16 a 20 anos aparecem como idade simples em 2018, 2020, 2022 e 2024.

Cor/raça, quilombola, Libras, identidade de gênero, idioma e grupo indígena só têm valores informados em 2024. Em 2018, 2020 e 2022, todas as linhas trazem `-1` / NÃO INFORMADO.

Em 2018 e 2022, as mesmas células aparecem nos dois turnos com o mesmo total de aptos (147.306.275 em 2018; 156.454.011 em 2022), mas com comparecimento e abstenção diferentes. Somar `QT_APTOS` entre turnos duplica o eleitorado.

DF e `ZZ` aparecem só em 2018 e 2022.

### Divergências com o LEIAME

- O LEIAME lista quatro colunas `QT_*` com nomes diferentes dos CSVs (`QT_COMPAREC_DEFICIENTES`, `QT_ABST_DEFICIENTES`, `QT_COMPAREC_TTE`, `QT_ABST_TTE`). Os nomes usados aqui são os dos CSVs.
- O LEIAME descreve `CD_IDIOMA_QUILOMBOLA` e `DS_IDIOMA_QUILOMBOLA`, mas essas colunas não estão nos CSVs nem na bronze.
- `CD_GENERO`, `CD_ESTADO_CIVIL` e `CD_GRAU_ESCOLARIDADE` têm o código `0` (NÃO INFORMADO), que o LEIAME não lista.
- O LEIAME define `CD_COR_RACA` de 01 a 06, mas os dados trazem 1 a 5 e `-1`.

## Fonte 2: IBGE

Tabelas em `data/bronze/ibge/`. Os nomes já estão em snake_case, então `variavel_original` e `variavel_snake_case` são iguais.

### populacao_municipios.parquet (27.854 linhas)

Fontes: SIDRA 6579, variável 9324 (estimativa, para 2018, 2020, 2021 e 2024) e SIDRA 4709, variável 93 (Censo 2022, para 2022). O PIB de 2023 usa a população de 2022 (ver `pib_municipios`), mas esse ano não é gravado nesta tabela.

| variavel_original | variavel_snake_case | tipo | usada | descricao | dominio |
|---|---|---|---|---|---|
| cd_municipio_ibge | cd_municipio_ibge | string | ✓ | Código IBGE do município, com 7 dígitos. | 5.570 ou 5.571 municípios por ano. |
| ano | ano | int16 | ✓ | Ano de referência da população. | 2018, 2020, 2021, 2022, 2024 |
| populacao | populacao | int32 | ✓ | População residente. | 771 a 12.396.372 (todos os anos). |
| fonte_populacao | fonte_populacao | category | ✗ | Origem do valor. | `estimativa_6579` (2018, 2020, 2021, 2024); `censo_4709` (2022). |

### pib_municipios.parquet (22.280 linhas)

Fonte: SIDRA 5938, variável 37 (PIB a preços correntes, mil reais), anos 2018, 2020, 2022 e 2023. `pib_per_capita` é calculado no projeto (`src/ibge.py`): `pib_mil_reais * 1000 / populacao`, com a população do mesmo ano.

| variavel_original | variavel_snake_case | tipo | usada | descricao | dominio |
|---|---|---|---|---|---|
| cd_municipio_ibge | cd_municipio_ibge | string | ✓ | Código IBGE do município, com 7 dígitos. | 5.570 municípios por ano. |
| ano | ano | int16 | ✓ | Ano do PIB. | 2018, 2020, 2022, 2023 |
| pib_mil_reais | pib_mil_reais | int64 | ✗ | PIB do município, em mil reais, a preços correntes. | 14.127 a 1.066.825.105 (todos os anos). |
| pib_per_capita | pib_per_capita | float64 | ✓ | PIB por habitante, em reais. | 4.778,49 a 842.004,60 (todos os anos). Os valores máximos são outliers de municípios pequenos. |
| ano_eleicao | ano_eleicao | int16 | ✓ | Eleição a que o PIB se associa. O PIB de 2023 vai para a eleição de 2024. | 2018, 2020, 2022, 2024 |

### municipios_ibge.parquet (5.571 linhas)

Fonte: API de localidades do IBGE (`servicodados.ibge.gov.br/api/v1/localidades/municipios`).

| variavel_original | variavel_snake_case | tipo | usada | descricao | dominio |
|---|---|---|---|---|---|
| cd_municipio_ibge | cd_municipio_ibge | string | ✓ | Código IBGE do município, com 7 dígitos. | 5.571 valores distintos. |
| nm_municipio | nm_municipio | string | ✗ | Nome do município (IBGE). | Texto livre. |
| sg_uf | sg_uf | category | ✓ | Sigla da UF. | 27 UFs (inclui DF, com 1 município). |
| nm_regiao | nm_regiao | category | ✓ | Grande região. | Centro-Oeste (468), Nordeste (1.794), Norte (450), Sudeste (1.668), Sul (1.191). |

### depara_tse_ibge.parquet (5.570 linhas)

Fonte: repositório `betafcc/Municipios-Brasileiros-TSE` (CSV de terceiros). A tabela na bronze tem só duas colunas. A chave TSE mantém os zeros à esquerda, por isso é texto de 5 caracteres.

| variavel_original | variavel_snake_case | tipo | usada | descricao | dominio |
|---|---|---|---|---|---|
| cd_municipio_tse | cd_municipio_tse | string | ✓ | Código TSE do município, com 5 caracteres e zeros à esquerda. | 5.570 valores distintos. Inclui 4 códigos `99xxx`. |
| cd_municipio_ibge | cd_municipio_ibge | string | ✓ | Código IBGE do município, com 7 dígitos. | 5.570 valores distintos. |

Junção: `cd_municipio` (TSE) = `cd_municipio_tse`. Não há correspondência para os códigos do exterior (`ZZ`, em 2018 e 2022) nem para Boa Esperança do Norte (MT, código TSE 73709), que aparece só em 2024.

## Variáveis derivadas (silver e gold)

Estas colunas não existem nos arquivos do TSE. O projeto as cria na limpeza (`src/limpeza.py`, camada silver) e na agregação (`src/agregacao.py`, camada gold). Tipos e domínios foram lidos dos Parquet.

### Silver (`data/silver/tse/`)

| variavel | camada | tipo | descricao | dominio |
|---|---|---|---|---|
| nm_regiao | silver | category | Grande região da UF. Nulo no exterior. | Centro-Oeste, Nordeste, Norte, Sudeste, Sul. Nulo em 141.100 linhas (`ZZ`). |
| faixa_etaria_agrupada | silver | category (ordenada) | Faixa etária reagrupada a partir de `cd_faixa_etaria`. | 16–17, 18–24, 25–34, 35–44, 45–59, 60–69, 70+. Nulo em 13.575 linhas (idade inválida). |
| grupo_idade | silver | category (ordenada) | Grupo de idade pela regra do voto: facultativo aos 16–17 e aos 70 ou mais, obrigatório entre 18 e 69. | 16–17, 18–69, 70+. Nulo em 13.575 linhas. |
| voto_facultativo | silver | boolean (nulável) | Verdadeiro para 16–17 anos, 70 anos ou mais, ou analfabeto (CF, art. 14, § 1º, II). Nulo quando idade ou escolaridade é desconhecida. | Verdadeiro (9.065.339), falso (17.185.523), nulo (59.320). |
| exterior | silver | boolean | Linha do exterior (`sg_uf` = `ZZ`). | Verdadeiro em 141.100 linhas. |
| tem_2o_turno | silver | boolean | O município teve 2º turno no ano. | Verdadeiro em 18.458.544 linhas, falso em 7.851.638. |
| data_turno | silver | date | Data oficial do turno, pelo calendário do TSE. | De 07/10/2018 a 27/10/2024; sem nulos. |
| mes_ano | silver | category | Mês e ano do turno, no formato AAAA-MM. | 2018-10, 2020-11, 2022-10, 2024-10. |
| cd_municipio_ibge | silver | string | Código IBGE do município (7 dígitos), obtido pelo de-para TSE → IBGE. | De 1100015 a 5300108. Nulo no exterior (141.100 linhas). |
| populacao | silver | int32 | População do município no ano da eleição. | 776 a 12.325.232. Nulo em 141.609 linhas (exterior e 509 linhas de 2024 sem dado de população). |
| fonte_populacao | silver | category | Origem da população. | `censo_4709` (8.651.140 linhas, 2022); `estimativa_6579` (17.517.942). Nulo no exterior. |
| ano_pib | silver | int16 | Ano do PIB municipal associado à eleição (o PIB de 2023 vai para 2024). | De 2018 a 2023. Nulo em 141.609 linhas. |
| pib_per_capita | silver | float64 | PIB por habitante, em reais, do ano `ano_pib`. | 4.778,49 a 842.004,60. Nulo em 141.609 linhas. |
| inconsistente | silver | boolean | Marca, sem remover, linhas em que `qt_aptos` ≠ `qt_comparecimento` + `qt_abstencao`. | Falso em todas as 26.310.182 linhas. |
| perfil_implausivel | silver | boolean | Marca, sem corrigir, células de 16–17 anos com superior completo. | Verdadeiro em 1.605 linhas. |

### Gold (`data/gold/`)

As tabelas gold usam só o 1º turno, exceto `turnos`. A taxa é sempre a soma das abstenções dividida pela soma dos aptos do grupo.

| variavel | camada | tipo | descricao | dominio |
|---|---|---|---|---|
| taxa_abstencao | gold | float64 | `qt_abstencao / qt_aptos` do grupo, em fração de 0 a 1. | Em `municipio_ano`, de 0 a 0,995. Em `turnos`, de 0,202 a 0,295. |
| abstencoes_por_100k_hab | gold | float64 | Abstenções por 100 mil habitantes do município (`municipio_ano`). Nulo sem população. | 2.487 a 122.679. Nulo em 353 linhas (exterior e município sem população). |
| pct_70_mais | gold | float64 | Fração dos aptos do município com 70 anos ou mais. | 0 a 0,333. |
| pct_16_17 | gold | float64 | Fração dos aptos do município com 16 ou 17 anos. | 0 a 0,066. |
| pct_superior | gold | float64 | Fração dos aptos do município com superior completo. | 0 a 1. |
| outlier_iqr | gold | boolean (nulável) | Município-ano com taxa fora de [Q1 − 1,5·IQR; Q3 + 1,5·IQR], com quartis calculados por ano e sem o exterior. Nulo no exterior ou sem taxa. | Verdadeiro (110), falso (22.167), nulo (352). |
| conjunto | gold | string | Conjunto de municípios da tabela `turnos`. | `com_2o_turno` (municípios com 2º turno no ano, nos dois turnos) e `todos` (1º turno de todos os municípios). |
