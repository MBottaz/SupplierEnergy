"""Comando `python -m etl`: carica un XML e riporta l'esito in JSON."""

import json
import sqlite3
from pathlib import Path

import pytest

from etl.__main__ import main

FIXTURE = Path(__file__).parent / "fixtures" / "offerta_estratto.xml"


def test_carica_la_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "offerte.db"
    assert main(["--db", str(db), str(FIXTURE)]) == 0

    esito = json.loads(capsys.readouterr().out)
    assert esito["esito"] == "ok"
    assert esito["n_offerte"] == 1
    assert esito["n_componenti"] == 4
    assert esito["n_condizioni"] == 1
    assert esito["offerte_scartate"] == 0
    assert esito["percorsi_sconosciuti"] == []

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM offerta").fetchone() == (1,)


def test_snapshot_esplicito(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "offerte.db"
    assert main(["--db", str(db), "--snapshot", "2026-10-14", str(FIXTURE)]) == 0
    esito = json.loads(capsys.readouterr().out)
    assert esito["snapshot_date"] == "2026-10-14"

    with sqlite3.connect(db) as conn:
        riga = conn.execute("SELECT snapshot_date FROM offerta").fetchone()
    assert riga == ("2026-10-14",)


def test_xml_non_valido_esce_con_errore_strutturato(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rotto = tmp_path / "rotto.xml"
    rotto.write_text(FIXTURE.read_text(encoding="utf-8")[:200], encoding="utf-8")
    db = tmp_path / "offerte.db"

    assert main(["--db", str(db), str(rotto)]) == 1

    catturato = capsys.readouterr()
    errore = json.loads(catturato.err)
    assert errore["esito"] == "errore"
    assert errore["codice"] == "xml_non_valido"
    assert errore["messaggio"]
    assert "Traceback" not in catturato.err
    assert str(tmp_path) not in catturato.err
    assert catturato.out == ""


def test_file_inesistente_esce_con_errore(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--db", str(tmp_path / "offerte.db"), str(tmp_path / "manca.xml")]) == 1
    errore = json.loads(capsys.readouterr().err)
    assert errore["codice"] == "file_non_leggibile"
