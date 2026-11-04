"""Readiness del server MCP e apertura esplicita del bind non-loopback."""

from __future__ import annotations

from pathlib import Path

import pytest

from offerte.mcp import _argomenti, main, valida_host, verifica_avvio
from tests.fixture_db import crea_db, offerta

VARIABILE = "OFFERTE_MCP_CONSENTI_NON_LOOPBACK"


def test_valida_host_ammette_loopback() -> None:
    for host in ("127.0.0.1", "::1", "localhost"):
        assert valida_host(host) == host


def test_valida_host_rifiuta_non_loopback_per_default() -> None:
    with pytest.raises(ValueError, match="loopback"):
        valida_host("0.0.0.0")


def test_valida_host_ammette_non_loopback_con_consenso() -> None:
    assert valida_host("0.0.0.0", consenti_non_loopback=True) == "0.0.0.0"


def test_consenso_non_loopback_dall_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VARIABILE, "1")
    assert _argomenti([]).consenti_bind_non_loopback is True


def test_consenso_non_loopback_falso_per_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VARIABILE, raising=False)
    assert _argomenti([]).consenti_bind_non_loopback is False


def test_verifica_database_assente(tmp_path: Path) -> None:
    codice, stato = verifica_avvio(tmp_path / "manca.db")

    assert codice == 1
    assert stato["stato"] == "database_assente"


def test_verifica_database_pronto(tmp_path: Path) -> None:
    db = crea_db(tmp_path / "offerte.db", [])

    codice, stato = verifica_avvio(db)

    assert codice == 0
    assert stato["stato"] == "pronto"


def test_verifica_file_non_sqlite(tmp_path: Path) -> None:
    rotto = tmp_path / "rotto.db"
    rotto.write_bytes(b"non sono un database sqlite")

    codice, stato = verifica_avvio(rotto)

    assert codice == 2
    assert stato["stato"] == "database_non_leggibile"


def test_verifica_errore_di_permessi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vero = Path.is_file

    def finto(self: Path) -> bool:
        if self.name == "vietato.db":
            raise PermissionError(13, "negato")
        return vero(self)

    monkeypatch.setattr(Path, "is_file", finto)

    codice, stato = verifica_avvio(tmp_path / "vietato.db")

    assert codice == 2
    assert stato["stato"] == "database_non_leggibile"


def test_main_verifica_assente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    codice = main(["--verifica", "--db", str(tmp_path / "manca.db")])

    assert codice == 1
    assert "database_assente" in capsys.readouterr().out


def test_main_verifica_pronto(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = crea_db(tmp_path / "offerte.db", [offerta("11111111111", "A1")])

    codice = main(["--verifica", "--db", str(db)])

    assert codice == 0
    assert "pronto" in capsys.readouterr().out
