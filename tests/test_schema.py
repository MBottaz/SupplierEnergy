"""Schema SQLite: tabelle, chiavi e vincoli minimi (docs/architettura.md §6)."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from etl.db import apri_db

COLONNE_ATTESE: dict[str, tuple[str, ...]] = {
    "offerta": (
        "piva",
        "cod_offerta",
        "nome",
        "descrizione",
        "tipo_mercato",
        "offerta_singola",
        "tipo_cliente",
        "tipo_offerta",
        "tipologia_att_contr",
        "durata",
        "garanzie",
        "idx_prezzo_energia",
        "data_inizio",
        "data_fine",
        "modalita_pagamento",
        "tipo_dispacciamento",
        "url_sito",
        "url_offerta",
        "telefono",
        "extra_json",
        "snapshot_date",
    ),
    "componente": (
        "piva",
        "cod_offerta",
        "nome",
        "descrizione",
        "tipologia",
        "macroarea",
        "fascia",
        "prezzo",
        "unita_misura",
        "extra_json",
    ),
    "condizione": ("piva", "cod_offerta", "tipologia", "descrizione", "limitante"),
    "codifica": ("dominio", "codice", "descrizione"),
    "parametro": ("nome", "valore", "descrizione", "riferimento"),
    "pun": ("data", "valore_eur_mwh", "serie"),
    "etl_run": (
        "id",
        "inizio",
        "fine",
        "esito",
        "sorgente",
        "sha256",
        "n_offerte",
        "percorsi_sconosciuti",
        "note",
    ),
}


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connessione = apri_db(tmp_path / "offerte.db")
    yield connessione
    connessione.close()


def test_tabelle_e_colonne(conn: sqlite3.Connection) -> None:
    righe = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    assert {riga["name"] for riga in righe} == set(COLONNE_ATTESE)

    for tabella, attese in COLONNE_ATTESE.items():
        presenti = {
            riga["name"] for riga in conn.execute(f"PRAGMA table_info({tabella})").fetchall()
        }
        assert presenti == set(attese), tabella


def test_chiavi_primarie(conn: sqlite3.Connection) -> None:
    chiavi = {
        tabella: tuple(
            riga["name"]
            for riga in conn.execute(f"PRAGMA table_info({tabella})").fetchall()
            if riga["pk"]
        )
        for tabella in COLONNE_ATTESE
    }
    assert chiavi["offerta"] == ("piva", "cod_offerta")
    assert chiavi["codifica"] == ("dominio", "codice")
    assert chiavi["parametro"] == ("nome", "riferimento")
    assert chiavi["pun"] == ("data", "serie")
    assert chiavi["etl_run"] == ("id",)
    assert chiavi["componente"] == ()
    assert chiavi["condizione"] == ()


def test_offerta_richiede_chiave_e_snapshot(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO offerta (piva, cod_offerta) VALUES ('1', 'x')")


def test_extra_json_deve_essere_json(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO offerta (piva, cod_offerta, snapshot_date) VALUES ('1', 'x', '2026-10-14')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE offerta SET extra_json = 'non-json' WHERE cod_offerta = 'x'")


def test_componente_orfano_rifiutato(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO componente (piva, cod_offerta, nome) VALUES ('1', 'assente', 'SPREAD')"
        )


def test_apri_db_e_ricreabile(tmp_path: Path) -> None:
    percorso = tmp_path / "offerte.db"
    apri_db(percorso).close()
    apri_db(percorso).close()  # idempotente: nessun errore la seconda volta
    assert percorso.exists()
