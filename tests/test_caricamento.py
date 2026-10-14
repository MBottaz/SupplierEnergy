"""Caricamento in SQLite: conteggi, idempotenza, extra_json, casi limite."""

import io
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from defusedxml.common import DefusedXmlException

from etl.caricamento import EsitoCaricamento, carica_offerte
from etl.db import apri_db

FIXTURE = Path(__file__).parent / "fixtures"
SNAPSHOT = "2026-10-14"


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connessione = apri_db(tmp_path / "offerte.db")
    yield connessione
    connessione.close()


def _conta(conn: sqlite3.Connection, tabella: str) -> int:
    riga = conn.execute(f"SELECT count(*) AS n FROM {tabella}").fetchone()
    assert riga is not None
    return int(riga["n"])


def _salva(conn: sqlite3.Connection, percorso: Path) -> EsitoCaricamento:
    return carica_offerte(percorso, conn, snapshot_date=SNAPSHOT)


def test_fixture_produce_una_offerta_quattro_componenti_una_condizione(
    conn: sqlite3.Connection,
) -> None:
    esito = _salva(conn, FIXTURE / "offerta_estratto.xml")

    assert esito.n_offerte == 1
    assert esito.n_componenti == 4
    assert esito.n_condizioni == 1
    assert esito.offerte_scartate == 0
    assert esito.percorsi_sconosciuti == ()

    assert _conta(conn, "offerta") == 1
    assert _conta(conn, "componente") == 4
    assert _conta(conn, "condizione") == 1


def test_valori_in_offerta(conn: sqlite3.Connection) -> None:
    _salva(conn, FIXTURE / "offerta_estratto.xml")
    riga = conn.execute("SELECT * FROM offerta").fetchone()
    assert riga is not None
    assert riga["piva"] == "01244170526"
    assert riga["cod_offerta"] == "001686ESVFL00XXPFA0726AU00000000"
    assert riga["tipo_cliente"] == "02"
    assert riga["idx_prezzo_energia"] == "12"
    assert riga["data_inizio"] == "2026-07-21T12:25:58+02:00"
    assert riga["data_fine"] == "2026-10-10T23:59:59+02:00"
    assert riga["snapshot_date"] == SNAPSHOT

    extra = json.loads(riga["extra_json"])
    assert extra["offerta/DettaglioOfferta/ModalitaAttivazione/MODALITA"] == "01"
    assert extra["offerta/Dispacciamento/NOME"] == "Dispacciamento"


def test_valori_in_componente(conn: sqlite3.Connection) -> None:
    _salva(conn, FIXTURE / "offerta_estratto.xml")
    righe = conn.execute(
        "SELECT nome, macroarea, fascia, prezzo, unita_misura FROM componente"
        " ORDER BY macroarea, fascia"
    ).fetchall()
    assert [(r["macroarea"], r["fascia"]) for r in righe] == [
        ("01", None),
        ("04", "01"),
        ("04", "02"),
        ("04", "03"),
    ]
    spread = righe[1:]
    assert [r["prezzo"] for r in spread] == [pytest.approx(0.0132)] * 3
    assert {r["unita_misura"] for r in spread} == {"03"}
    assert righe[0]["prezzo"] == pytest.approx(162.0)
    assert righe[0]["unita_misura"] == "01"
    assert all(r["prezzo"] is None or isinstance(r["prezzo"], float) for r in righe)


def test_valori_in_condizione(conn: sqlite3.Connection) -> None:
    _salva(conn, FIXTURE / "offerta_estratto.xml")
    riga = conn.execute("SELECT * FROM condizione").fetchone()
    assert riga is not None
    assert riga["tipologia"] == "03"
    assert riga["limitante"] == "02"
    assert riga["descrizione"] == "Il contratto è a tempo indeterminato."


def test_codifica_caricata(conn: sqlite3.Connection) -> None:
    _salva(conn, FIXTURE / "offerta_estratto.xml")
    riga = conn.execute(
        "SELECT descrizione FROM codifica WHERE dominio = 'tipo_cliente' AND codice = '02'"
    ).fetchone()
    assert riga is not None
    assert riga["descrizione"] == "Altri Usi"
    assert _conta(conn, "codifica") > 20


def test_caricamento_idempotente(conn: sqlite3.Connection) -> None:
    _salva(conn, FIXTURE / "offerta_estratto.xml")
    _salva(conn, FIXTURE / "offerta_estratto.xml")
    assert _conta(conn, "offerta") == 1
    assert _conta(conn, "componente") == 4
    assert _conta(conn, "condizione") == 1


def test_nuovo_caricamento_sostituisce_le_componenti(conn: sqlite3.Connection) -> None:
    _salva(conn, FIXTURE / "offerta_estratto.xml")
    testo = (FIXTURE / "offerta_estratto.xml").read_text(encoding="utf-8")
    aggiornato = testo.replace("POWER FLEX AZIENDA", "POWER FLEX AZIENDA 2").replace(
        "<IntervalloPrezzi>\n<FASCIA_COMPONENTE>03</FASCIA_COMPONENTE>"
        "\n<PREZZO>0.0132</PREZZO>\n<UNITA_MISURA>03</UNITA_MISURA>\n</IntervalloPrezzi>\n",
        "",
    )
    assert aggiornato != testo

    esito = carica_offerte(io.BytesIO(aggiornato.encode("utf-8")), conn, snapshot_date="2026-10-15")
    assert esito.n_componenti == 3
    assert _conta(conn, "componente") == 3
    riga = conn.execute("SELECT nome, snapshot_date FROM offerta").fetchone()
    assert riga is not None
    assert riga["nome"] == "POWER FLEX AZIENDA 2"
    assert riga["snapshot_date"] == "2026-10-15"


def test_elemento_inventato_non_fa_fallire(conn: sqlite3.Connection) -> None:
    esito = _salva(conn, FIXTURE / "offerta_elemento_sconosciuto.xml")

    assert esito.n_offerte == 1
    assert esito.n_componenti == 1
    assert esito.percorsi_sconosciuti == (
        "offerta/ComponenteImpresa/ELEMENTO_COMPONENTE_INVENTATO",
        "offerta/DettaglioOfferta/ELEMENTO_INVENTATO",
    )

    offerta = conn.execute("SELECT extra_json FROM offerta").fetchone()
    assert offerta is not None
    assert json.loads(offerta["extra_json"])["offerta/DettaglioOfferta/ELEMENTO_INVENTATO"] == (
        "valore-inventato"
    )

    componente = conn.execute("SELECT extra_json FROM componente").fetchone()
    assert componente is not None
    assert (
        json.loads(componente["extra_json"])[
            "offerta/ComponenteImpresa/ELEMENTO_COMPONENTE_INVENTATO"
        ]
        == "valore-componente"
    )


def test_entita_esterne_non_caricate(conn: sqlite3.Connection) -> None:
    with pytest.raises(DefusedXmlException):
        _salva(conn, FIXTURE / "offerta_entita_esterna.xml")
    assert _conta(conn, "offerta") == 0


def test_xml_troncato_non_lascia_righe(conn: sqlite3.Connection) -> None:
    troncato = (FIXTURE / "offerta_estratto.xml").read_text(encoding="utf-8")[:200]
    with pytest.raises(Exception):  # noqa: B017 - l'errore di expat non è stabile
        carica_offerte(io.BytesIO(troncato.encode("utf-8")), conn, snapshot_date=SNAPSHOT)
    assert _conta(conn, "offerta") == 0
    assert _conta(conn, "componente") == 0


def test_offerta_senza_chiave_viene_scartata(conn: sqlite3.Connection) -> None:
    xml = (
        "<ListaOfferteMercatoLibero>"
        "<offerta><DettaglioOfferta><NOME_OFFERTA>SENZA CHIAVE</NOME_OFFERTA>"
        "</DettaglioOfferta></offerta>"
        "</ListaOfferteMercatoLibero>"
    )
    esito = carica_offerte(io.BytesIO(xml.encode("utf-8")), conn, snapshot_date=SNAPSHOT)
    assert esito.n_offerte == 0
    assert esito.offerte_scartate == 1
    assert _conta(conn, "offerta") == 0
