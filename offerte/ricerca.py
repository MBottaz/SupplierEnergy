"""Funzione applicativa condivisa `cerca_offerte`.

Una sola implementazione per il server MCP e per eventuali strumenti locali di
debug: validazione, limiti, ordinamento e forma del risultato stanno qui. Il
contratto è in
`docs/cerca_offerte_contract.md`; il server MCP traduce solo il protocollo.

Nessun calcolo di costo, nessun accesso alla rete, nessuna scrittura. Il testo
libero dei venditori viene restituito marcato come non fidato e non entra mai in
istruzioni o messaggi generati.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from offerte.errori import FiltroNonSupportato, InputNonValido
from offerte.zone import (
    codice_provincia,
    codice_regione,
    nome_provincia,
    nome_regione,
    regione_di_provincia,
)

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
# Etichette dell'interfaccia pubblica, derivate dalle decodifiche ufficiali
# dell'ETL (`etl/codifiche.py`). Le query continuano a usare i codici del DB.
OPZIONI_TIPO_CLIENTE: tuple[str, ...] = (
    "domestico",
    "altri usi",
    "condominio uso domestico (gas)",
)
_CODICI_TIPO_CLIENTE = {
    "domestico": "01",
    "altri usi": "02",
    "condominio uso domestico (gas)": "03",
}

OPZIONI_TIPO_OFFERTA: tuple[str, ...] = ("fisso", "variabile", "flat", "mista")
_CODICI_TIPO_OFFERTA = {
    "fisso": "01",
    "variabile": "02",
    "flat": "03",
    "mista": "04",
}

_ZONE: tuple[tuple[str, str], ...] = (
    ("regione", "REGIONE"),
    ("provincia", "PROVINCIA"),
    ("comune", "COMUNE"),
)

#: Percorsi delle zone in `extra_json`, nell'ordine di `_ZONE`.
_PERCORSI_ZONA_SQL: tuple[str, ...] = tuple(
    f'$."offerta/ZoneOfferta/{percorso}"' for _, percorso in _ZONE
)

#: Offerta senza alcuna zona dichiarata: vale su tutto il territorio nazionale.
_CLAUSOLA_NAZIONALE = "(" + " AND ".join("json_type(o.extra_json, ?) IS NULL" for _ in _ZONE) + ")"

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


def _codice_comune(valore: str) -> str:
    """Il filtro `comune` è un codice ISTAT a 6 cifre: i nomi non sono tradotti."""
    if len(valore) != 6 or not valore.isdigit():
        raise InputNonValido(
            "comune deve essere il codice ISTAT a 6 cifre "
            "(per esempio 015146 per Milano); la ricerca per nome del comune "
            "non è supportata"
        )
    if regione_di_provincia(valore[:3]) is None:
        raise InputNonValido(
            "comune deve essere un codice ISTAT valido: le prime 3 cifre sono la provincia"
        )
    return valore


def _valida_gerarchia(regione: str | None, provincia: str | None, comune: str | None) -> None:
    """I filtri geografici indicati insieme devono essere annidati."""
    if provincia is not None and regione is not None and regione_di_provincia(provincia) != regione:
        raise InputNonValido("la provincia indicata non appartiene alla regione indicata")
    if comune is not None:
        provincia_del_comune = comune[:3]
        if provincia is not None and provincia_del_comune != provincia:
            raise InputNonValido("il comune indicato non appartiene alla provincia indicata")
        if regione is not None and regione_di_provincia(provincia_del_comune) != regione:
            raise InputNonValido("il comune indicato non appartiene alla regione indicata")


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

    def opzione(nome: str, opzioni: tuple[str, ...], codici: Mapping[str, str]) -> str | None:
        valore = stringa(nome)
        if valore is None:
            return None
        chiave = valore.casefold()
        if chiave not in codici:
            raise InputNonValido(f"{nome} deve essere uno di: {', '.join(opzioni)}")
        return codici[chiave]

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

    regione_grezza = stringa("regione")
    provincia_grezza = stringa("provincia")
    comune_grezzo = stringa("comune")

    regione = codice_regione(regione_grezza) if regione_grezza is not None else None
    provincia = codice_provincia(provincia_grezza) if provincia_grezza is not None else None
    comune = _codice_comune(comune_grezzo) if comune_grezzo is not None else None
    _valida_gerarchia(regione, provincia, comune)

    return _Filtri(
        fornitore=stringa("fornitore"),
        regione=regione,
        provincia=provincia,
        comune=comune,
        tipo_cliente=opzione("tipo_cliente", OPZIONI_TIPO_CLIENTE, _CODICI_TIPO_CLIENTE),
        tipo_offerta=opzione("tipo_offerta", OPZIONI_TIPO_OFFERTA, _CODICI_TIPO_OFFERTA),
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


def _bacini_geografici(filtri: _Filtri) -> tuple[list[str], list[str], list[str]]:
    """Livelli da corrispondere: il filtro più specifico e i livelli più ampi.

    Una provincia è coperta da un'offerta che la dichiara o che dichiara la sua
    regione; un comune anche da un'offerta che dichiara la sua provincia.
    """
    if filtri.comune is not None:
        provincia = filtri.comune[:3]
        regione = regione_di_provincia(provincia)
        assert regione is not None  # garantito da `_codice_comune`
        return [regione], [provincia], [filtri.comune]
    if filtri.provincia is not None:
        regione = regione_di_provincia(filtri.provincia)
        assert regione is not None  # garantito da `_valida`
        return [regione], [filtri.provincia], []
    if filtri.regione is not None:
        return [filtri.regione], [], []
    return [], [], []


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

    regioni, province, comuni = _bacini_geografici(filtri)
    if regioni or province or comuni:
        sottoclausole = [_CLAUSOLA_NAZIONALE]
        parametri.extend(_PERCORSI_ZONA_SQL)
        for percorso, valori in (
            ("REGIONE", regioni),
            ("PROVINCIA", province),
            ("COMUNE", comuni),
        ):
            if not valori:
                continue
            segnaposti = ", ".join("casefold(?)" for _ in valori)
            sottoclausole.append(
                "EXISTS (SELECT 1 FROM json_each(o.extra_json, ?) AS g"
                f" WHERE casefold(g.value) IN ({segnaposti}))"
            )
            parametri.append(f'$."offerta/ZoneOfferta/{percorso}"')
            parametri.extend(valori)
        clausole.append("(" + " OR ".join(sottoclausole) + ")")

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


def _decodifica(valori: list[str], nome_ufficiale: Any) -> list[str]:
    """Codice ISTAT -> denominazione ufficiale, con il codice grezzo di ripiego."""
    return [nome_ufficiale(valore) or valore for valore in valori]


def _zone_risultato(extra: Mapping[str, Any]) -> dict[str, list[str]]:
    """Zone decodificate: regioni e province per nome, comuni come codici."""
    return {
        "regione": _decodifica(_valori_zona(extra, "offerta/ZoneOfferta/REGIONE"), nome_regione),
        "provincia": _decodifica(
            _valori_zona(extra, "offerta/ZoneOfferta/PROVINCIA"), nome_provincia
        ),
        "comune": _valori_zona(extra, "offerta/ZoneOfferta/COMUNE"),
    }


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
        "zone": _zone_risultato(extra),
    }


def _avvertenze(filtri: _Filtri) -> list[str]:
    avvertenze: list[str] = []
    if filtri.fornitore is not None:
        avvertenze.append(
            "fornitore è la P.IVA: il nome commerciale del venditore non è nel modello dati"
        )
    if any(getattr(filtri, nome) is not None for nome, _ in _ZONE):
        avvertenze.append(
            "le offerte senza zone dichiarate valgono su tutto il territorio "
            "nazionale e sono sempre incluse; un filtro più specifico include "
            "anche le offerte dichiarate a livello più ampio"
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
