# Fontes de dados (verificadas em 2026-11-14)

Este arquivo registra a verificação das fontes feita antes da coleta, atualizada com o que a coleta encontrou.

## 1. TSE - perfil_comparecimento_abstencao
Portal: https://dadosabertos.tse.jus.br (CKAN; dataset "Comparecimento e Abstenção - {ano}", pacote `comparecimento-e-abstencao-{ano}`).
Licença: Creative Commons Attribution (CC-BY), conforme `license_id=cc-by` na API CKAN. Citar TSE como fonte.
Leiaute: `leiame.pdf` dentro de cada ZIP (125 KB no ZIP de 2024; copiado em `data/bronze/tse/2024/leiame.pdf`).

| Ano | URL (padrão confirmado) | HTTP | Tamanho ZIP |
|---|---|---|---|
| 2018 | https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_comparecimento_abstencao/perfil_comparecimento_abstencao_2018.zip | 200 | 187.576.884 B |
| 2020 | .../perfil_comparecimento_abstencao_2020.zip | 200 | 112.407.801 B |
| 2022 | .../perfil_comparecimento_abstencao_2022.zip | 200 | 200.995.304 B |
| 2024 | .../perfil_comparecimento_abstencao_2024.zip | 200 | 197.126.312 B |

Também existem 2012, 2014, 2016 e 2026 no CKAN (mesmo padrão), fora do recorte. Os arquivos têm Last-Modified 30/04/2025. Os quatro ZIPs foram baixados (666 MB no total) e ficam em `data/bronze/tse/`.

### Conteúdo dos ZIPs
- Cada ZIP traz um CSV por UF, `leiame.pdf` e um `_BRASIL.csv` de cerca de 2,5 GB que repete todas as linhas. Os CSVs por UF cobrem 26 UFs (2020 e 2024) ou 28 arquivos (2018 e 2022); os arquivos por UF não incluem DF nem o exterior (`ZZ`).
- Decisão: usar os CSVs por UF e ler o `_BRASIL.csv` só em fluxo (streaming), para recuperar as linhas de DF e ZZ, que existem apenas nele. O arquivo nunca é salvo inteiro. Os CSVs extraídos ficam em `data/bronze/tse/{ano}/` e o Parquet particionado em `data/bronze/tse_parquet/`.
- Formato: delimitador `;`, encoding ISO-8859-1 (latin-1), CRLF, cabeçalho presente, textos entre aspas. Em 2018 os numéricos vêm sem aspas; a leitura usa texto (all_varchar) e converte depois.
- Colunas (43), as mesmas nos quatro anos: DT_GERACAO, HH_GERACAO, ANO_ELEICAO, NR_TURNO, SG_UF, CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA, CD_GENERO, DS_GENERO, CD_ESTADO_CIVIL, DS_ESTADO_CIVIL, CD_FAIXA_ETARIA, DS_FAIXA_ETARIA, CD_GRAU_ESCOLARIDADE, DS_GRAU_ESCOLARIDADE, CD_COR_RACA, DS_COR_RACA, CD_QUILOMBOLA, DS_QUILOMBOLA, CD_INTERPRETE_LIBRAS, DS_INTERPRETE_LIBRAS, CD_IDENTIDADE_GENERO, DS_IDENTIDADE_GENERO, CD_IDIOMA_INDIGENA, DS_IDIOMA_INDIGENA, CD_GRUPO_INDIGENA, DS_GRUPO_INDIGENA, QT_APTOS, QT_COMPARECIMENTO, QT_ABSTENCAO, QT_COMPARECIMENTO_DEFICIENCIA, QT_ABSTENCAO_DEFICIENCIA, QT_COMPARECIMENTO_TTE, QT_ABSTENCAO_TTE, QT_COMPAREC_FACULTATIVO, QT_ABST_FACULTATIVO, QT_COMPAREC_OBRIGATORIO, QT_ABST_OBRIGATORIO, QT_COMPAREC_DEFIC_FACULTATIVO, QT_ABST_DEFIC_FACULTATIVO, QT_COMPAREC_DEFIC_OBRIGATORIO, QT_ABST_DEFIC_OBRIGATORIO.
- CD_MUNICIPIO é código TSE em string com zero à esquerda (ex. "01066"), não é código IBGE.
- Sentinelas: `-1` / `NÃO INFORMADO` em CD_/DS_ de cor/raça, quilombola, libras, identidade de gênero, idioma e grupo indígena (em 2018, 2020 e 2022 são todas as linhas; em 2024, de 4,3 M a 9,7 M, conforme a variável); `CD_GENERO=0` + `NÃO INFORMADO` (18.529 linhas em 2024); estado civil e escolaridade também têm `NÃO INFORMADO`. `#NULO#` e `#NE#` não aparecem em nenhum dos quatro anos. Em 2024, turno 1 = 8.964.457 linhas e turno 2 = 861.020.
- Cada linha é uma célula agregada (zona x perfil), não um eleitor; QT_* são contagens (min QT_APTOS = 1).
- 5.569 municípios distintos em 2024.

### Diferenças entre anos
Os nomes das colunas são iguais nos quatro anos, e a faixa etária também: idade simples de 16 a 20 anos, "21 a 24 anos" e faixas de 5 anos acima disso (mesmos códigos em 2018, 2020, 2022 e 2024). A única diferença de formato é que os numéricos de 2018 vêm sem aspas. Cor/raça e as demais colunas de perfil só têm valores informados em 2024. Em 2018 e 2022 as células se repetem nos dois turnos; em 2020 e 2024 o 2º turno só existe nos municípios com mais de 200 mil eleitores. Detalhes em `reports/dicionario_dados.md`.

## 2. Volume
Total medido: **31.633.820 linhas** em 108 CSVs (`reports/metadados_coleta.csv`).

| Ano | Linhas |
|---|---:|
| 2018 | 8.377.682 |
| 2020 | 4.644.923 |
| 2022 | 8.785.738 |
| 2024 | 9.825.477 |

VOLUME: OK (31.633.820 linhas; cada ano sozinho tem mais de 4,6 milhões e 2024 supera 9 milhões).

## 3. IBGE (testado)
- SIDRA 6579 (estimativa população): variável **9324** "População residente estimada". Retorna município (n6) para 2018, 2020, 2021, 2024 (SP: 12.176.866 / 12.325.232 / 12.396.372 / 11.895.578). `n6/all` para 2024: 5.571 municípios. Ex.: `https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/2018,2020,2021,2024`.
- SIDRA 4709 (Censo 2022): variável **93** "População residente", p/2022, 5.570 municípios (também 5936 variação absoluta, 10605 taxa de crescimento).
- SIDRA 5938 (PIB municipal): variável **37** "PIB a preços correntes" (mil reais), último período 2023; 5.570 municípios; também VAB (agropecuária, indústria, serviços, adm. pública, total). NÃO há variável de PIB per capita na tabela: calcular = PIB*1000 / população (6579/9324 ou 4709/93). Períodos 2018, 2020, 2021 retornam dados.
- API localidades: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios` -> JSON, 5.571 municípios (id IBGE 7 dígitos, nome, UF, microrregião, regiões).
- Nota: SIDRA devolve 1ª linha de cabeçalho no JSON; filtrar. Valor "..." = sem dado.

## 4. De-para TSE -> IBGE
URL: https://raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE/master/municipios_brasileiros_tse.csv (HTTP 200, UTF-8).
Colunas: codigo_tse (int sem zero à esquerda), uf, nome_municipio, capital, codigo_ibge (7 dígitos). **5.570 linhas** (5.571 com cabeçalho). Join: `CAST(CD_MUNICIPIO AS INT) = codigo_tse`. Observação: TSE 2024 tem 5.569 municípios, IBGE 5.570/5.571 ; o exterior (ZZ) aparece em 2018 e 2022 e não tem código IBGE. Boa Esperança do Norte (MT, código TSE 73709) só existe em 2024 e foi acrescentada à mão (73709 → 5101837).

## 5. Arquivos locais
`data/bronze/tse/` guarda os quatro ZIPs (666 MB) e os CSVs extraídos por ano. `data/bronze/tse_parquet/` guarda o Parquet da bronze (217 MB), `data/bronze/ibge/` as tabelas do IBGE e o de-para. Esses arquivos não vão para o Git.
