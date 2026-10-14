"""Esecuzione completa dell'ETL: DB nuovo, validazioni, swap atomico (§8).

Ordine:

1. si costruisce un DB nuovo (`offerte.db.new`) e si copia dal DB in uso solo
   `parametro`, `pun` ed `etl_run` (storico);
2. si caricano offerte e parametri;
3. `PRAGMA integrity_check`, chiavi nulle o duplicate, calo delle offerte,
   parametri obbligatori (il PUN è solo un avviso);
4. se tutto passa: la versione in uso diventa `offerte.db.prev` e il DB nuovo
   prende il suo posto; altrimenti il DB in uso resta intatto, l'errore finisce
   in `etl_run` e l'esito è "errore".
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from etl.caricamento import EsitoCaricamento, carica_offerte
from etl.db import apri_db
from etl.parametri import carica_parametri
from etl.tempo import FUSO, oggi

#: Oltre questa soglia (frazione della esecuzione precedente) lo swap è bloccato.
FRAZIONE_MINIMA_OFFERTE = 0.5

#: Il PUN più vecchio di così produce solo un avviso.
GIORNI_PUN_RECENTE = 7

TABELLE_STORICO: dict[str, tuple[str, ...]] = {
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


class _Blocco(ValueError):
    """Un controllo di validazione non è passato: il DB nuovo non si usa."""

    def __init__(self, codice: str, note: list[str]) -> None:
        super().__init__(codice)
        self.codice = codice
        self.note = note


@dataclass(frozen=True)
class EsitoEsecuzione:
    """Esito di un'esecuzione dell'ETL."""

    esito: str
    db: Path
    codice: str | None = None
    note: tuple[str, ...] = ()
    n_offerte: int = 0
    n_parametri: int = 0
    sha256: str | None = None
    percorsi_sconosciuti: tuple[str, ...] = ()
    etl_run_id: int | None = None

    @property
    def non_modificato(self) -> bool:
        """True se lo swap non è avvenuto (nessuna offerta nuova da caricare)."""
        return self.esito == "non_modificato"


def esegui(
    raw_xml: str | Path,
    *,
    db: str | Path,
    snapshot_date: str | None = None,
    parametri: str | Path | None = None,
    sorgente: str = "",
    sha256: str | None = None,
) -> EsitoEsecuzione:
    """Esegue l'ETL in `db` e fa lo swap solo se le validazioni passano."""
    percorso_db = Path(db)
    nuovo = percorso_db.with_name(percorso_db.name + ".new")
    snapshot = snapshot_date or oggi()
    inizio = _adesso()
    sha256 = sha256 or _sha256_file(raw_xml)
    precedenti = _offerte_in_uso(percorso_db)
    nuovo.unlink(missing_ok=True)

    conn = apri_db(nuovo)
    codice: str | None = None
    note: list[str] = []
    caricate = EsitoCaricamento(0, 0, 0, 0, ())
    n_parametri = 0
    etl_run_id: int | None = None
    try:
        try:
            _copia_storico(conn, percorso_db)
            caricate = carica_offerte(raw_xml, conn, snapshot_date=snapshot)
            if caricate.offerte_scartate:
                note.append(f"offerte scartate senza chiave: {caricate.offerte_scartate}")
            mancanti, n_parametri = _carica_o_controlla_parametri(conn, parametri, note)
            _validazioni(
                conn,
                caricate=caricate,
                mancanti=mancanti,
                parametri_forniti=parametri is not None,
                precedenti=precedenti,
                note=note,
            )
            etl_run_id = _registra(
                conn,
                inizio=inizio,
                esito="ok",
                sorgente=sorgente,
                sha256=sha256,
                n_offerte=caricate.n_offerte,
                percorsi=len(caricate.percorsi_sconosciuti),
                note=note,
            )
            conn.commit()
        except _Blocco as blocco:
            codice, note = blocco.codice, list(blocco.note)
        except (DefusedXmlException, ParseError):
            codice = "xml_non_valido"
            note = ["XML non valido o troncato"]
        except OSError:
            codice = "file_non_leggibile"
            note = ["il file raw non è leggibile"]
        except sqlite3.Error:
            codice = "errore_interno"
            note = ["errore del database durante il caricamento"]
    finally:
        conn.close()

    if codice is not None:
        nuovo.unlink(missing_ok=True)
        _registra_errore_in_uso(
            percorso_db,
            inizio=inizio,
            sorgente=sorgente,
            sha256=sha256,
            codice=codice,
            note=note,
        )
        return EsitoEsecuzione(esito="errore", db=percorso_db, codice=codice, note=tuple(note))

    _swap(percorso_db, nuovo)
    return EsitoEsecuzione(
        esito="ok",
        db=percorso_db,
        note=tuple(note),
        n_offerte=caricate.n_offerte,
        n_parametri=n_parametri,
        sha256=sha256,
        percorsi_sconosciuti=caricate.percorsi_sconosciuti,
        etl_run_id=etl_run_id,
    )


def ultimo_run(db: str | Path) -> dict[str, object] | None:
    """L'ultima riga di `etl_run` del DB indicato, se il DB esiste."""
    percorso = Path(db)
    if not percorso.is_file():
        return None
    with sqlite3.connect(f"file:{percorso}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        riga = conn.execute("SELECT * FROM etl_run ORDER BY id DESC LIMIT 1").fetchone()
    return dict(riga) if riga is not None else None


def _carica_o_controlla_parametri(
    conn: sqlite3.Connection, parametri: str | Path | None, note: list[str]
) -> tuple[tuple[str, ...], int]:
    """Carica il CSV dei parametri (se c'è) e dice quali obbligatori mancano."""
    if parametri is None:
        mancanti = _parametri_mancanti(conn)
        if mancanti:
            note.append("nessun CSV dei parametri fornito: assenti " + ", ".join(mancanti))
        return mancanti, 0
    esito = carica_parametri(conn, parametri)
    return esito.mancanti, esito.n_parametri


def _validazioni(
    conn: sqlite3.Connection,
    *,
    caricate: EsitoCaricamento,
    mancanti: tuple[str, ...],
    parametri_forniti: bool,
    precedenti: int | None,
    note: list[str],
) -> None:
    if caricate.n_offerte == 0:
        raise _Blocco("nessuna_offerta", ["l'XML non contiene offerte con chiave"])
    if mancanti and parametri_forniti:
        raise _Blocco(
            "parametri_mancanti", ["parametri obbligatori assenti: " + ", ".join(mancanti)]
        )
    if precedenti is not None and caricate.n_offerte < precedenti * FRAZIONE_MINIMA_OFFERTE:
        raise _Blocco(
            "troppe_poche_offerte",
            [f"offerte caricate {caricate.n_offerte}, meno del 50% delle {precedenti} precedenti"],
        )
    _controlla_integrita(conn)
    _controlla_chiavi(conn)
    nota_pun = _nota_pun(conn)
    if nota_pun is not None:
        note.append(nota_pun)


def _controlla_integrita(conn: sqlite3.Connection) -> None:
    riga = conn.execute("PRAGMA integrity_check").fetchone()
    if riga is None or riga[0] != "ok":
        raise _Blocco("db_corrotto", [f"integrity_check: {riga[0] if riga else 'nessun esito'}"])


def _controlla_chiavi(conn: sqlite3.Connection) -> None:
    nulle = conn.execute(
        "SELECT count(*) FROM offerta WHERE piva IS NULL OR cod_offerta IS NULL"
    ).fetchone()[0]
    if nulle:
        raise _Blocco("chiavi_nulle", [f"offerte con chiave nulla: {nulle}"])
    duplicate = conn.execute(
        "SELECT count(*) FROM ("
        "  SELECT 1 FROM offerta GROUP BY piva, cod_offerta HAVING count(*) > 1"
        ")"
    ).fetchone()[0]
    if duplicate:
        raise _Blocco("chiavi_duplicate", [f"chiavi duplicate: {duplicate}"])


def _nota_pun(conn: sqlite3.Connection) -> str | None:
    riga = conn.execute("SELECT max(data) FROM pun").fetchone()
    ultimo = riga[0] if riga is not None else None
    if not isinstance(ultimo, str):
        return None
    limite = date.fromisoformat(oggi()) - timedelta(days=GIORNI_PUN_RECENTE)
    if date.fromisoformat(ultimo[:10]) < limite:
        return f"PUN fermo al {ultimo[:10]} (solo avviso)"
    return None


def _parametri_mancanti(conn: sqlite3.Connection) -> tuple[str, ...]:
    from etl.parametri import parametri_obbligatori_mancanti

    nomi = [riga[0] for riga in conn.execute("SELECT DISTINCT nome FROM parametro")]
    return parametri_obbligatori_mancanti(nomi)


def _copia_storico(conn: sqlite3.Connection, percorso_db: Path) -> None:
    """Porta nel DB nuovo `parametro`, `pun` ed `etl_run` dal DB in uso.

    Con una seconda connessione in sola lettura: `ATTACH` + `DETACH` si
    bloccherebbe sulla transazione di lettura ancora aperta.
    """
    if not percorso_db.is_file():
        return
    with sqlite3.connect(f"file:{percorso_db}?mode=ro", uri=True) as vecchio:
        for tabella, colonne in TABELLE_STORICO.items():
            elenco = ", ".join(colonne)
            segnaposto = ", ".join("?" for _ in colonne)
            righe = [tuple(riga) for riga in vecchio.execute(f"SELECT {elenco} FROM {tabella}")]
            conn.executemany(
                f"INSERT OR IGNORE INTO {tabella} ({elenco}) VALUES ({segnaposto})", righe
            )


def _offerte_in_uso(percorso_db: Path) -> int | None:
    """Quante offerte ha il DB in uso (None se non esiste o non è leggibile)."""
    if not percorso_db.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{percorso_db}?mode=ro", uri=True) as conn:
            return int(conn.execute("SELECT count(*) FROM offerta").fetchone()[0])
    except sqlite3.Error:
        return None


def _registra(
    conn: sqlite3.Connection,
    *,
    inizio: str,
    esito: str,
    sorgente: str,
    sha256: str | None,
    n_offerte: int,
    percorsi: int,
    note: list[str],
) -> int:
    cursore = conn.execute(
        "INSERT INTO etl_run (inizio, fine, esito, sorgente, sha256, n_offerte,"
        " percorsi_sconosciuti, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (inizio, _adesso(), esito, sorgente[:200], sha256, n_offerte, percorsi, "; ".join(note)),
    )
    assert cursore.lastrowid is not None
    return cursore.lastrowid


def _registra_errore_in_uso(
    percorso_db: Path,
    *,
    inizio: str,
    sorgente: str,
    sha256: str | None,
    codice: str,
    note: list[str],
) -> None:
    """Annota l'errore nel DB in uso, se c'è. Non deve far fallire l'esito."""
    if not percorso_db.is_file():
        return
    try:
        with apri_db(percorso_db) as conn:
            conn.execute(
                "INSERT INTO etl_run (inizio, fine, esito, sorgente, sha256, note)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (inizio, _adesso(), "errore", sorgente[:200], sha256, "; ".join([codice, *note])),
            )
    except sqlite3.Error:
        return


def _swap(percorso_db: Path, nuovo: Path) -> None:
    """Rende `nuovo` il DB in uso, spostando il precedente in `.prev`."""
    if percorso_db.exists():
        os.replace(percorso_db, percorso_db.with_name(percorso_db.name + ".prev"))
    os.replace(nuovo, percorso_db)


def _sha256_file(percorso: str | Path | object) -> str | None:
    """SHA-256 del raw, se è un file; `None` per gli stream (test)."""
    cammino = Path(percorso) if isinstance(percorso, (str, Path)) else None
    if cammino is None or not cammino.is_file():
        return None
    impronta = hashlib.sha256()
    with cammino.open("rb") as flusso:
        while pezzo := flusso.read(1024 * 1024):
            impronta.update(pezzo)
    return impronta.hexdigest()


def _adesso() -> str:
    from datetime import datetime

    return datetime.now(FUSO).isoformat(timespec="seconds")
