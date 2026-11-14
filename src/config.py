"""Constantes do projeto: caminhos, anos, origem dos dados e convenções de leitura."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

BRONZE = RAIZ / "data" / "bronze"
SILVER = RAIZ / "data" / "silver"
GOLD = RAIZ / "data" / "gold"
REPORTS = RAIZ / "reports"
FIGURAS = REPORTS / "figuras"
TSE_BRONZE = BRONZE / "tse"

ANOS: list[int] = [2018, 2020, 2022, 2024]

URL_TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele/perfil_comparecimento_abstencao/perfil_comparecimento_abstencao_{ano}.zip"

SENTINELAS: set[str] = {"#NULO#", "#NULO", "#NE#", "#NE", "-1", "-3", "NÃO INFORMADO"}

SEP = ";"
ENCODING = "latin-1"
