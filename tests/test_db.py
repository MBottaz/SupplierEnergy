"""Livello di accesso read-only al database (`offerte.db`)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from offerte.db import apri_db
from offerte.errori import DatabaseNonDisponibile
from tests.fixture_db import crea_db, offerta


def _sha256(percorso: Path) -> str:
    return hashlib.sha256(percorso.read_bytes()).hexdigest()


def test_ricerca_base_e_query_only(tmp_path: Path) -> None:
    db = crea_db(tmp_path / "offerte.db", [offerta("11111111111", "A1")])

    with apri_db(db) as conn:
        riga = conn.execute(
            "SELECT piva, cod_offerta FROM offerta WHERE piva = ?", ("11111111111",)
        ).fetchone()
        assert riga is not None
        assert riga["cod_offerta"] == "A1"
        assert conn.execute("PRAGMA query_only").fetchone()[0] == 1


def test_la_scrittura_fallisce(tmp_path: Path) -> None:
    db = crea_db(tmp_path / "offerte.db", [offerta("11111111111", "A1")])

    with apri_db(db) as conn, pytest.raises(sqlite3.Error):
        conn.execute(
            "INSERT INTO offerta (piva, cod_offerta, snapshot_date)"
            " VALUES ('22222222222', 'A2', '2026-10-14')"
        )

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM offerta").fetchone() == (1,)


def test_db_invariato_dopo_ricerca_e_errore(tmp_path: Path) -> None:
    db = crea_db(tmp_path / "offerte.db", [offerta("11111111111", "A1")])
    prima = _sha256(db)

    with apri_db(db) as conn:
        conn.execute("SELECT * FROM offerta").fetchall()

    with apri_db(db) as conn, pytest.raises(sqlite3.Error):
        conn.execute("SELECT * FROM tabella_inesistente").fetchall()

    assert _sha256(db) == prima


def test_file_inesistente(tmp_path: Path) -> None:
    with pytest.raises(DatabaseNonDisponibile) as errore, apri_db(tmp_path / "manca.db"):
        pass
    assert errore.value.codice == "database_non_disponibile"
    assert str(tmp_path) not in errore.value.messaggio


def test_percorso_directory(tmp_path: Path) -> None:
    with pytest.raises(DatabaseNonDisponibile), apri_db(tmp_path):
        pass


def test_file_non_database(tmp_path: Path) -> None:
    finto = tmp_path / "finto.db"
    finto.write_text("non sono un database sqlite", encoding="utf-8")

    with pytest.raises(DatabaseNonDisponibile), apri_db(finto):
        pass


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora i permessi del file")
def test_file_non_leggibile(tmp_path: Path) -> None:
    db = crea_db(tmp_path / "offerte.db", [])
    db.chmod(0o000)
    try:
        with pytest.raises(DatabaseNonDisponibile), apri_db(db):
            pass
    finally:
        db.chmod(0o644)
