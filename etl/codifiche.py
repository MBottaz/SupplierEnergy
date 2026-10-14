"""Decodifiche ufficiali dei codici del tracciato delle offerte.

Fonte unica: il tracciato ufficiale pubblicato da Acquirente Unico per il SII,
sezione "Formato e tracciato delle Offerte". I codici e le descrizioni sono
copiati da lì; non si deduce nulla dai nomi dei campi.

Quando il tracciato cambia versione va aggiornato questo file (e `FONTE`), non
il parser.
"""

from __future__ import annotations

from typing import NamedTuple


class FonteTracciato(NamedTuple):
    """Riferimento al documento ufficiale da cui vengono le decodifiche."""

    titolo: str
    versione: str
    data: str
    sezione: str
    url: str


FONTE = FonteTracciato(
    titolo=("Funzionamento e Specifiche del Processo di Trasmissione Offerte Mercato Retail"),
    versione="5.0",
    data="2025-12-15",
    sezione="7 Formato e tracciato delle Offerte",
    url=(
        "https://siiportale.acquirenteunico.it/documents/11387888/11426817/"
        "Funzionamento+e+Specifiche+del+Processo+di+Trasmissione+Offerte+Mercato+"
        "Retail_v5.0.pdf/c7fb0256-ce8d-0977-3356-227cfaa91443?version=1.0"
    ),
)

# dominio → {codice: descrizione}. I nomi dei domini sono quelli dei campi XML,
# così una decodifica si trova senza ambiguità.
DECODIFICHE: dict[str, dict[str, str]] = {
    "tipo_mercato": {
        "01": "Elettrico",
        "02": "Gas",
        "03": "Dual Fuel",
    },
    "tipo_cliente": {
        "01": "Domestico",
        "02": "Altri Usi",
        "03": "Condominio Uso Domestico (Gas)",
    },
    "tipo_offerta": {
        "01": "Fisso",
        "02": "Variabile",
        "03": "FLAT",
        "04": "Mista",
    },
    "tipologia_att_contr": {
        "01": "Cambio Fornitore",
        "02": "Prima Attivazione (Contatore non presente)",
        "03": "Riattivazione (Contatore presente ma disattivato)",
        "04": "Voltura",
        "99": "sempre",
    },
    "modalita_attivazione": {
        "01": "Offerta attivabile solo da web",
        "02": "Offerta attivabile da qualsiasi canale",
        "03": "Presso punto vendita",
        "04": "Teleselling",
        "05": "Agenzia",
        "99": "Altro",
    },
    "modalita_pagamento": {
        "01": "Domiciliazione bancaria",
        "02": "Domiciliazione postale",
        "03": "Domiciliazione su carta di credito",
        "04": "Bollettino precompilato",
        "99": "Altro",
    },
    "tipo_dispacciamento": {
        "01": "Corrispettivo Dispacciamento",
        "02": "PD",
        "09": "Corrispettivo Capacità di Mercato STG",
        "10": "Corrispettivo capacità di mercato MT",
        "11": "Reintegrazione oneri salvaguardia",
        "12": "Reintegrazione oneri tutele graduali",
        "13": "DispBT",
        "14": "CdispD",
        "99": "Altro",
    },
    # La periodicità dell'indice fa parte della descrizione: lo stesso nome di
    # indice compare con codici diversi per trimestrale/bimestrale/mensile.
    "idx_prezzo_energia": {
        "01": "PUN Index GME (trimestrale)",
        "02": "TTF (trimestrale)",
        "03": "PSV (trimestrale)",
        "04": "Psbil (trimestrale)",
        "05": "PE (trimestrale)",
        "07": "Pfor (trimestrale)",
        "06": "Cmem (mensile)",
        "08": "PUN Index GME (bimestrale)",
        "09": "TTF (bimestrale)",
        "10": "PSV (bimestrale)",
        "11": "Psbil (bimestrale)",
        "12": "PUN Index GME (mensile)",
        "13": "TTF (mensile)",
        "14": "PSV (mensile)",
        "15": "Psbil (mensile)",
        "99": "Altro",
    },
    "tipologia_componente": {
        "01": "STANDARD",
        "02": "OPZIONALE",
    },
    "macroarea": {
        "01": "Commercializzazione quota fissa",
        "02": "Commercializzazione quota energia",
        "04": "Prezzo quota energia",
        "05": "Una Tantum",
        "06": "FER/Energia Verde",
    },
    # FASCIA_COMPONENTE, FASCIA_PREZZO e TIPOLOGIA_FASCIA usano gli stessi codici.
    "fascia": {
        "01": "monorario/F1",
        "02": "F2",
        "03": "F3",
        "04": "F4",
        "05": "F5",
        "06": "F6",
        "07": "Peak",
        "08": "OffPeak",
        "91": "F2+F3",
        "92": "F1+F3",
        "93": "F1+F2",
    },
    "unita_misura": {
        "01": "€/Anno",
        "02": "€/kW",
        "03": "€/kWh",
        "04": "€/Smc",
        "05": "€",
    },
    "tipologia_condizione": {
        "01": "Attivazione",
        "02": "Disattivazione",
        "03": "Recesso",
        "04": "Offerta Pluriennale",
        "05": "Oneri di Recesso Anticipato",
        "99": "Altro",
    },
    "limitante": {
        "01": "Si, è limitante",
        "02": "No, non è limitante",
    },
}

DOMINI_TRACCIATO: tuple[str, ...] = tuple(DECODIFICHE)
