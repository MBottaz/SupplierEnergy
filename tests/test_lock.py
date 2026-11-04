"""Lock ETL: una sola esecuzione alla volta, anche fra container."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from etl.__main__ import EXIT_LOCK, main
from etl.lock import ETLInCorso, blocco_etl

FIXTURE_XML = Path(__file__).parent / "fixtures" / "offerta_estratto.xml"
FIXTURE_CSV = Path(__file__).parent / "fixtures" / "PO_Parametri_Mercato_Libero_E_20261014.csv"


def test_lock_esclusivo_nello_stesso_processo(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"

    with blocco_etl(db), pytest.raises(ETLInCorso), blocco_etl(db):
        pass


def test_lock_rilasciato_dopo_il_blocco(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"

    with blocco_etl(db):
        pass

    with blocco_etl(db):
        pass


def test_lock_creato_nella_directory_del_db(tmp_path: Path) -> None:
    db = tmp_path / "sottocartella" / "offerte.db"

    with blocco_etl(db) as percorso_lock:
        assert percorso_lock == db.parent / "etl.lock"
        assert percorso_lock.is_file()


def test_main_rifiuta_etl_sovrapposto(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "offerte.db"

    with blocco_etl(db):
        codice = main(
            [
                "locale",
                "--db",
                str(db),
                "--raw",
                str(FIXTURE_XML),
                "--parametri",
                str(FIXTURE_CSV),
                "--snapshot",
                "2026-10-14",
            ]
        )

    assert codice == EXIT_LOCK
    errore = json.loads(capsys.readouterr().err)
    assert errore["codice"] == "etl_in_corso"
    assert not db.exists()


def test_main_esegue_con_lock_libero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "offerte.db"

    codice = main(
        [
            "locale",
            "--db",
            str(db),
            "--raw",
            str(FIXTURE_XML),
            "--parametri",
            str(FIXTURE_CSV),
            "--snapshot",
            "2026-10-14",
        ]
    )

    assert codice == 0
    assert json.loads(capsys.readouterr().out)["esito"] == "ok"
    assert (db.parent / "etl.lock").is_file()
