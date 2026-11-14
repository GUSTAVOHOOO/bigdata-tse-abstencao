# Ficha de proposta: abstenção eleitoral no Brasil (2018–2024)

| Campo | Conteúdo |
|---|---|
| Tema | Abstenção eleitoral no Brasil e seus determinantes (perfil do eleitor e território) nas eleições de 2018, 2020, 2022 e 2024 |
| Fonte primária | TSE, perfil de comparecimento e abstenção. Portal: https://dadosabertos.tse.jus.br (CKAN, pacotes `comparecimento-e-abstencao-{ano}`). Padrão do arquivo: https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_comparecimento_abstencao/perfil_comparecimento_abstencao_{ano}.zip |
| Licença | Creative Commons Attribution (CC-BY). Citar o TSE como fonte. |
| Recorte | Anos 2018, 2020, 2022 e 2024; todas as UFs. DF e exterior (ZZ) aparecem apenas nas eleições gerais (2018 e 2022). |
| Unidade | Célula agregada por município, zona, turno e perfil do eleitor. Não há microdado individual. |
| Volume | 31.633.820 linhas: 2018 = 8.377.682; 2020 = 4.644.923; 2022 = 8.785.738; 2024 = 9.825.477. Em CSV, 8.312 MB; em Parquet, 217 MB. |

## Segunda fonte: IBGE

| Tabela | Endpoint | Conteúdo |
|---|---|---|
| População estimada | SIDRA 6579, variável 9324: https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/2018,2020,2021,2024 | População por município em 2018, 2020, 2021 e 2024 |
| População do Censo | SIDRA 4709, variável 93: https://apisidra.ibge.gov.br/values/t/4709/n6/all/v/93/p/2022 | População por município no Censo 2022 |
| PIB municipal | SIDRA 5938, variável 37 (mil reais, preços correntes): https://apisidra.ibge.gov.br/values/t/5938/n6/all/v/37/p/2018,2020,2022,2023 | PIB por município em 2018, 2020, 2022 e 2023 (o de 2023 entra na eleição de 2024). PIB per capita calculado no projeto. |
| Municípios | https://servicodados.ibge.gov.br/api/v1/localidades/municipios | 5.571 municípios: código IBGE de 7 dígitos, nome, UF e região |
| De-para TSE → IBGE | https://raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE/master/municipios_brasileiros_tse.csv | Código TSE do município para código IBGE (5.570 pares) |

Licença dos dados do IBGE e do de-para (repositório de terceiros): a confirmar antes da entrega.

## Perguntas de pesquisa

1. A abstenção cresceu de 2018 a 2024, e como se comportam eleições gerais (2018/2022) × municipais (2020/2024) e 1º × 2º turno?
2. Quais faixas etárias se abstêm mais, e quanto pesam os grupos de voto facultativo (16–17 e 70+)?
3. Existe gradiente de abstenção por escolaridade?
4. Quais UFs e regiões têm as maiores taxas de abstenção, e a eleição de 2020 (pandemia) foi um ponto fora da curva?
5. Municípios mais populosos ou com maior PIB per capita se abstêm mais ou menos?

## Motivação

A abstenção varia conforme o tipo de eleição, o perfil do eleitorado e o território. Os dados do TSE trazem, para cada município, zona e turno, o número de aptos, de comparecimentos e de abstenções, separado por faixa etária, escolaridade e tipo de voto. Cor/raça só aparece em 2024. Cruzados com população e PIB do IBGE, esses dados permitem verificar se as diferenças de abstenção acompanham o perfil socioeconômico das localidades e se a eleição de 2020, realizada na pandemia, destoou do padrão.
