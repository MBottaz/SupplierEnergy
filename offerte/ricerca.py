"""Funzione applicativa condivisa `cerca_offerte`.

Una sola implementazione per MCP e (in futuro) CLI: validazione, limiti,
ordinamento e forma del risultato stanno qui. Il contratto è in
`docs/contratto_cerca_offerte.md`; il server MCP traduce solo il protocollo.

Nessun calcolo di costo, nessun accesso alla rete, nessuna scrittura. Il testo
libero dei venditori viene restituito marcato come non fidato e non entra mai in
istruzioni o messaggi generati.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from offerte.errori import FiltroNonSupportato, InputNonValido

FILTRI_AMMESSI = frozenset(
    {
        "fornitore",
        "regione",
        "provincia",
        "comune",
        "tipo_cliente",
        "tipo_offerta",
        "indicizzata",
        "testo",
        "limit",
    }
)

LIMIT_DEFAULT = 20
LIMIT_MASSIMO = 50
MAX_LUNGHEZZA_FILTRO = 200

_FUSO = ZoneInfo("Europe/Rome")
_CODICE_DUE_CIFRE = re.compile(r"^\d{2}$")
_ZONE: tuple[tuple[str, str], ...] = (
    ("regione", "REGIONE"),
    ("provincia", "PROVINCIA"),
    ("comune", "COMUNE"),
)

#: Colonne selezionate, nell'ordine in cui vengono lette.
_SQL_COLONNE = (
    "o.piva, o.cod_offerta, o.nome, o.descrizione, o.tipo_cliente, o.tipo_offerta,"
    " o.idx_prezzo_energia, o.data_inizio, o.data_fine, o.extra_json"
)


@dataclass(frozen=True)
class _Filtri:
    """Filtri già validati e normalizzati."""

    fornitore: str | None
    regione: str | None
    provincia: str | None
    comune: str | None
    tipo_cliente: str | None
    tipo_offerta: str | None
    indicizzata: bool | None
    testo: str | None
    limit: int


def oggi() -> str:
    """Data odierna in `Europe/Rome` (stessa convenzione dell'ETL)."""
    return datetime.now(_FUSO).date().isoformat()


def _valida(filtri: Mapping[str, object]) -> _Filtri:
    ignote = sorted(set(filtri) - FILTRI_AMMESSI)
    if ignote:
        raise FiltroNonSupportato(f"filtro non supportato: {', '.join(ignote)}")

    def stringa(nome: str) -> str | None:
        valore = filtri.get(nome)
        if valore is None:
            return None
        if not isinstance(valore, str):
            raise InputNonValido(f"{nome} deve essere una stringa")
        valore = valore.strip()
        if not valore:
            raise InputNonValido(f"{nome} non può essere una stringa vuota")
        if len(valore) > MAX_LUNGHEZZA_FILTRO:
            raise InputNonValido(
                f"{nome} supera la lunghezza massima di {MAX_LUNGHEZZA_FILTRO} caratteri"
            )
        return valore

    def codice(nome: str) -> str | None:
        valore = stringa(nome)
        if valore is not None and not _CODICE_DUE_CIFRE.match(valore):
            raise InputNonValido(f"{nome} deve essere un codice di due cifre")
        return valore

    indicizzata = filtri.get("indicizzata")
    if indicizzata is not None and not isinstance(indicizzata, bool):
        raise InputNonValido("indicizzata deve essere true o false")

    limite = filtri.get("limit")
    if limite is None:
        limite = LIMIT_DEFAULT
    elif isinstance(limite, bool) or not isinstance(limite, int):
        raise InputNonValido("limit deve essere un intero")
    elif not 1 <= limite <= LIMIT_MASSIMO:
        raise InputNonValido(f"limit deve essere un intero fra 1 e {LIMIT_MASSIMO}")

    return _Filtri(
        fornitore=stringa("fornitore"),
        regione=stringa("regione"),
        provincia=stringa("provincia"),
        comune=stringa("comune"),
        tipo_cliente=codice("tipo_cliente"),
        tipo_offerta=codice("tipo_offerta"),
        indicizzata=indicizzata,
        testo=stringa("testo"),
        limit=limite,
    )


def _casefold(valore: Any) -> Any:
    """`casefold` Unicode deterministico, esposto a SQLite (ASCII-only `lower`)."""
    if valore is None:
        return None
    return str(valore).casefold()


def _sfuggi_like(testo: str) -> str:
    return testo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _clausole(filtri: _Filtri) -> tuple[list[str], list[object]]:
    clausole = ["(o.data_fine IS NULL OR o.data_fine >= ?)"]
    parametri: list[object] = [oggi()]

    if filtri.fornitore is not None:
        clausole.append("o.piva = ?")
        parametri.append(filtri.fornitore)
    if filtri.tipo_cliente is not None:
        clausole.append("o.tipo_cliente = ?")
        parametri.append(filtri.tipo_cliente)
    if filtri.tipo_offerta is not None:
        clausole.append("o.tipo_offerta = ?")
        parametri.append(filtri.tipo_offerta)
    if filtri.indicizzata is True:
        clausole.append("o.idx_prezzo_energia IS NOT NULL")
    elif filtri.indicizzata is False:
        clausole.append("o.idx_prezzo_energia IS NULL")

    if filtri.testo is not None:
        modello = f"%{_sfuggi_like(filtri.testo.casefold())}%"
        clausole.append(
            "(casefold(o.nome) LIKE ? ESCAPE '\\' OR casefold(o.descrizione) LIKE ? ESCAPE '\\')"
        )
        parametri.extend([modello, modello])

    for nome, percorso in _ZONE:
        valore = getattr(filtri, nome)
        if valore is None:
            continue
        clausole.append(
            "EXISTS (SELECT 1 FROM json_each(o.extra_json, ?) AS g"
            " WHERE casefold(g.value) = casefold(?))"
        )
        parametri.extend([f'$."offerta/ZoneOfferta/{percorso}"', valore])

    return clausole, parametri


def _carica_extra(testo: str | None) -> dict[str, Any]:
    if not testo:
        return {}
    try:
        dati = json.loads(testo)
    except (TypeError, ValueError):
        return {}
    return dati if isinstance(dati, dict) else {}


def _valori_zona(extra: Mapping[str, Any], percorso: str) -> list[str]:
    valore = extra.get(percorso)
    if isinstance(valore, str):
        return [valore]
    if isinstance(valore, list):
        return [elemento for elemento in valore if isinstance(elemento, str)]
    return []


def _riga_a_risultato(riga: sqlite3.Row) -> dict[str, Any]:
    extra = _carica_extra(riga["extra_json"])
    return {
        "piva": riga["piva"],
        "cod_offerta": riga["cod_offerta"],
        "nome_offerta": riga["nome"],
        "descrizione_offerta": riga["descrizione"],
        "testo_venditore_non_fidato": True,
        "tipo_cliente": riga["tipo_cliente"],
        "tipo_offerta": riga["tipo_offerta"],
        "indicizzata": riga["idx_prezzo_energia"] is not None,
        "data_inizio": riga["data_inizio"],
        "data_fine": riga["data_fine"],
        "zone": {
            nome: _valori_zona(extra, f"offerta/ZoneOfferta/{percorso}") for nome, percorso in _ZONE
        },
    }


def _avvertenze(filtri: _Filtri) -> list[str]:
    avvertenze: list[str] = []
    if filtri.fornitore is not None:
        avvertenze.append(
            "fornitore è la P.IVA: il nome commerciale del venditore non è nel modello dati"
        )
    if any(getattr(filtri, nome) is not None for nome, _ in _ZONE):
        avvertenze.append(
            "le zone sono quelle dichiarate dall'offerta; le offerte senza zone non corrispondono"
        )
    if filtri.testo is not None:
        avvertenze.append("la ricerca testuale copre solo nome e descrizione dell'offerta")
    return avvertenze


def _dati_aggiornati_al(conn: sqlite3.Connection) -> str | None:
    riga = conn.execute("SELECT max(snapshot_date) AS massimo FROM offerta").fetchone()
    if riga is None:
        return None
    valore = riga["massimo"]
    return valore if isinstance(valore, str) else None


def cerca_offerte(conn: sqlite3.Connection, filtri: Mapping[str, object]) -> dict[str, Any]:
    """Cerca le offerte valide che rispettano `filtri`.

    `conn` è una connessione aperta da `offerte.db.apri_db` (sola lettura).
    Solleva `InputNonValido` o `FiltroNonSupportato` per input fuori contratto.
    """
    filtri_validati = _valida(filtri)

    # `lower` di SQLite è ASCII-only: serve un casefold Unicode per i nomi con
    # accenti (per esempio la provincia di Forlì).
    conn.create_function("casefold", 1, _casefold, deterministic=True)

    clausole, parametri = _clausole(filtri_validati)
    sql = (
        f"SELECT {_SQL_COLONNE} FROM offerta AS o"
        f" WHERE {' AND '.join(clausole)}"
        " ORDER BY o.piva, o.cod_offerta"
        " LIMIT ?"
    )
    righe: Sequence[sqlite3.Row] = conn.execute(
        sql, [*parametri, filtri_validati.limit + 1]
    ).fetchall()

    troncato = len(righe) > filtri_validati.limit
    risultati = [_riga_a_risultato(riga) for riga in righe[: filtri_validati.limit]]

    return {
        "risultati": risultati,
        "numero_risultati": len(risultati),
        "limit": filtri_validati.limit,
        "troncato": troncato,
        "dati_aggiornati_al": _dati_aggiornati_al(conn),
        "avvertenze": _avvertenze(filtri_validati),
    }
