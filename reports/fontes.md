# Fontes de dados (verificadas em 2026-11-14)

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

Também existem 2012, 2014, 2016 e 2026 no CKAN (mesmo padrão). Arquivos têm Last-Modified 30/04/2025.

### Conteúdo do ZIP 2024
- 26 CSVs por UF (AC..TO; sem DF/ZZ separados além dos listados: 26 arquivos) + `_BRASIL.csv` (2,5 GB, DUPLICA todas as linhas) + `leiame.pdf`.
- DECISÃO: usar os CSVs por UF e EXCLUIR `_BRASIL.csv` (extrair com `unzip -x '*BRASIL*'`). Extraídos em `data/bronze/tse/2024/` (ZIP mantido em `data/bronze/tse/`).
- Formato: delimitador `;`, encoding ISO-8859-1 (latin-1), CRLF, cabeçalho presente, textos entre aspas. Em 2018, numéricos vêm sem aspas (duckdb lida com isso; ler com all_varchar e converter).
- Colunas (45): DT_GERACAO, HH_GERACAO, ANO_ELEICAO, NR_TURNO, SG_UF, CD_MUNICIPIO, NM_MUNICIPIO, NR_ZONA, CD_GENERO, DS_GENERO, CD_ESTADO_CIVIL, DS_ESTADO_CIVIL, CD_FAIXA_ETARIA, DS_FAIXA_ETARIA, CD_GRAU_ESCOLARIDADE, DS_GRAU_ESCOLARIDADE, CD_COR_RACA, DS_COR_RACA, CD_QUILOMBOLA, DS_QUILOMBOLA, CD_INTERPRETE_LIBRAS, DS_INTERPRETE_LIBRAS, CD_IDENTIDADE_GENERO, DS_IDENTIDADE_GENERO, CD_IDIOMA_INDIGENA, DS_IDIOMA_INDIGENA, CD_GRUPO_INDIGENA, DS_GRUPO_INDIGENA, QT_APTOS, QT_COMPARECIMENTO, QT_ABSTENCAO, QT_COMPARECIMENTO_DEFICIENCIA, QT_ABSTENCAO_DEFICIENCIA, QT_COMPARECIMENTO_TTE, QT_ABSTENCAO_TTE, QT_COMPAREC_FACULTATIVO, QT_ABST_FACULTATIVO, QT_COMPAREC_OBRIGATORIO, QT_ABST_OBRIGATORIO, QT_COMPAREC_DEFIC_FACULTATIVO, QT_ABST_DEFIC_FACULTATIVO, QT_COMPAREC_DEFIC_OBRIGATORIO, QT_ABST_DEFIC_OBRIGATORIO.
- CD_MUNICIPIO é código TSE em string com zero à esquerda (ex. "01066"), NÃO é código IBGE.
- Sentinelas observados (2024): `-1` / `NÃO INFORMADO` em CD_/DS_ de cor/raça, quilombola, libras, identidade de gênero, idioma e grupo indígena (ex. 4,3 M linhas sem cor/raça); `CD_GENERO=0` + `NÃO INFORMADO` (18.529 linhas); estado civil e escolaridade também têm `NÃO INFORMADO`. `#NULO#`/`#NE#` não observados na amostra completa de 2024 (conferir em 2018/2020 na Task 2). 2 turnos: turno 1 = 8.964.457 linhas, turno 2 = 861.020.
- Cada linha é uma célula agregada (zona x perfil), não um eleitor; QT_* são contagens (min QT_APTOS = 1).
- 5.569 municípios distintos em 2024.

### Diferença 2018 vs 2024 (cabeçalho via range request, mesmo conjunto de 45 colunas)
Mesmos nomes de colunas. Diferenças: em 2018 DS_FAIXA_ETARIA é por idade simples ("20 anos", CD_FAIXA_ETARIA=2000) em vez de faixas de 5 anos ("40 a 44 anos", 4044); campos numéricos sem aspas. Verificar 2020/2022 e contagens completas na Task 2.

## 2. Volume
- 2024 (26 UFs, sem BRASIL): `SELECT count(*)` com duckdb = **9.825.477 linhas** (medido).
- Estimativa dos demais anos proporcional ao tamanho do ZIP (2018 ~9,3 M; 2020 ~5,6 M; 2022 ~10,0 M). Total estimado 4 anos ~ 34,7 M linhas. Apenas 2024 já supera 5 M.

VOLUME: OK (~34.700.000 linhas estimadas; 9.825.477 medidas só em 2024)

## 3. IBGE (testado)
- SIDRA 6579 (estimativa população): variável **9324** "População residente estimada". Retorna município (n6) para 2018, 2020, 2021, 2024 (SP: 12.176.866 / 12.325.232 / 12.396.372 / 11.895.578). `n6/all` para 2024: 5.571 municípios. Ex.: `https://apisidra.ibge.gov.br/values/t/6579/n6/all/v/9324/p/2018,2020,2021,2024`.
- SIDRA 4709 (Censo 2022): variável **93** "População residente", p/2022, 5.570 municípios (também 5936 variação absoluta, 10605 taxa de crescimento).
- SIDRA 5938 (PIB municipal): variável **37** "PIB a preços correntes" (mil reais), último período 2023; 5.570 municípios; também VAB (agropecuária, indústria, serviços, adm. pública, total). NÃO há variável de PIB per capita na tabela: calcular = PIB*1000 / população (6579/9324 ou 4709/93). Períodos 2018, 2020, 2021 retornam dados.
- API localidades: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios` -> JSON, 5.571 municípios (id IBGE 7 dígitos, nome, UF, microrregião, regiões).
- Nota: SIDRA devolve 1ª linha de cabeçalho no JSON; filtrar. Valor "..." = sem dado.

## 4. De-para TSE -> IBGE
URL: https://raw.githubusercontent.com/betafcc/Municipios-Brasileiros-TSE/master/municipios_brasileiros_tse.csv (HTTP 200, UTF-8).
Colunas: codigo_tse (int sem zero à esquerda), uf, nome_municipio, capital, codigo_ibge (7 dígitos). **5.570 linhas** (5.571 com cabeçalho). Join: `CAST(CD_MUNICIPIO AS INT) = codigo_tse`. Observação: TSE 2024 tem 5.569 municípios, IBGE 5.570/5.571 (diferença a verificar, ex. Fernando de Noronha/Brasília); exterior (ZZ) não aparece no 2024 lido.

## 5. Arquivos locais
`data/bronze/tse/perfil_comparecimento_abstencao_2024.zip` (197 MB) e `data/bronze/tse/2024/` (26 CSVs + leiame.pdf, sem BRASIL). Outros anos não baixados.
