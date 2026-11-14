"""Testes da coleta TSE (sem acesso a rede)."""
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from src import coleta

FIXTURE = Path(__file__).parent / "fixtures" / "amostra_tse.csv"


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a_AC.csv", "A;B\n1;2\n")
        z.writestr("a_BRASIL.csv", "A;B\n1;2\n")
    return buf.getvalue()


def _resposta(conteudo: bytes) -> MagicMock:
    r = MagicMock()
    r.iter_content.return_value = [conteudo]
    r.raise_for_status.return_value = None
    r.__enter__.return_value = r
    r.__exit__.return_value = False
    return r


@pytest.fixture(autouse=True)
def sem_sleep():
    with patch("src.coleta.time.sleep"):
        yield


def test_baixar_pula_arquivo_existente(tmp_path):
    destino = tmp_path / "x.zip"
    destino.write_bytes(_zip_bytes())
    with patch("src.coleta.requests.get") as get:
        assert coleta.baixar("http://x", destino) == destino
    get.assert_not_called()


def test_baixar_refaz_zip_corrompido(tmp_path):
    destino = tmp_path / "x.zip"
    destino.write_bytes(b"lixo")
    with patch("src.coleta.requests.get", return_value=_resposta(_zip_bytes())) as get:
        coleta.baixar("http://x", destino)
    assert get.call_count == 1
    assert zipfile.is_zipfile(destino)
    assert not destino.with_suffix(".part").exists()


def test_baixar_repete_apos_falha(tmp_path):
    destino = tmp_path / "x.zip"
    efeitos = [requests.ConnectionError("a"), requests.ConnectionError("b"), _resposta(_zip_bytes())]
    with patch("src.coleta.requests.get", side_effect=efeitos) as get:
        coleta.baixar("http://x", destino)
    assert get.call_count == 3
    assert zipfile.is_zipfile(destino)


def test_baixar_desiste_apos_tentativas(tmp_path):
    destino = tmp_path / "x.zip"
    with patch("src.coleta.requests.get", side_effect=requests.ConnectionError("x")) as get:
        with pytest.raises(requests.ConnectionError):
            coleta.baixar("http://x", destino, tentativas=3)
    assert get.call_count == 3
    assert not destino.exists()


def test_extrair_ignora_brasil(tmp_path):
    z = tmp_path / "x.zip"
    z.write_bytes(_zip_bytes())
    arquivos = coleta.extrair_csvs(z, tmp_path / "out")
    assert [a.name for a in arquivos] == ["a_AC.csv"]


def test_metadados_conta_linhas_colunas(tmp_path, monkeypatch):
    monkeypatch.setattr(coleta, "REPORTS", tmp_path)
    df = coleta.registrar_metadados([FIXTURE], "http://x", 2024)
    linha = df.iloc[0]
    assert linha["n_linhas"] == 30
    assert linha["n_colunas"] == 43
    assert linha["tamanho_bytes"] == FIXTURE.stat().st_size
    assert list(df.columns) == ["ano", "url", "arquivo", "data_download", "n_linhas", "n_colunas", "tamanho_bytes"]


def test_metadados_nao_duplica(tmp_path, monkeypatch):
    monkeypatch.setattr(coleta, "REPORTS", tmp_path)
    coleta.registrar_metadados([FIXTURE], "http://x", 2024)
    coleta.registrar_metadados([FIXTURE], "http://x", 2024)
    import pandas as pd
    assert len(pd.read_csv(tmp_path / "metadados_coleta.csv")) == 1
