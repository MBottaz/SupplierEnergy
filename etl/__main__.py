"""CLI dell'ETL.

- `python -m etl locale --db DB --raw FILE [--parametri CSV] [--snapshot AAAA-MM-GG]`
  ricarica il DB a partire da un raw già scaricato (rilancio, prove, ripristino).
- `python -m etl scarica --db DB [--url URL] [--raw-dir raw] [--parametri CSV]`
  scarica l'XML open data (condizionale: 304 o SHA-256 invariato = niente da
  fare) e poi esegue l'ETL.

L'output è JSON; gli errori hanno `codice` e `messaggio`, senza dettagli interni.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from typing import Any

from etl.download import (
    HOST_AMMESSI,
    DownloadFallito,
    DownloadTroppoGrande,
    UrlNonAmmesso,
    pulisci_vecchi,
    scarica,
)
from etl.esegui import EsitoEsecuzione, esegui, ultimo_run
from etl.tempo import oggi

#: URL open data indicato dall'utente (Portale Offerte, mercato libero elettrico).
URL_OFFERTE = (
    "https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv/offerteML/"
    "{mese}/PO_Offerte_E_MLIBERO_{giorno}.xml"
)

#: Errori strutturati: codice stabile e messaggio senza dettagli interni.
ERRORI = {
    "file_non_leggibile": "Il file raw indicato non è leggibile.",
    "xml_non_valido": "Il file raw non è un XML valido o è troncato.",
    "db_non_apribile": "Il database indicato non è apribile in scrittura.",
    "errore_interno": "Errore interno durante il caricamento.",
    "parametri_mancanti": "Mancano parametri obbligatori nel CSV indicato.",
    "nessuna_offerta": "Il file raw non contiene offerte utilizzabili.",
    "troppe_poche_offerte": "Offerte troppo poche rispetto al database in uso: swap bloccato.",
    "chiavi_nulle": "Offerte senza chiave: swap bloccato.",
    "chiavi_duplicate": "Offerte con chiave duplicata: swap bloccato.",
    "db_corrotto": "Il database nuovo non ha passato il controllo di integrità.",
    "url_non_ammesso": "URL non ammesso: servono HTTPS e un host in allowlist.",
    "download_fallito": "Download non riuscito.",
    "download_troppo_grande": "Il file scaricato supera il limite di dimensione.",
}


def url_offerte(giorno: str) -> str:
    """URL open data dell'XML offerte per il giorno ISO indicato."""
    return URL_OFFERTE.format(mese=giorno[:7].replace("-", "_"), giorno=giorno.replace("-", ""))


def main(
    argomenti: Sequence[str] | None = None,
    *,
    apri: Callable[..., AbstractContextManager[Any]] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m etl",
        description="Carica le offerte del mercato libero in un database SQLite.",
    )
    comandi = parser.add_subparsers(dest="comando", required=True)

    locale = comandi.add_parser("locale", help="carica il DB da un raw già scaricato")
    _argomenti_comuni(locale)
    locale.add_argument("--raw", required=True, help="file XML del raw locale")

    rete = comandi.add_parser("scarica", help="scarica l'XML open data e carica il DB")
    _argomenti_comuni(rete)
    rete.add_argument(
        "--url",
        default=None,
        help=f"default: URL open data del giorno; host ammessi: {', '.join(sorted(HOST_AMMESSI))}",
    )
    rete.add_argument("--raw-dir", default="raw", help="cartella dei raw datati (default: raw)")

    opzioni = parser.parse_args(argomenti)
    snapshot = opzioni.snapshot or oggi()
    if opzioni.comando == "locale":
        return _locale(opzioni, snapshot)
    return _scarica(opzioni, snapshot, apri=apri)


def _argomenti_comuni(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", required=True, help="percorso del database SQLite")
    parser.add_argument("--parametri", default=None, help="CSV dei parametri regolati")
    parser.add_argument(
        "--snapshot",
        default=None,
        help="data dello snapshot in formato AAAA-MM-GG (default: oggi, Europe/Rome)",
    )


def _locale(opzioni: argparse.Namespace, snapshot: str) -> int:
    try:
        esito = esegui(
            opzioni.raw,
            db=opzioni.db,
            snapshot_date=snapshot,
            parametri=opzioni.parametri,
            sorgente=str(opzioni.raw),
        )
    except sqlite3.Error:
        return _errore("db_non_apribile")
    return _stampa_esecuzione(esito, snapshot, sorgente=str(opzioni.raw))


def _scarica(
    opzioni: argparse.Namespace,
    snapshot: str,
    *,
    apri: Callable[..., AbstractContextManager[Any]] | None,
) -> int:
    url = opzioni.url or url_offerte(snapshot)
    precedente = ultimo_run(opzioni.db)
    sha_atteso = None
    if precedente is not None and precedente.get("esito") == "ok":
        valore = precedente.get("sha256")
        sha_atteso = valore if isinstance(valore, str) else None

    try:
        scaricato = scarica(
            url,
            cartella_raw=opzioni.raw_dir,
            giorno=snapshot,
            sha256_atteso=sha_atteso,
            apri=apri,
        )
    except UrlNonAmmesso:
        return _errore("url_non_ammesso")
    except DownloadTroppoGrande:
        return _errore("download_troppo_grande")
    except DownloadFallito:
        return _errore("download_fallito")

    if scaricato.non_modificato:
        _stampa(
            {
                "esito": "non_modificato",
                "db": opzioni.db,
                "snapshot_date": snapshot,
                "sorgente": url,
                "sha256": scaricato.sha256,
            }
        )
        return 0

    assert scaricato.percorso is not None
    try:
        esito = esegui(
            scaricato.percorso,
            db=opzioni.db,
            snapshot_date=snapshot,
            parametri=opzioni.parametri,
            sorgente=url,
            sha256=scaricato.sha256,
        )
    except sqlite3.Error:
        return _errore("db_non_apribile")

    if esito.esito == "ok":
        pulisci_vecchi(opzioni.raw_dir, oggi=snapshot)
    return _stampa_esecuzione(esito, snapshot, sorgente=url, sha256=scaricato.sha256)


def _stampa_esecuzione(
    esito: EsitoEsecuzione,
    snapshot: str,
    *,
    sorgente: str = "",
    sha256: str | None = None,
) -> int:
    if esito.esito == "errore":
        return _errore(esito.codice or "errore_interno", note=esito.note)
    _stampa(
        {
            "esito": "ok",
            "db": str(esito.db),
            "snapshot_date": snapshot,
            "sorgente": sorgente,
            "sha256": esito.sha256 or sha256,
            "n_offerte": esito.n_offerte,
            "n_parametri": esito.n_parametri,
            "percorsi_sconosciuti": list(esito.percorsi_sconosciuti),
            "etl_run_id": esito.etl_run_id,
            "note": list(esito.note),
        }
    )
    return 0


def _errore(codice: str, note: Sequence[str] = ()) -> int:
    messaggio = ERRORI.get(codice, ERRORI["errore_interno"])
    contenuto: dict[str, object] = {"esito": "errore", "codice": codice, "messaggio": messaggio}
    if note:
        contenuto["note"] = list(note)
    _stampa(contenuto, su_errore=True)
    return 1


def _stampa(contenuto: dict[str, object], *, su_errore: bool = False) -> None:
    flusso = sys.stderr if su_errore else sys.stdout
    json.dump(contenuto, flusso, ensure_ascii=False, sort_keys=True)
    flusso.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
