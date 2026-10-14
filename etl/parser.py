"""Parser tollerante dell'XML delle offerte (docs/architettura.md §5).

Regole:

- il parser conosce solo i percorsi elencati in `_CAMPI`; tutto il resto non fa
  fallire il caricamento: finisce in `extra` (JSON dell'offerta o della
  componente) e il percorso entra in `percorsi_sconosciuti`;
- gli elementi noti ma senza colonna dedicata (tipo `EXTRA`) vanno in `extra`
  senza essere contati come sconosciuti;
- `campi` contiene solo le chiavi valorizzate: chi legge usa `.get(colonna)`;
- lettura in streaming: ogni `<offerta>` viene elaborata e liberata subito;
- XML hardened: DTD ed entità (interne ed esterne) sono rifiutati da defusedxml.

I prezzi sono letti con `Decimal`; è il caricamento a convertirli in REAL.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import IO, Any
from unicodedata import category
from xml.etree.ElementTree import Element
from zoneinfo import ZoneInfo

from defusedxml import ElementTree as DefusedET

FUSO = ZoneInfo("Europe/Rome")

#: Oltre questa lunghezza il testo libero dei venditori viene troncato.
MAX_TESTO = 4000

TESTO = "testo"
DATA = "data"
PREZZO = "prezzo"
EXTRA = "extra"

#: percorso XML (relativo a `<offerta>`) → (colonna, tipo di valore).
#: Con tipo `EXTRA` la colonna è `None`: il valore va in `extra_json`.
_CAMPI: dict[str, tuple[str | None, str]] = {
    # IdentificativiOfferta
    "offerta/IdentificativiOfferta/PIVA_UTENTE": ("piva", TESTO),
    "offerta/IdentificativiOfferta/COD_OFFERTA": ("cod_offerta", TESTO),
    # DettaglioOfferta
    "offerta/DettaglioOfferta/TIPO_MERCATO": ("tipo_mercato", TESTO),
    "offerta/DettaglioOfferta/OFFERTA_SINGOLA": ("offerta_singola", TESTO),
    "offerta/DettaglioOfferta/TIPO_CLIENTE": ("tipo_cliente", TESTO),
    "offerta/DettaglioOfferta/TIPO_OFFERTA": ("tipo_offerta", TESTO),
    "offerta/DettaglioOfferta/TIPOLOGIA_ATT_CONTR": ("tipologia_att_contr", TESTO),
    "offerta/DettaglioOfferta/NOME_OFFERTA": ("nome", TESTO),
    "offerta/DettaglioOfferta/DESCRIZIONE": ("descrizione", TESTO),
    "offerta/DettaglioOfferta/DURATA": ("durata", TESTO),
    "offerta/DettaglioOfferta/GARANZIE": ("garanzie", TESTO),
    "offerta/DettaglioOfferta/ModalitaAttivazione/MODALITA": (None, EXTRA),
    "offerta/DettaglioOfferta/Contatti/TELEFONO": ("telefono", TESTO),
    "offerta/DettaglioOfferta/Contatti/URL_SITO_VENDITORE": ("url_sito", TESTO),
    "offerta/DettaglioOfferta/Contatti/URL_OFFERTA": ("url_offerta", TESTO),
    # RiferimentiPrezzoEnergia
    "offerta/RiferimentiPrezzoEnergia/IDX_PREZZO_ENERGIA": ("idx_prezzo_energia", TESTO),
    # ValiditaOfferta
    "offerta/ValiditaOfferta/DATA_INIZIO": ("data_inizio", DATA),
    "offerta/ValiditaOfferta/DATA_FINE": ("data_fine", DATA),
    # MetodoPagamento
    "offerta/MetodoPagamento/MODALITA_PAGAMENTO": ("modalita_pagamento", TESTO),
    # Dispacciamento
    "offerta/Dispacciamento/TIPO_DISPACCIAMENTO": ("tipo_dispacciamento", TESTO),
    "offerta/Dispacciamento/NOME": (None, EXTRA),
    # ComponenteImpresa
    "offerta/ComponenteImpresa/NOME": ("nome", TESTO),
    "offerta/ComponenteImpresa/DESCRIZIONE": ("descrizione", TESTO),
    "offerta/ComponenteImpresa/TIPOLOGIA": ("tipologia", TESTO),
    "offerta/ComponenteImpresa/MACROAREA": ("macroarea", TESTO),
    "offerta/ComponenteImpresa/IntervalloPrezzi/FASCIA_COMPONENTE": ("fascia", TESTO),
    "offerta/ComponenteImpresa/IntervalloPrezzi/PREZZO": ("prezzo", PREZZO),
    "offerta/ComponenteImpresa/IntervalloPrezzi/UNITA_MISURA": ("unita_misura", TESTO),
    # CondizioniContrattuali
    "offerta/CondizioniContrattuali/TIPOLOGIA_CONDIZIONE": ("tipologia", TESTO),
    "offerta/CondizioniContrattuali/DESCRIZIONE": ("descrizione", TESTO),
    "offerta/CondizioniContrattuali/LIMITANTE": ("limitante", TESTO),
}

_TAG_COMPONENTE = "ComponenteImpresa"
_BASE_COMPONENTE = f"offerta/{_TAG_COMPONENTE}"
_INTERVALLO = "IntervalloPrezzi"
_CONDIZIONI = "CondizioniContrattuali"

_NON_CONVERTIBILE = object()


@dataclass
class Componente:
    """Una componente di prezzo (`componente`), con il suo JSON di extra.

    Una riga per `IntervalloPrezzi`: i campi comuni (nome, macroarea…) sono
    ripetuti su ogni riga, come richiede il formato "long".
    """

    campi: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Condizione:
    """Una condizione contrattuale (`condizione`)."""

    campi: dict[str, Any] = field(default_factory=dict)


@dataclass
class Offerta:
    """Un'offerta normalizzata, pronta per il caricamento."""

    campi: dict[str, Any] = field(default_factory=dict)
    componenti: list[Componente] = field(default_factory=list)
    condizioni: list[Condizione] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)
    percorsi_sconosciuti: set[str] = field(default_factory=set)


@dataclass
class _Record:
    """Campi e extra di un singolo record (offerta, componente, condizione)."""

    campi: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def iter_offerte(sorgente: str | Path | IO[bytes]) -> Iterator[Offerta]:
    """Elenca le offerte di un XML, una alla volta, senza tenerle in memoria."""
    if isinstance(sorgente, (str, Path)):
        with Path(sorgente).open("rb") as flusso:
            yield from _iter_flusso(flusso)
    else:
        yield from _iter_flusso(sorgente)


def _iter_flusso(flusso: IO[bytes]) -> Iterator[Offerta]:
    eventi = DefusedET.iterparse(flusso, events=("start", "end"))
    try:
        for evento, elemento in eventi:
            if evento != "end" or _tag(elemento) != "offerta":
                continue
            yield parse_offerta(elemento)
            elemento.clear()
    finally:
        chiudi = getattr(eventi, "close", None)
        if callable(chiudi):
            chiudi()


def parse_offerta(elemento: Element) -> Offerta:
    """Costruisce un'`Offerta` dall'elemento `<offerta>` già letto."""
    radice = _Record()
    componenti: list[Componente] = []
    condizioni: list[_Record] = []
    sconosciuti: set[str] = set()

    _attributi(elemento, "offerta", radice, sconosciuti)
    for figlio in elemento:
        tag = _tag(figlio)
        percorso = f"offerta/{tag}"
        if tag == _TAG_COMPONENTE:
            componenti.extend(_componenti(figlio, sconosciuti))
        elif tag == _CONDIZIONI:
            condizione = _Record()
            _sottoalbero(figlio, percorso, condizione, sconosciuti)
            condizioni.append(condizione)
        else:
            _sottoalbero(figlio, percorso, radice, sconosciuti)

    # `condizione` non ha una colonna extra_json: quanto non previsto dentro le
    # condizioni confluisce nell'extra dell'offerta.
    extra = dict(radice.extra)
    for condizione in condizioni:
        for chiave, valore in condizione.extra.items():
            _accoda(extra, chiave, valore)

    return Offerta(
        campi=radice.campi,
        componenti=componenti,
        condizioni=[Condizione(campi=record.campi) for record in condizioni],
        extra=extra,
        percorsi_sconosciuti=sconosciuti,
    )


def _componenti(elemento: Element, sconosciuti: set[str]) -> list[Componente]:
    """Una riga per `IntervalloPrezzi`; una sola riga se non ce ne sono."""
    comune = _Record()
    intervalli: list[_Record] = []
    _attributi(elemento, _BASE_COMPONENTE, comune, sconosciuti)
    for figlio in elemento:
        percorso = f"{_BASE_COMPONENTE}/{_tag(figlio)}"
        if _tag(figlio) == _INTERVALLO:
            intervallo = _Record()
            _sottoalbero(figlio, percorso, intervallo, sconosciuti)
            intervalli.append(intervallo)
        else:
            _sottoalbero(figlio, percorso, comune, sconosciuti)

    righe = intervalli or [_Record()]
    return [
        Componente(
            campi={**comune.campi, **riga.campi},
            extra={**comune.extra, **riga.extra},
        )
        for riga in righe
    ]


def _sottoalbero(nodo: Element, percorso: str, record: _Record, sconosciuti: set[str]) -> None:
    """Riempe `record` con il nodo e tutto il suo sottoalbero."""
    _attributi(nodo, percorso, record, sconosciuti)
    if len(nodo):
        for figlio in nodo:
            _sottoalbero(figlio, f"{percorso}/{_tag(figlio)}", record, sconosciuti)
    else:
        _foglia(nodo, percorso, record, sconosciuti)


def _foglia(nodo: Element, percorso: str, record: _Record, sconosciuti: set[str]) -> None:
    testo = _testo(nodo)
    campo = _CAMPI.get(percorso)
    if campo is None:
        if testo is not None:
            _accoda(record.extra, percorso, testo)
            sconosciuti.add(percorso)
        return

    colonna, tipo = campo
    if tipo == EXTRA:
        if testo is not None:
            record.extra[percorso] = testo
        return

    valore = _converti(testo, tipo)
    if valore is _NON_CONVERTIBILE:
        sconosciuti.add(percorso)
        if testo is not None:
            _accoda(record.extra, percorso, testo)
    elif colonna is not None:
        record.campi[colonna] = valore


def _attributi(nodo: Element, percorso: str, record: _Record, sconosciuti: set[str]) -> None:
    """Gli attributi non fanno parte del tracciato: extra + percorso sconosciuto."""
    for nome, valore in nodo.attrib.items():
        chiave = f"{percorso}@{nome}"
        record.extra[chiave] = _pulisci(valore)
        sconosciuti.add(chiave)


def _accoda(dizionario: dict[str, Any], chiave: str, valore: Any) -> None:
    """Aggiunge un valore; se la chiave esiste già, raccoglie in lista."""
    if chiave not in dizionario:
        dizionario[chiave] = valore
    elif isinstance(dizionario[chiave], list):
        dizionario[chiave].append(valore)
    else:
        dizionario[chiave] = [dizionario[chiave], valore]


def _converti(testo: str | None, tipo: str) -> Any:
    if testo is None:
        return None
    if tipo == PREZZO:
        try:
            return Decimal(testo)
        except InvalidOperation:
            return _NON_CONVERTIBILE
    if tipo == DATA:
        try:
            momento = datetime.strptime(testo, "%d/%m/%Y_%H:%M:%S")
        except ValueError:
            return _NON_CONVERTIBILE
        return momento.replace(tzinfo=FUSO).isoformat()
    return testo


def _tag(elemento: Element) -> str:
    tag = elemento.tag
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _testo(elemento: Element) -> str | None:
    return _pulisci(elemento.text)


def _pulisci(testo: str | None) -> str | None:
    if testo is None:
        return None
    # I caratteri di controllo diventano spazi: rimuoverli e basta
    # attaccherebbe parole che erano separate da un tab o da un a capo.
    senza_controlli = "".join(" " if category(c) == "Cc" else c for c in testo)
    normalizzato = " ".join(senza_controlli.split())
    if not normalizzato:
        return None
    return normalizzato[:MAX_TESTO]


def json_extra(extra: dict[str, Any]) -> str | None:
    """Serializza l'`extra` per `extra_json`. `None` se non c'è nulla."""
    if not extra:
        return None
    return json.dumps(extra, ensure_ascii=False, sort_keys=True, default=str)
