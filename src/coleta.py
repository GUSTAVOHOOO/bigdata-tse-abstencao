"""Coleta dos dados do TSE: download com retry, extracao e metadados."""
import argparse
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd
import requests

if __package__ in (None, ""):  # execucao direta: python src/coleta.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ANOS, ENCODING, REPORTS, SEP, TSE_BRONZE, URL_TSE

T = TypeVar("T")
CHUNK = 1024 * 1024
COLUNAS_META = ["ano", "url", "arquivo", "data_download", "n_linhas", "n_colunas", "tamanho_bytes"]


def com_retry(func: Callable[[], T], tentativas: int = 5, espera: float = 2.0) -> T:
    """Chama func(); repete com backoff exponencial em erros de rede/IO."""
    for i in range(tentativas):
        try:
            return func()
        except requests.HTTPError as e:
            resp = e.response
            if resp is not None and 400 <= resp.status_code < 500:
                raise  # erro do cliente: repetir nao adianta
            if i == tentativas - 1:
                raise
            time.sleep(espera * 2**i)
        except (requests.RequestException, OSError):
            if i == tentativas - 1:
                raise
            time.sleep(espera * 2**i)
    raise RuntimeError("tentativas deve ser >= 1")


def _zip_valido(caminho: Path) -> bool:
    try:
        if not zipfile.is_zipfile(caminho):
            return False
        with zipfile.ZipFile(caminho) as z:
            return z.testzip() is None
    except (zipfile.BadZipFile, OSError):
        return False


def baixar(url: str, destino: Path, tentativas: int = 5, espera: float = 2.0) -> Path:
    """Baixa url para destino (streaming). Pula se ja existir ZIP valido."""
    destino = Path(destino)
    if destino.exists():
        if _zip_valido(destino):
            return destino
        destino.unlink()
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(".part")

    def _tentar() -> None:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(parcial, "wb") as f:
                for bloco in r.iter_content(chunk_size=CHUNK):
                    f.write(bloco)
        if not _zip_valido(parcial):
            raise OSError(f"ZIP baixado invalido: {url}")

    try:
        com_retry(_tentar, tentativas, espera)
    except BaseException:
        parcial.unlink(missing_ok=True)
        raise
    parcial.replace(destino)
    return destino


MARCADOR_DERIVADOS = ".derivados_brasil_ok"


def _derivar_ufs_ausentes(zf: zipfile.ZipFile, nome_brasil: str, pasta: Path,
                          ufs_existentes: set[str]) -> None:
    """Le o BRASIL em streaming e grava as UFs sem arquivo proprio (bytes crus)."""
    abertos: dict[str, "object"] = {}
    cabecalho = b""
    try:
        with zf.open(nome_brasil) as src:
            for n, linha in enumerate(src):
                if n == 0:
                    cabecalho = linha
                    continue
                campos = linha.split(b";", 5)
                if len(campos) < 5:
                    continue
                uf = campos[4].strip().strip(b'"').decode(ENCODING)
                if uf in ufs_existentes:
                    continue
                if uf not in abertos:
                    alvo = pasta / Path(nome_brasil).name.replace("BRASIL", uf)
                    abertos[uf] = open(alvo, "wb")
                    abertos[uf].write(cabecalho)
                abertos[uf].write(linha)
    finally:
        for f in abertos.values():
            f.close()


def extrair_csvs(zip_path: Path, pasta: Path) -> list[Path]:
    """Extrai os CSVs por UF; UFs presentes so no *BRASIL* viram arquivos derivados.

    O BRASIL em si nunca vai para o disco (duplica as demais linhas).
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    saida = []
    brasil = None
    with zipfile.ZipFile(zip_path) as z:
        for nome in z.namelist():
            base = Path(nome).name
            if not base.lower().endswith(".csv"):
                continue
            if "BRASIL" in base.upper():
                brasil = nome
                continue
            alvo = pasta / base
            if not alvo.exists() or alvo.stat().st_size != z.getinfo(nome).file_size:
                with z.open(nome) as src, open(alvo, "wb") as dst:
                    while bloco := src.read(CHUNK):
                        dst.write(bloco)
            saida.append(alvo)
        marcador = pasta / MARCADOR_DERIVADOS
        if brasil is not None:
            ufs = {Path(a).stem.split("_")[-1] for a in saida}
            if not marcador.exists():
                _derivar_ufs_ausentes(z, brasil, pasta, ufs)
                marcador.write_text("ok")
            saida += [c for c in pasta.glob("*.csv") if c not in saida]
    return sorted(saida)


def _contar(csv: Path) -> tuple[int, int]:
    """Retorna (linhas de dados, colunas) sem carregar o arquivo em memoria."""
    with open(csv, "rb") as f:
        cabecalho = f.readline().decode(ENCODING).rstrip("\r\n")
    n_colunas = cabecalho.count(SEP) + 1
    total, ultimo = 0, b"\n"
    with open(csv, "rb") as f:
        while bloco := f.read(CHUNK):
            total += bloco.count(b"\n")
            ultimo = bloco[-1:]
    if ultimo != b"\n":
        total += 1  # ultima linha sem quebra final
    return max(total - 1, 0), n_colunas


def registrar_metadados(arquivos: list[Path], url: str, ano: int) -> pd.DataFrame:
    """Anexa metadados em reports/metadados_coleta.csv (substitui o ano)."""
    agora = datetime.now().isoformat(timespec="seconds")
    linhas = []
    for a in map(Path, arquivos):
        n_linhas, n_colunas = _contar(a)
        linhas.append({
            "ano": ano, "url": url, "arquivo": a.name, "data_download": agora,
            "n_linhas": n_linhas, "n_colunas": n_colunas, "tamanho_bytes": a.stat().st_size,
        })
    novo = pd.DataFrame(linhas, columns=COLUNAS_META)
    REPORTS.mkdir(parents=True, exist_ok=True)
    caminho = REPORTS / "metadados_coleta.csv"
    if caminho.exists():
        antigo = pd.read_csv(caminho)
        antigo = antigo[antigo["ano"] != ano]
        completo = pd.concat([antigo, novo], ignore_index=True) if len(antigo) else novo
    else:
        completo = novo
    completo.to_csv(caminho, index=False)
    return novo


def coletar(ano: int) -> list[Path]:
    url = URL_TSE.format(ano=ano)
    zip_path = baixar(url, TSE_BRONZE / f"perfil_comparecimento_abstencao_{ano}.zip")
    csvs = extrair_csvs(zip_path, TSE_BRONZE / str(ano))
    registrar_metadados(csvs, url, ano)
    return csvs


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Coleta TSE: perfil comparecimento/abstencao")
    p.add_argument("--anos", nargs="+", type=int, default=ANOS)
    args = p.parse_args(argv)
    for ano in args.anos:
        csvs = coletar(ano)
        print(f"{ano}: {len(csvs)} CSVs")
        # Task 3: converter_para_parquet(csvs, ano)


if __name__ == "__main__":
    main()
