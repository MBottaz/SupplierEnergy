"""Comando `python -m etl FILE --db DB`: carica le offerte di un XML locale.

Fase 1: solo caricamento da file locale (la fixture). Download condizionale,
validazioni e swap atomico arrivano in fase 2.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from xml.etree.ElementTree import ParseError

from defusedxml.common import DefusedXmlException

from etl.caricamento import EsitoCaricamento, carica_offerte
from etl.db import apri_db
from etl.tempo import oggi

#: Errori strutturati: codice stabile e messaggio senza dettagli interni.
ERRORI = {
    "file_non_leggibile": "Il file indicato non è leggibile.",
    "xml_non_valido": "Il file non è un XML valido o è troncato.",
    "db_non_apribile": "Il database indicato non è apribile.",
    "errore_interno": "Errore interno durante il caricamento.",
}


def main(argomenti: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl",
        description="Carica un XML di offerte in un database SQLite.",
    )
    parser.add_argument("file", help="XML delle offerte (fase 1: la fixture)")
    parser.add_argument("--db", required=True, help="percorso del database SQLite")
    parser.add_argument(
        "--snapshot",
        default=None,
        help="data dello snapshot in formato AAAA-MM-GG (default: oggi, Europe/Rome)",
    )
    opzioni = parser.parse_args(argomenti)

    snapshot_date = opzioni.snapshot or oggi()

    try:
        conn = apri_db(opzioni.db)
    except (OSError, sqlite3.Error):
        return _errore("db_non_apribile")

    try:
        esito = carica_offerte(opzioni.file, conn, snapshot_date=snapshot_date)
    except (DefusedXmlException, ParseError):
        return _errore("xml_non_valido")
    except OSError:
        return _errore("file_non_leggibile")
    except sqlite3.Error:
        return _errore("errore_interno")
    finally:
        conn.close()

    _stampa(
        {
            "esito": "ok",
            "db": opzioni.db,
            "snapshot_date": snapshot_date,
            **_esito(esito),
        }
    )
    return 0


def _esito(esito: EsitoCaricamento) -> dict[str, object]:
    return {
        "n_offerte": esito.n_offerte,
        "n_componenti": esito.n_componenti,
        "n_condizioni": esito.n_condizioni,
        "offerte_scartate": esito.offerte_scartate,
        "percorsi_sconosciuti": list(esito.percorsi_sconosciuti),
    }


def _errore(codice: str) -> int:
    _stampa({"esito": "errore", "codice": codice, "messaggio": ERRORI[codice]}, su_errore=True)
    return 1


def _stampa(contenuto: dict[str, object], *, su_errore: bool = False) -> None:
    flusso = sys.stderr if su_errore else sys.stdout
    json.dump(contenuto, flusso, ensure_ascii=False, sort_keys=True)
    flusso.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
