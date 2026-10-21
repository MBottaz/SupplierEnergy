"""Parametri regolati dal CSV `PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv`.

Regole (docs/architettura.md §4 e §7):

- la data nel nome del file è la data di riferimento: si salva con i valori;
- le righe si caricano così come sono, senza interpretare i nomi;
- le unità di misura non sono nel file: i metadati (`unita`, `categoria_cliente`,
  BTA) si ricaveranno dalla documentazione ufficiale in fase B, con una tabella
  dedicata: non si derivano dai nomi (questione aperta);
- alcuni parametri sono obbligatori: se mancano, l'ETL blocca lo swap.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

#: `PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv`
NOME_FILE = re.compile(r"^PO_Parametri_Mercato_Libero_E_(\d{8})\.csv$")

#: Controllati dall'ETL: se mancano, lo swap del DB è bloccato (§7).
OBBLIGATORI = ("pcv_a", "pcv_c", "iva_a", "iva_c", "lambda")

MAX_TESTO = 4000


@dataclass(frozen=True)
class RigaParametro:
    nome: str
    valore: str | None
    descrizione: str | None
    riferimento: str


@dataclass(frozen=True)
class EsitoParametri:
    n_parametri: int
    riferimento: str
    mancanti: tuple[str, ...]


def riferimento_da_nome(percorso: str | Path) -> str:
    """Data di riferimento (`AAAA-MM-GG`) dal nome del file dei parametri."""
    nome = Path(percorso).name
    trovato = NOME_FILE.match(nome)
    if trovato is None:
        raise ValueError(
            "nome file senza riferimento: atteso "
            f"PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv, ricevuto {nome!r}"
        )
    grezzo = trovato.group(1)
    return f"{grezzo[0:4]}-{grezzo[4:6]}-{grezzo[6:8]}"


def leggi_parametri(percorso: str | Path) -> list[RigaParametro]:
    """Legge il CSV e restituisce le righe con il loro riferimento."""
    riferimento = riferimento_da_nome(percorso)
    with Path(percorso).open("r", encoding="utf-8-sig", newline="") as flusso:
        lettore = csv.DictReader(flusso)
        if lettore.fieldnames is None or "nome_parametro" not in lettore.fieldnames:
            raise ValueError("CSV dei parametri senza colonna nome_parametro")
        righe = [
            RigaParametro(
                nome=nome,
                valore=_testo(riga.get("valore")),
                descrizione=_testo(riga.get("descrizione")),
                riferimento=riferimento,
            )
            for riga in lettore
            if (nome := _testo(riga.get("nome_parametro"))) is not None
        ]
    return righe


def parametri_obbligatori_mancanti(nomi: Iterable[str]) -> tuple[str, ...]:
    """Quali parametri obbligatori non ci sono, in ordine alfabetico."""
    presenti = set(nomi)
    return tuple(sorted(nome for nome in OBBLIGATORI if nome not in presenti))


def carica_parametri(conn: sqlite3.Connection, percorso: str | Path) -> EsitoParametri:
    """Sostituisce lo snapshot dei parametri con quello del file indicato."""
    righe = leggi_parametri(percorso)
    riferimento = riferimento_da_nome(percorso)
    with conn:
        conn.execute("DELETE FROM parametro WHERE riferimento = ?", (riferimento,))
        conn.executemany(
            "INSERT INTO parametro (nome, valore, descrizione, riferimento)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (nome, riferimento) DO UPDATE SET"
            " valore = excluded.valore, descrizione = excluded.descrizione",
            [(riga.nome, riga.valore, riga.descrizione, riga.riferimento) for riga in righe],
        )
    return EsitoParametri(
        n_parametri=len(righe),
        riferimento=riferimento,
        mancanti=parametri_obbligatori_mancanti(riga.nome for riga in righe),
    )


def _testo(valore: str | None) -> str | None:
    if valore is None:
        return None
    ripulito = " ".join(valore.split())
    if not ripulito:
        return None
    return ripulito[:MAX_TESTO]


def _voci(conn: sqlite3.Connection, riferimento: str) -> Iterator[tuple[str, str | None]]:
    for riga in conn.execute(
        "SELECT nome, valore FROM parametro WHERE riferimento = ? ORDER BY nome", (riferimento,)
    ):
        yield riga["nome"], riga["valore"]
