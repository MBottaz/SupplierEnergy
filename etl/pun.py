"""PUN mensile dal file "Prezzi storici" del Portale Offerte (architettura §4).

Fonte: pagina Open Data di `ilportaleofferte.it`, voce "Prezzi storici - indici a
pubblica diffusione". Il documento è un CSV aggiornato a mese concluso; non ha un
URL open data datato come l'XML, quindi l'indirizzo è quello del documento CMS e
va verificato se il Portale lo sostituisce.

Formato: CSV con separatore `;`, codifica cp1252, colonna `AnnoMese` (`AAAAMM`) e
colonna `PUN (€/kWh)`. Le altre colonne (PSV, CMEM, …) riguardano il gas e si
ignorano. L'unità di misura è scritta nell'intestazione della colonna: il valore
si converte in €/MWh moltiplicando per 1000, senza indovinare formati diversi.

La serie salvata è `PUN_MENSILE`: un valore per mese, senza dire come è pesato.
Che sia la media aritmetica dei PUN giornalieri o il PUN Index GME ponderato per
le quantità è una questione aperta (docs/questioni_aperte.md): si salva il dato
così come pubblicato e la scelta dell'indice per una singola offerta spetta al
calcolo (fase 4), non a questo modulo.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

#: Documento "Prezzi storici (csv)" della pagina Open Data. URL non datato:
#: se il Portale lo sostituisce, va aggiornato qui (questione aperta).
URL_PUN = (
    "https://www.ilportaleofferte.it/portaleOfferte/resources/cms/documents/"
    "0c916785cbc1c33483b3dee7fc53c7a5.csv"
)

#: Nome della serie salvata in `pun`. Un solo valore per mese.
SERIE = "PUN_MENSILE"

#: Tetto ai frammenti di file citati nei messaggi di errore.
MAX_ERRORE = 120

#: Fattori di conversione da unità di misura dell'intestazione a €/MWh.
FATTORI_EUR_MWH = {
    "€/kwh": Decimal(1000),
    "eur/kwh": Decimal(1000),
    "€/mwh": Decimal(1),
    "eur/mwh": Decimal(1),
}

_UNITA = re.compile(r"\(([^)]+)\)")
_PERIODO = re.compile(r"^(\d{4})(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class RigaPun:
    """Una riga di `pun`: primo giorno del mese, valore in €/MWh."""

    data: str
    valore_eur_mwh: Decimal
    serie: str = SERIE


@dataclass(frozen=True)
class LetturaPun:
    """Risultato della lettura: righe utilizzabili e righe con PUN assente."""

    righe: tuple[RigaPun, ...]
    n_scartate: int


@dataclass(frozen=True)
class EsitoPun:
    """Esito del caricamento: quante righe, quali periodi, cosa è stato scartato."""

    n_righe: int
    n_scartate: int
    serie: str
    prima: str | None
    ultima: str | None


def nome_file_raw(giorno: str) -> str:
    """Nome descrittivo del raw scaricato, per la cartella datata."""
    return f"PO_Prezzi_Storici_{giorno.replace('-', '')}.csv"


def serie_mensile(serie: str) -> bool:
    """True se la serie ha un valore per mese (staleness misurata a mese)."""
    return "MENSILE" in serie.upper()


def leggi_pun(percorso: str | Path) -> LetturaPun:
    """Legge il CSV dei prezzi storici e restituisce le righe del PUN.

    Un valore PUN assente è una riga scartata; un periodo malformato o duplicato
    è un errore: significa che il file non è quello atteso.
    """
    with Path(percorso).open("r", encoding="cp1252", newline="") as flusso:
        lettore = csv.reader(flusso, delimiter=";")
        try:
            intestazione = next(lettore)
        except StopIteration:
            raise ValueError("file dei prezzi storici vuoto") from None

        colonna_periodo = _colonna(intestazione, "annomese", esatta=True)
        colonna_pun = _colonna(intestazione, "pun", esatta=False)
        fattore = _fattore(intestazione[colonna_pun])

        righe: dict[str, RigaPun] = {}
        scartate = 0
        for numero, campi in enumerate(lettore, start=2):
            if not any(campo.strip() for campo in campi):
                continue
            data = _data(_campo(campi, colonna_periodo, numero))
            valore = _decimale(_campo(campi, colonna_pun, numero))
            if valore is None:
                scartate += 1
                continue
            if data in righe:
                raise ValueError(f"periodo duplicato alla riga {numero}: {data}")
            righe[data] = RigaPun(data=data, valore_eur_mwh=valore * fattore)

    return LetturaPun(righe=tuple(righe[data] for data in sorted(righe)), n_scartate=scartate)


def carica_pun(conn: sqlite3.Connection, percorso: str | Path) -> EsitoPun:
    """Carica (o aggiorna) il PUN mensile nel DB. Idempotente.

    La chiave è `(data, serie)`: ricaricare lo stesso file non duplica righe e
    un valore rivisto dal Portale sostituisce quello vecchio.
    """
    lettura = leggi_pun(percorso)
    with conn:
        conn.executemany(
            "INSERT INTO pun (data, valore_eur_mwh, serie) VALUES (?, ?, ?)"
            " ON CONFLICT (data, serie) DO UPDATE SET valore_eur_mwh = excluded.valore_eur_mwh",
            [(riga.data, float(riga.valore_eur_mwh), riga.serie) for riga in lettura.righe],
        )
    return EsitoPun(
        n_righe=len(lettura.righe),
        n_scartate=lettura.n_scartate,
        serie=SERIE,
        prima=lettura.righe[0].data if lettura.righe else None,
        ultima=lettura.righe[-1].data if lettura.righe else None,
    )


def righe_del_db(conn: sqlite3.Connection, serie: str = SERIE) -> Iterator[tuple[str, float]]:
    """La serie salvata, dal periodo più vecchio al più recente."""
    yield from (
        (riga[0], riga[1])
        for riga in conn.execute(
            "SELECT data, valore_eur_mwh FROM pun WHERE serie = ? ORDER BY data", (serie,)
        )
    )


def _colonna(intestazione: list[str], cercata: str, *, esatta: bool) -> int:
    """Indice della colonna `cercata`: nome esatto o prefisso (colonna PUN)."""

    def corrisponde(cella: str) -> bool:
        return _uguale(cella, cercata) if esatta else _inizia(cella, cercata)

    trovate = [indice for indice, cella in enumerate(intestazione) if corrisponde(cella)]
    if len(trovate) != 1:
        raise ValueError(f"colonne `{cercata}` trovate: {len(trovate)}")
    return trovate[0]


def _uguale(cella: str, cercata: str) -> bool:
    return cella.strip().casefold() == cercata


def _inizia(cella: str, cercata: str) -> bool:
    return cella.strip().casefold().startswith(cercata)


def _fattore(intestazione: str) -> Decimal:
    """Fattore €/MWh ricavato dall'unità di misura dell'intestazione."""
    trovata = _UNITA.search(intestazione)
    if trovata is None:
        raise ValueError(f"unità di misura assente nell'intestazione: {_breve(intestazione)}")
    unita = trovata.group(1).strip().casefold().replace(" ", "")
    try:
        return FATTORI_EUR_MWH[unita]
    except KeyError:
        raise ValueError(f"unità di misura non prevista: {_breve(intestazione)}") from None


def _campo(campi: list[str], indice: int, numero: int) -> str:
    if indice >= len(campi):
        raise ValueError(f"riga {numero} con colonne insufficienti")
    return campi[indice]


def _data(grezzo: str) -> str:
    trovato = _PERIODO.match(grezzo.strip())
    if trovato is None:
        raise ValueError(f"periodo non valido: {_breve(grezzo)}")
    return f"{trovato.group(1)}-{trovato.group(2)}-01"


def _decimale(grezzo: str) -> Decimal | None:
    """Valore con virgola decimale. `None` se assente."""
    testo = grezzo.strip().replace(" ", "")
    if not testo:
        return None
    if "," in testo and "." in testo:
        raise ValueError(f"formato numerico non atteso: {_breve(testo)}")
    try:
        return Decimal(testo.replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"formato numerico non atteso: {_breve(testo)}") from None


def _breve(testo: str) -> str:
    return repr(testo[:MAX_ERRORE])
