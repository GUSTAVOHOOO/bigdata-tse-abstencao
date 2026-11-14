"""Coleta dos dados do TSE: download com retry, extracao e metadados."""
import argparse
import csv
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import requests

if __package__ in (None, ""):  # execucao direta: python src/coleta.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ANOS, BRONZE, ENCODING, REPORTS, SEP, TSE_BRONZE, URL_TSE

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


PARQUET = BRONZE / "tse_parquet"  # hive: ano=YYYY/SG_UF=XX/*.parquet
BLOCK_SIZE = 64 * 1024 * 1024


def _cabecalho(csv_path: Path) -> list[str]:
    with open(csv_path, "r", encoding=ENCODING, newline="") as f:
        return [c.strip().upper() for c in next(csv.reader(f, delimiter=SEP))]


def csv_para_parquet(csvs: list[Path], ano: int, destino: Path = PARQUET) -> int:
    """Converte os CSVs de um ano para Parquet (zstd) particionado em ano/SG_UF.

    Streaming (blocos de 64 MB); todas as colunas como string; idempotente:
    a particao ano=YYYY e' apagada antes de gravar. Retorna linhas gravadas.
    """
    destino = Path(destino)
    shutil.rmtree(destino / f"ano={ano}", ignore_errors=True)
    particao = ds.partitioning(pa.schema([("ano", pa.int16()), ("SG_UF", pa.string())]),
                               flavor="hive")
    total = 0
    for csv_path in map(Path, csvs):
        nomes = _cabecalho(csv_path)
        reader = pacsv.open_csv(
            csv_path,
            read_options=pacsv.ReadOptions(encoding=ENCODING, block_size=BLOCK_SIZE,
                                           column_names=nomes, skip_rows=1),
            parse_options=pacsv.ParseOptions(delimiter=SEP),
            convert_options=pacsv.ConvertOptions(column_types={n: pa.string() for n in nomes}),
        )

        def lotes():
            nonlocal total
            for lote in reader:
                total += lote.num_rows
                yield lote.append_column("ano", pa.array([ano] * lote.num_rows, pa.int16()))

        esquema = reader.schema.append(pa.field("ano", pa.int16()))
        ds.write_dataset(
            pa.RecordBatchReader.from_batches(esquema, lotes()), destino,
            format="parquet", partitioning=particao,
            basename_template=f"{csv_path.stem}-{{i}}.parquet",
            existing_data_behavior="overwrite_or_ignore",
            file_options=ds.ParquetFileFormat().make_write_options(compression="zstd"),
            min_rows_per_group=100_000, max_rows_per_group=1_000_000,
        )
    return total


def ler_bronze(raiz: Path = PARQUET) -> ds.Dataset:
    """Dataset da bronze com esquema unificado (coluna ausente num ano = nula)."""
    raiz = Path(raiz)
    particao = ds.partitioning(pa.schema([("ano", pa.int16()), ("SG_UF", pa.string())]),
                               flavor="hive")
    base = ds.dataset(raiz, format="parquet", partitioning=particao)
    esquemas = [f.physical_schema for f in base.get_fragments()]
    unificado = pa.unify_schemas(esquemas, promote_options="permissive")
    for campo in particao.schema:
        if campo.name not in unificado.names:
            unificado = unificado.append(campo)
    return ds.dataset(raiz, format="parquet", partitioning=particao, schema=unificado)


def _tamanho_mb(caminhos: list[Path]) -> float:
    return sum(Path(c).stat().st_size for c in caminhos) / 1024**2


def _tempo(func: Callable[[], object]) -> float:
    t0 = time.perf_counter()
    func()
    return time.perf_counter() - t0


def benchmark(csv: Path, parquet_dir: Path = PARQUET) -> dict:
    """Compara CSV x Parquet no maior arquivo e no total; salva reports/benchmark_csv_parquet.csv."""
    csv, parquet_dir = Path(csv), Path(parquet_dir)
    ano = int(csv.stem.split("_")[-2])
    uf = csv.stem.split("_")[-1]
    part = parquet_dir / f"ano={ano}" / f"SG_UF={uf}"
    pqs = sorted(part.glob("*.parquet"))
    ler_pq = lambda: pq.read_table(part)  # noqa: E731
    ler_csv = lambda: pacsv.read_csv(  # noqa: E731
        csv, read_options=pacsv.ReadOptions(encoding=ENCODING),
        parse_options=pacsv.ParseOptions(delimiter=SEP))
    pd_csv = lambda: pd.read_csv(csv, sep=SEP, encoding=ENCODING, dtype=str)  # noqa: E731
    pd_pq = lambda: pd.read_parquet(part)  # noqa: E731

    def linha(nome: str, mb_csv: float, mb_pq: float, t_csv: float, t_pq: float) -> dict:
        return {"comparacao": nome, "tamanho_csv_mb": round(mb_csv, 2),
                "tamanho_parquet_mb": round(mb_pq, 2),
                "reducao_pct": round(100 * (1 - mb_pq / mb_csv), 1),
                "t_leitura_csv_s": round(t_csv, 2) if t_csv is not None else None,
                "t_leitura_parquet_s": round(t_pq, 2) if t_pq is not None else None}

    mb_csv, mb_pq = _tamanho_mb([csv]), _tamanho_mb(pqs)
    todos_csv = [c for c in TSE_BRONZE.rglob("*.csv")] if csv.is_relative_to(TSE_BRONZE)         else list(csv.parent.rglob("*.csv"))
    todos_pq = list(parquet_dir.rglob("*.parquet"))
    linhas = [
        linha(f"pyarrow_{csv.stem}", mb_csv, mb_pq, _tempo(ler_csv), _tempo(ler_pq)),
        linha(f"pandas_{csv.stem}", mb_csv, mb_pq, _tempo(pd_csv), _tempo(pd_pq)),
        linha("total_bronze", _tamanho_mb(todos_csv), _tamanho_mb(todos_pq), None, None),
    ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(linhas).to_csv(REPORTS / "benchmark_csv_parquet.csv", index=False)
    return linhas[0]


def _maior_csv() -> Path:
    return max(TSE_BRONZE.rglob("perfil_*_??.csv"), key=lambda c: c.stat().st_size)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Coleta TSE: perfil comparecimento/abstencao")
    p.add_argument("--anos", nargs="+", type=int, default=ANOS)
    p.add_argument("--benchmark", action="store_true",
                   help="so roda o benchmark CSV x Parquet no maior CSV")
    args = p.parse_args(argv)
    if args.benchmark:
        print(benchmark(_maior_csv(), PARQUET))
        return
    for ano in args.anos:
        csvs = coletar(ano)
        print(f"{ano}: {len(csvs)} CSVs")
        print(f"{ano}: {csv_para_parquet(csvs, ano)} linhas em Parquet")


if __name__ == "__main__":
    main()
