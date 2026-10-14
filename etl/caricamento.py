"""Caricamento delle offerte in SQLite.

Regole:

- tutto il caricamento sta in una transazione: un XML troncato o un errore di
  parsing non lascia righe a metà;
- un'offerta senza `piva`/`cod_offerta` viene scartata e contata, non fa
  fallire il caricamento (il parser è tollerante);
- un secondo caricamento della stessa offerta sostituisce componenti e
  condizioni, non le duplica;
- i prezzi arrivano dal parser come `Decimal` e vengono salvati REAL.

`carica_offerte` è usato dall'ETL; le interfacce di sola lettura stanno
altrove (fase 4/5).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import IO, Any

from etl.codifiche import DECODIFICHE
from etl.parser import Componente, Offerta, iter_offerte, json_extra

COLONNE_OFFERTA = (
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
)

COLONNE_COMPONENTE = (
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
)

COLONNE_CONDIZIONE = ("piva", "cod_offerta", "tipologia", "descrizione", "limitante")


@dataclass(frozen=True)
class EsitoCaricamento:
    """Quello che l'ETL registra in `etl_run` (e che i test verificano)."""

    n_offerte: int
    n_componenti: int
    n_condizioni: int
    offerte_scartate: int
    percorsi_sconosciuti: tuple[str, ...]


def carica_offerte(
    sorgente: str | Path | IO[bytes],
    conn: sqlite3.Connection,
    *,
    snapshot_date: str,
) -> EsitoCaricamento:
    """Carica un XML di offerte in `conn`, in una sola transazione."""
    n_offerte = n_componenti = n_condizioni = scartate = 0
    percorsi: set[str] = set()

    with conn:  # commit se tutto va a buon fine, rollback all'errore
        carica_codifiche(conn)
        for offerta in iter_offerte(sorgente):
            percorsi |= offerta.percorsi_sconosciuti
            if not _chiave(offerta):
                scartate += 1
                continue
            _salva_offerta(conn, offerta, snapshot_date=snapshot_date)
            n_offerte += 1
            n_componenti += len(offerta.componenti)
            n_condizioni += len(offerta.condizioni)

    return EsitoCaricamento(
        n_offerte=n_offerte,
        n_componenti=n_componenti,
        n_condizioni=n_condizioni,
        offerte_scartate=scartate,
        percorsi_sconosciuti=tuple(sorted(percorsi)),
    )


def carica_codifiche(conn: sqlite3.Connection) -> int:
    """Allinea `codifica` alle decodifiche ufficiali. Ritorna le righe scritte."""
    righe = [
        (dominio, codice, descrizione)
        for dominio, voci in DECODIFICHE.items()
        for codice, descrizione in voci.items()
    ]
    conn.executemany(
        "INSERT INTO codifica (dominio, codice, descrizione) VALUES (?, ?, ?)"
        " ON CONFLICT (dominio, codice) DO UPDATE SET descrizione = excluded.descrizione",
        righe,
    )
    return len(righe)


def _chiave(offerta: Offerta) -> tuple[str, str] | None:
    piva = offerta.campi.get("piva")
    cod_offerta = offerta.campi.get("cod_offerta")
    if isinstance(piva, str) and isinstance(cod_offerta, str) and piva and cod_offerta:
        return piva, cod_offerta
    return None


def _salva_offerta(conn: sqlite3.Connection, offerta: Offerta, *, snapshot_date: str) -> None:
    chiave = _chiave(offerta)
    assert chiave is not None  # garantito da carica_offerte
    piva, cod_offerta = chiave

    _sostituisci_righe(conn, "componente", piva, cod_offerta)
    _sostituisci_righe(conn, "condizione", piva, cod_offerta)

    valori: dict[str, Any] = dict.fromkeys(COLONNE_OFFERTA)
    for colonna in COLONNE_OFFERTA:
        if colonna in ("extra_json", "snapshot_date"):
            continue
        valori[colonna] = offerta.campi.get(colonna)
    valori["extra_json"] = json_extra(offerta.extra)
    valori["snapshot_date"] = snapshot_date

    _scrivi(conn, "offerta", COLONNE_OFFERTA, [valori], chiave=("piva", "cod_offerta"))

    conn.executemany(
        _insert("componente", COLONNE_COMPONENTE),
        [_riga_componente(componente, piva, cod_offerta) for componente in offerta.componenti],
    )
    conn.executemany(
        _insert("condizione", COLONNE_CONDIZIONE),
        [
            _ordina(
                COLONNE_CONDIZIONE,
                {
                    **dict.fromkeys(COLONNE_CONDIZIONE),
                    **condizione.campi,
                    "piva": piva,
                    "cod_offerta": cod_offerta,
                },
            )
            for condizione in offerta.condizioni
        ],
    )


def _riga_componente(componente: Componente, piva: str, cod_offerta: str) -> tuple[Any, ...]:
    riga: dict[str, Any] = dict.fromkeys(COLONNE_COMPONENTE)
    riga.update(componente.campi)
    riga["prezzo"] = _real(riga.get("prezzo"))
    riga["extra_json"] = json_extra(componente.extra)
    riga["piva"] = piva
    riga["cod_offerta"] = cod_offerta
    return _ordina(COLONNE_COMPONENTE, riga)


def _ordina(colonne: tuple[str, ...], riga: dict[str, Any]) -> tuple[Any, ...]:
    """Trasforma una riga in tupla, nell'ordine delle colonne."""
    return tuple(riga.get(colonna) for colonna in colonne)


def _sostituisci_righe(conn: sqlite3.Connection, tabella: str, piva: str, cod_offerta: str) -> None:
    conn.execute(f"DELETE FROM {tabella} WHERE piva = ? AND cod_offerta = ?", (piva, cod_offerta))


def _scrivi(
    conn: sqlite3.Connection,
    tabella: str,
    colonne: tuple[str, ...],
    righe: list[dict[str, Any]],
    *,
    chiave: tuple[str, ...],
) -> None:
    aggiornamenti = ", ".join(
        f"{colonna} = excluded.{colonna}" for colonna in colonne if colonna not in chiave
    )
    conn.executemany(
        _insert(tabella, colonne)
        + f" ON CONFLICT ({', '.join(chiave)}) DO UPDATE SET {aggiornamenti}",
        [_ordina(colonne, riga) for riga in righe],
    )


def _insert(tabella: str, colonne: tuple[str, ...]) -> str:
    segnaposto = ", ".join("?" for _ in colonne)
    return f"INSERT INTO {tabella} ({', '.join(colonne)}) VALUES ({segnaposto})"


def _real(valore: Any) -> float | None:
    """Converte un `Decimal` del parser in REAL (o None)."""
    if valore is None:
        return None
    if isinstance(valore, Decimal):
        return float(valore)
    if isinstance(valore, (int, float)):
        return float(valore)
    return None
