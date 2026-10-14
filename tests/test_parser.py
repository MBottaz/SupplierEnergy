"""Parser tollerante dell'XML delle offerte (docs/architettura.md §5).

L'XML non previsto non fa mai fallire il caricamento: finisce in `extra` e
incrementa l'insieme dei percorsi sconosciuti.
"""

import io
from decimal import Decimal
from pathlib import Path

import pytest
from defusedxml.common import DefusedXmlException

from etl.parser import MAX_TESTO, Offerta, _pulisci, iter_offerte

FIXTURE = Path(__file__).parent / "fixtures"


def _offerte(percorso: Path) -> list[Offerta]:
    return list(iter_offerte(percorso))


def _offerte_da_xml(xml: str) -> list[Offerta]:
    return list(iter_offerte(io.BytesIO(xml.encode("utf-8"))))


def _offerta_singola(contenuto: str) -> Offerta:
    """Offerta minima con dentro `contenuto` (per i casi costruiti a mano)."""
    xml = (
        "<ListaOfferteMercatoLibero><offerta>"
        "<IdentificativiOfferta><PIVA_UTENTE>1</PIVA_UTENTE>"
        "<COD_OFFERTA>X</COD_OFFERTA></IdentificativiOfferta>"
        f"{contenuto}"
        "</offerta></ListaOfferteMercatoLibero>"
    )
    offerte = _offerte_da_xml(xml)
    assert len(offerte) == 1
    return offerte[0]


@pytest.fixture
def offerta() -> Offerta:
    offerte = _offerte(FIXTURE / "offerta_estratto.xml")
    assert len(offerte) == 1
    return offerte[0]


def test_unica_offerta(offerta: Offerta) -> None:
    assert offerta.campi["piva"] == "01244170526"
    assert offerta.campi["cod_offerta"] == "001686ESVFL00XXPFA0726AU00000000"


def test_campi_dell_offerta(offerta: Offerta) -> None:
    assert offerta.campi["nome"] == "POWER FLEX AZIENDA"
    assert offerta.campi["descrizione"] == "Offerta EE a prezzo variabile per altri usi"
    assert offerta.campi["tipo_mercato"] == "01"
    assert offerta.campi["offerta_singola"] == "SI"
    assert offerta.campi["tipo_cliente"] == "02"
    assert offerta.campi["tipo_offerta"] == "02"
    assert offerta.campi["tipologia_att_contr"] == "99"
    assert offerta.campi["durata"] == "-1"
    assert offerta.campi["garanzie"] == "NO"
    assert offerta.campi["idx_prezzo_energia"] == "12"
    assert offerta.campi["modalita_pagamento"] == "01"
    assert offerta.campi["tipo_dispacciamento"] == "01"
    assert offerta.campi["telefono"] == "074220813"
    assert offerta.campi["url_sito"] == "www.piuenergia.it"
    assert offerta.campi["url_offerta"] == "https://www.piuenergia.it/"


def test_date_normalizzate(offerta: Offerta) -> None:
    assert offerta.campi["data_inizio"] == "2026-07-21T12:25:58+02:00"
    assert offerta.campi["data_fine"] == "2026-10-10T23:59:59+02:00"


def test_quattro_componenti(offerta: Offerta) -> None:
    assert len(offerta.componenti) == 4

    spread = offerta.componenti[:3]
    assert [c.campi["fascia"] for c in spread] == ["01", "02", "03"]
    for componente in spread:
        assert componente.campi["nome"] == "SPREAD"
        assert componente.campi["macroarea"] == "04"
        assert componente.campi["prezzo"] == Decimal("0.0132")
        assert componente.campi["unita_misura"] == "03"
        assert componente.campi["descrizione"] == (
            "Contributo a copertura dei costi per la spesa materia prima"
        )
        assert componente.extra == {}

    quota = offerta.componenti[3]
    assert quota.campi["nome"] == "Quota comm."
    assert quota.campi["macroarea"] == "01"
    assert quota.campi["prezzo"] == Decimal("162")
    assert quota.campi["unita_misura"] == "01"
    assert quota.campi.get("fascia") is None


def test_una_condizione(offerta: Offerta) -> None:
    assert len(offerta.condizioni) == 1
    condizione = offerta.condizioni[0]
    assert condizione.campi["tipologia"] == "03"
    assert condizione.campi["limitante"] == "02"
    assert condizione.campi["descrizione"] == "Il contratto è a tempo indeterminato."


def test_extra_noti_non_contano_come_sconosciuti(offerta: Offerta) -> None:
    assert offerta.extra["offerta/DettaglioOfferta/ModalitaAttivazione/MODALITA"] == "01"
    assert offerta.extra["offerta/Dispacciamento/NOME"] == "Dispacciamento"
    assert offerta.percorsi_sconosciuti == frozenset()


def test_elemento_inventato_finisce_in_extra() -> None:
    offerta = _offerte(FIXTURE / "offerta_elemento_sconosciuto.xml")[0]
    assert offerta.campi["piva"] == "00000000000"
    assert offerta.campi["nome"] == "OFFERTA CON ELEMENTO NON PREVISTO"
    assert offerta.extra["offerta/DettaglioOfferta/ELEMENTO_INVENTATO"] == "valore-inventato"
    assert offerta.percorsi_sconosciuti == frozenset(
        {
            "offerta/DettaglioOfferta/ELEMENTO_INVENTATO",
            "offerta/ComponenteImpresa/ELEMENTO_COMPONENTE_INVENTATO",
        }
    )
    assert offerta.componenti[0].extra == {
        "offerta/ComponenteImpresa/ELEMENTO_COMPONENTE_INVENTATO": "valore-componente"
    }
    # il resto della componente resta leggibile
    assert offerta.componenti[0].campi["fascia"] == "01"


def test_percorso_sconosciuto_ripetuto_diventa_lista() -> None:
    offerta = _offerta_singola(
        "<DettaglioOfferta><INVENTATO>a</INVENTATO><INVENTATO>b</INVENTATO></DettaglioOfferta>"
    )
    assert offerta.extra["offerta/DettaglioOfferta/INVENTATO"] == ["a", "b"]
    assert offerta.percorsi_sconosciuti == frozenset({"offerta/DettaglioOfferta/INVENTATO"})


def test_attributi_non_previsti_contano() -> None:
    offerta = _offerta_singola(
        '<DettaglioOfferta nome="valore"><NOME_OFFERTA>A</NOME_OFFERTA></DettaglioOfferta>'
    )
    assert offerta.extra["offerta/DettaglioOfferta@nome"] == "valore"
    assert "offerta/DettaglioOfferta@nome" in offerta.percorsi_sconosciuti
    assert offerta.campi["nome"] == "A"


def test_elemento_sconosciuto_nella_condizione() -> None:
    offerta = _offerta_singola(
        "<CondizioniContrattuali><LIMITANTE>02</LIMITANTE>"
        "<ELEMENTO_CONDIZIONE_INVENTATO>x</ELEMENTO_CONDIZIONE_INVENTATO>"
        "</CondizioniContrattuali>"
    )
    assert offerta.condizioni[0].campi["limitante"] == "02"
    assert offerta.extra["offerta/CondizioniContrattuali/ELEMENTO_CONDIZIONE_INVENTATO"] == "x"
    assert (
        "offerta/CondizioniContrattuali/ELEMENTO_CONDIZIONE_INVENTATO"
        in offerta.percorsi_sconosciuti
    )


def test_prezzo_non_numerico_non_fa_fallire() -> None:
    offerta = _offerta_singola(
        "<ComponenteImpresa><NOME>SPREAD</NOME><IntervalloPrezzi>"
        "<PREZZO>non-un-numero</PREZZO></IntervalloPrezzi></ComponenteImpresa>"
    )
    assert offerta.componenti[0].campi.get("prezzo") is None
    assert offerta.componenti[0].extra["offerta/ComponenteImpresa/IntervalloPrezzi/PREZZO"] == (
        "non-un-numero"
    )
    assert "offerta/ComponenteImpresa/IntervalloPrezzi/PREZZO" in offerta.percorsi_sconosciuti


def test_data_non_valida_non_fa_fallire() -> None:
    offerta = _offerta_singola(
        "<ValiditaOfferta><DATA_INIZIO>31/02/2026_10:00:00</DATA_INIZIO></ValiditaOfferta>"
    )
    assert offerta.campi.get("data_inizio") is None
    assert offerta.extra["offerta/ValiditaOfferta/DATA_INIZIO"] == "31/02/2026_10:00:00"
    assert "offerta/ValiditaOfferta/DATA_INIZIO" in offerta.percorsi_sconosciuti


def test_un_componente_per_intervallo_prezzi() -> None:
    offerta = _offerta_singola(
        "<ComponenteImpresa><NOME>Quota comm.</NOME><MACROAREA>01</MACROAREA>"
        "<IntervalloPrezzi><PREZZO>120</PREZZO></IntervalloPrezzi>"
        "<IntervalloPrezzi><PREZZO>130</PREZZO>"
        "<FASCIA_COMPONENTE>01</FASCIA_COMPONENTE>"
        "</IntervalloPrezzi></ComponenteImpresa>"
    )
    assert [c.campi["prezzo"] for c in offerta.componenti] == [Decimal("120"), Decimal("130")]
    assert [c.campi["macroarea"] for c in offerta.componenti] == ["01", "01"]
    assert [c.campi.get("fascia") for c in offerta.componenti] == [None, "01"]


def test_componente_senza_intervallo_prezzi() -> None:
    offerta = _offerta_singola(
        "<ComponenteImpresa><NOME>Quota comm.</NOME><MACROAREA>01</MACROAREA></ComponenteImpresa>"
    )
    assert len(offerta.componenti) == 1
    assert offerta.componenti[0].campi["nome"] == "Quota comm."
    assert offerta.percorsi_sconosciuti == frozenset()


def test_testo_normalizzato(offerta: Offerta) -> None:
    # Il testo dei venditori arriva su più righe e con spazi multipli.
    assert offerta.componenti[0].campi["descrizione"] == (
        "Contributo a copertura dei costi per la spesa materia prima"
    )


def test_caratteri_di_controllo_rimossi() -> None:
    assert _pulisci("Nome\x07  con\n\tcontrolli") == "Nome con controlli"
    assert _pulisci("\x00\x1f") is None
    assert _pulisci(None) is None
    assert _pulisci("   ") is None


def test_testo_troncato() -> None:
    offerta = _offerta_singola(
        "<DettaglioOfferta><DESCRIZIONE>" + "a" * (MAX_TESTO + 100) + "</DESCRIZIONE>"
        "</DettaglioOfferta>"
    )
    assert len(str(offerta.campi["descrizione"])) == MAX_TESTO


def test_entita_esterna_non_risolta() -> None:
    with pytest.raises(DefusedXmlException):
        _offerte(FIXTURE / "offerta_entita_esterna.xml")


def test_entita_interne_non_espanse() -> None:
    entita = "".join(f'<!ENTITY a{i} "{"&a" + str(i - 1) + ";" * 10}">' for i in range(1, 12))
    xml = (
        '<?xml version="1.0"?><!DOCTYPE ListaOfferteMercatoLibero ['
        + entita
        + "]><offerta><IdentificativiOfferta><NOME_OFFERTA>&a11;</NOME_OFFERTA>"
        "</IdentificativiOfferta></offerta>"
    )
    with pytest.raises(DefusedXmlException):
        _offerte_da_xml(xml)


def test_xml_troncato_solleva_errore() -> None:
    troncato = (FIXTURE / "offerta_estratto.xml").read_text(encoding="utf-8")[:200]
    with pytest.raises(Exception):  # noqa: B017 - l'errore di expat non è stabile
        _offerte_da_xml(troncato)
