"""CSV dei parametri regolati: lettura, riferimento, caricamento, obbligatori."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from etl.db import apri_db
from etl.parametri import (
    OBBLIGATORI,
    carica_parametri,
    leggi_parametri,
    parametri_obbligatori_mancanti,
    riferimento_da_nome,
)

FIXTURE = Path(__file__).parent / "fixtures" / "PO_Parametri_Mercato_Libero_E_20261014.csv"
REALE = Path(__file__).parent.parent / "docs" / "PO_Parametri_Mercato_Libero_E_20261014.csv"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connessione = apri_db(tmp_path / "offerte.db")
    yield connessione
    connessione.close()


def test_riferimento_dalla_data_nel_nome() -> None:
    assert riferimento_da_nome("PO_Parametri_Mercato_Libero_E_20261014.csv") == "2026-10-14"
    assert riferimento_da_nome(Path("/tmp") / "PO_Parametri_Mercato_Libero_E_20260928.csv") == (
        "2026-09-28"
    )


def test_nome_non_riconosciuto() -> None:
    with pytest.raises(ValueError, match="riferimento"):
        riferimento_da_nome("parametri.csv")


def test_lettura_fixture() -> None:
    righe = leggi_parametri(FIXTURE)
    assert [riga.nome for riga in righe] == [
        "pcv_a",
        "pcv_c",
        "iva_a",
        "iva_c",
        "lambda",
        "acc_a_h_h",
    ]
    assert all(riga.riferimento == "2026-10-14" for riga in righe)
    assert righe[0].valore == "23.04"
    assert righe[0].descrizione == "Quota fissa non domestico"
    assert righe[5].valore == "4820.000000"


def test_caricamento_e_idempotenza(conn: sqlite3.Connection) -> None:
    esito = carica_parametri(conn, FIXTURE)
    assert esito.n_parametri == 6
    assert esito.riferimento == "2026-10-14"
    assert esito.mancanti == ()

    riga = conn.execute(
        "SELECT valore, descrizione FROM parametro WHERE nome = ? AND riferimento = ?",
        ("pcv_a", "2026-10-14"),
    ).fetchone()
    assert riga is not None
    assert riga["valore"] == "23.04"
    assert riga["descrizione"] == "Quota fissa non domestico"

    carica_parametri(conn, FIXTURE)
    n = conn.execute("SELECT count(*) AS n FROM parametro").fetchone()["n"]
    assert n == 6


def test_obbligatori_mancanti(tmp_path: Path, conn: sqlite3.Connection) -> None:
    parziale = tmp_path / "PO_Parametri_Mercato_Libero_E_20261014.csv"
    parziale.write_text("nome_parametro,valore,descrizione\npcv_a,23.04,Quota fissa\n")

    esito = carica_parametri(conn, parziale)
    assert esito.n_parametri == 1
    assert esito.mancanti == ("iva_a", "iva_c", "lambda", "pcv_c")

    assert parametri_obbligatori_mancanti(["pcv_a", "pcv_c", "iva_a", "iva_c", "lambda"]) == ()
    assert set(OBBLIGATORI) == {"pcv_a", "pcv_c", "iva_a", "iva_c", "lambda"}


def test_file_reale_dei_parametri(conn: sqlite3.Connection) -> None:
    if not REALE.exists():
        pytest.skip("CSV dei parametri non presente in docs/")

    esito = carica_parametri(conn, REALE)
    assert esito.n_parametri == 100
    assert esito.riferimento == "2026-10-14"
    assert esito.mancanti == ()

    vuoti = conn.execute(
        "SELECT count(*) AS n FROM parametro WHERE valore IS NULL OR valore = ''"
    ).fetchone()["n"]
    assert vuoti == 0
