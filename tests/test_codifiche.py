"""Codifiche ufficiali del tracciato (docs/architettura.md §6, tabella `codifica`).

Le decodifiche sono copiate dal tracciato ufficiale, non indovinate: ogni
dominio qui è stato letto dal documento citato in `FONTE`.
"""

import pytest

from etl.codifiche import DECODIFICHE, DOMINI_TRACCIATO, FONTE

# Valori presenti nella fixture tests/fixtures/offerta_estratto.xml.
ATTESI: dict[str, dict[str, str]] = {
    "tipo_mercato": {"01": "Elettrico"},
    "tipo_cliente": {"01": "Domestico", "02": "Altri Usi"},
    "tipo_offerta": {"01": "Fisso", "02": "Variabile"},
    "tipologia_att_contr": {"99": "sempre"},
    "modalita_attivazione": {"01": "Offerta attivabile solo da web"},
    "modalita_pagamento": {"01": "Domiciliazione bancaria"},
    "tipo_dispacciamento": {"01": "Corrispettivo Dispacciamento"},
    "idx_prezzo_energia": {"12": "PUN Index GME (mensile)"},
    "tipologia_componente": {"01": "STANDARD"},
    "macroarea": {"01": "Commercializzazione quota fissa", "04": "Prezzo quota energia"},
    "fascia": {"01": "monorario/F1", "02": "F2", "03": "F3"},
    "unita_misura": {"01": "€/Anno", "03": "€/kWh"},
    "tipologia_condizione": {"03": "Recesso"},
    "limitante": {"02": "No, non è limitante"},
}


def test_fonte_ufficiale() -> None:
    assert FONTE.url.startswith("https://")
    assert FONTE.versione
    assert FONTE.data
    assert "tracciato" in FONTE.sezione.lower()


def test_domini_del_tracciato() -> None:
    assert set(DECODIFICHE) == set(DOMINI_TRACCIATO)


@pytest.mark.parametrize("dominio", sorted(DECODIFICHE))
def test_domini_non_vuoti_e_senza_duplicati(dominio: str) -> None:
    voci = DECODIFICHE[dominio]
    assert voci, dominio
    for codice, descrizione in voci.items():
        assert codice == codice.strip(), (dominio, codice)
        assert descrizione.strip(), (dominio, codice)


@pytest.mark.parametrize("dominio", sorted(ATTESI))
def test_decodifiche_usate_dalla_fixture(dominio: str) -> None:
    voci = DECODIFICHE[dominio]
    for codice, descrizione in ATTESI[dominio].items():
        assert voci.get(codice) == descrizione, (dominio, codice)


def test_idx_prezzo_energia_distingue_la_periodicita() -> None:
    indici = DECODIFICHE["idx_prezzo_energia"]
    pun = {codice for codice, testo in indici.items() if testo.startswith("PUN Index GME")}
    assert pun == {"01", "08", "12"}
    assert indici["06"] == "Cmem (mensile)"
