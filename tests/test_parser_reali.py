"""Parser sui dati reali: percorsi del tracciato presenti nell'XML pubblicato.

Il primo test lavora sull'XML completo in `raw/` (file non versionato): se non
c'è, viene saltato. Gli altri usano frammenti XML scritti a mano per fissare
il comportamento dei percorsi ripetuti e dei campi noti senza colonna.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from xml.etree.ElementTree import fromstring

import pytest

from etl.parser import Offerta, iter_offerte, parse_offerta

RAW = Path(__file__).parent.parent / "raw"
TESTA = '<offerta xmlns="http://www.acquirenteunico.it/schemas/SII_AU/OffertaRetail/01">'


def trova_raw() -> Path | None:
    """L'XML completo più recente in `raw/AAAA-MM-GG/`, se presente."""
    candidati = sorted(RAW.glob("*/PO_Offerte_E_MLIBERO_*.xml"))
    return candidati[-1] if candidati else None


def _annida(percorso: str, valore: str) -> str:
    """Trasforma `A/B/C` nel frammento `<A><B><C>valore</C></B></A>`."""
    parti = percorso.split("/")
    apertura = "".join(f"<{parte}>" for parte in parti)
    chiusura = "".join(f"</{parte}>" for parte in reversed(parti))
    return f"{apertura}{valore}{chiusura}"


def _offerta(corpo: str) -> Offerta:
    """Costruisce una `<offerta>` con namespace, come l'XML pubblicato."""
    return parse_offerta(fromstring(f"{TESTA}{corpo}</offerta>"))


def test_percorsi_del_tracciato_e_nessuno_sconosciuto() -> None:
    """Ogni percorso dell'XML pubblicato è noto: zero percorsi sconosciuti."""
    percorso = trova_raw()
    if percorso is None:
        pytest.skip("XML completo non presente in raw/")

    n_offerte = n_componenti = n_condizioni = 0
    senza_componenti = senza_chiave = offerte_con_modalita_ripetute = 0
    sconosciuti: set[str] = set()
    tipo_offerta: Counter[str] = Counter()
    idx: Counter[str] = Counter()
    macroaree: set[str] = set()
    unita: set[str] = set()
    fasce: set[str | None] = set()
    chiavi: set[tuple[str, str]] = set()
    max_comuni = 0

    for offerta in iter_offerte(percorso):
        n_offerte += 1
        n_componenti += len(offerta.componenti)
        n_condizioni += len(offerta.condizioni)
        sconosciuti |= offerta.percorsi_sconosciuti

        piva = offerta.campi.get("piva")
        cod = offerta.campi.get("cod_offerta")
        if piva and cod:
            chiavi.add((piva, cod))
        else:
            senza_chiave += 1
        if not offerta.componenti:
            senza_componenti += 1
        assert offerta.campi.get("data_inizio"), "offerta senza data di inizio"
        assert offerta.campi.get("data_fine"), "offerta senza data di fine"

        tipo_offerta[str(offerta.campi.get("tipo_offerta"))] += 1
        if offerta.campi.get("idx_prezzo_energia"):
            idx[str(offerta.campi["idx_prezzo_energia"])] += 1
        for componente in offerta.componenti:
            macroaree.add(str(componente.campi.get("macroarea")))
            unita.add(str(componente.campi.get("unita_misura")))
            fasce.add(componente.campi.get("fascia"))

        modalita = offerta.extra.get("offerta/MetodoPagamento/MODALITA_PAGAMENTO")
        if isinstance(modalita, list):
            offerte_con_modalita_ripetute += 1
        comuni = offerta.extra.get("offerta/ZoneOfferta/COMUNE")
        if isinstance(comuni, list):
            max_comuni = max(max_comuni, len(comuni))

    assert sconosciuti == set()
    assert n_offerte == 3540
    assert n_componenti == 15269
    assert n_condizioni == 5186
    assert len(chiavi) == n_offerte
    assert senza_chiave == 0
    assert senza_componenti == 2
    assert tipo_offerta == {"02": 2893, "01": 646, "04": 1}
    assert idx == {"12": 2793, "01": 107, "08": 9, "05": 1}
    assert macroaree == {"01", "02", "04", "05", "06"}
    assert unita == {"01", "02", "03", "05"}
    assert fasce == {"01", "02", "03", "07", "08", "91", None}
    assert offerte_con_modalita_ripetute > 0
    assert max_comuni == 659


def test_percorsi_ripetuti_vanno_in_lista_e_primo_valore_in_colonna() -> None:
    offerta = _offerta(
        "<DettaglioOfferta><TIPOLOGIA_ATT_CONTR>01</TIPOLOGIA_ATT_CONTR>"
        "<TIPOLOGIA_ATT_CONTR>04</TIPOLOGIA_ATT_CONTR></DettaglioOfferta>"
        "<MetodoPagamento><MODALITA_PAGAMENTO>01</MODALITA_PAGAMENTO></MetodoPagamento>"
        "<MetodoPagamento><MODALITA_PAGAMENTO>04</MODALITA_PAGAMENTO></MetodoPagamento>"
    )
    assert offerta.campi["tipologia_att_contr"] == "01"
    assert offerta.extra["offerta/DettaglioOfferta/TIPOLOGIA_ATT_CONTR"] == ["01", "04"]
    assert offerta.campi["modalita_pagamento"] == "01"
    assert offerta.extra["offerta/MetodoPagamento/MODALITA_PAGAMENTO"] == ["01", "04"]
    assert offerta.percorsi_sconosciuti == set()


def test_valore_singolo_resta_una_lista_per_i_campi_ripetuti() -> None:
    offerta = _offerta(
        "<MetodoPagamento><MODALITA_PAGAMENTO>02</MODALITA_PAGAMENTO></MetodoPagamento>"
    )
    assert offerta.campi["modalita_pagamento"] == "02"
    assert offerta.extra["offerta/MetodoPagamento/MODALITA_PAGAMENTO"] == ["02"]


@pytest.mark.parametrize(
    ("percorso", "valore"),
    [
        ("offerta/TipoPrezzo/TIPOLOGIA_FASCE", "03"),
        ("offerta/TipoPrezzo/FasceOrarieSettimanali/F_LUNEDI", "1-1,96-2"),
        ("offerta/DettaglioOfferta/DOMESTICO_RESIDENTE", "03"),
        ("offerta/DettaglioOfferta/ModalitaAttivazione/DESCRIZIONE", "Solo online"),
        ("offerta/MetodoPagamento/DESCRIZIONE", "Domiciliazione"),
        ("offerta/Dispacciamento/DESCRIZIONE", "Incluso"),
        ("offerta/Dispacciamento/VALORE_DISP", "0.012"),
        ("offerta/RiferimentiPrezzoEnergia/COEFFICIENTE", "1"),
        ("offerta/RiferimentiPrezzoEnergia/ALTRO", "PUN"),
        ("offerta/ComponentiRegolate/CODICE", "01"),
        ("offerta/CaratteristicheOfferta/POTENZA_MAX", "6"),
        ("offerta/CaratteristicheOfferta/CONSUMO_MIN", "0"),
        ("offerta/Sconto/NOME", "Sconto web"),
        ("offerta/Sconto/PrezziSconto/PREZZO", "30"),
        ("offerta/Sconto/Condizione/CONDIZIONE_APPLICAZIONE", "01"),
        ("offerta/Sconto/PeriodoValidita/DURATA", "12"),
        ("offerta/ZoneOfferta/REGIONE", "12"),
        ("offerta/ZoneOfferta/COMUNE", "058091"),
        ("offerta/ProdottiServiziAggiuntivi/NOME", "Assistenza"),
        ("offerta/ProdottiServiziAggiuntivi/MACROAREA", "99"),
        ("offerta/OffertaDual/OFFERTE_CONGIUNTE_GAS", "000852DSVML01XXFUTURADUALGASAU01"),
        ("offerta/CondizioniContrattuali/ALTRO", "Testo libero della condizione"),
    ],
)
def test_percorsi_noti_senza_colonna_non_sono_sconosciuti(percorso: str, valore: str) -> None:
    offerta = _offerta(_annida(percorso.removeprefix("offerta/"), valore))
    assert offerta.extra[percorso] == valore
    assert offerta.percorsi_sconosciuti == set()


@pytest.mark.parametrize(
    ("percorso", "valore"),
    [
        ("ComponenteImpresa/IntervalloPrezzi/CONSUMO_DA", "0"),
        ("ComponenteImpresa/IntervalloPrezzi/CONSUMO_A", "50000"),
        ("ComponenteImpresa/IntervalloPrezzi/TIPO_PREZZO", "02"),
        ("ComponenteImpresa/IntervalloPrezzi/PeriodoValidita/DURATA", "12"),
        ("ComponenteImpresa/IntervalloPrezzi/PeriodoValidita/VALIDO_FINO", "12/2028"),
        ("ComponenteImpresa/IntervalloPrezzi/PeriodoValidita/MESE_VALIDITA", "01"),
    ],
)
def test_campi_della_componente_senza_colonna(percorso: str, valore: str) -> None:
    offerta = _offerta(_annida(percorso, valore))
    assert len(offerta.componenti) == 1
    assert offerta.componenti[0].extra[f"offerta/{percorso}"] == valore
    assert offerta.percorsi_sconosciuti == set()


def test_componente_con_nome_e_descrizione_ignota_resta_sconosciuta() -> None:
    offerta = _offerta(
        "<ComponenteImpresa><NOME>SPREAD</NOME><NOVITA>1</NOVITA>"
        "<IntervalloPrezzi><PREZZO>0.0132</PREZZO></IntervalloPrezzi></ComponenteImpresa>"
    )
    componente = offerta.componenti[0]
    assert componente.campi["nome"] == "SPREAD"
    assert componente.extra["offerta/ComponenteImpresa/NOVITA"] == "1"
    assert offerta.percorsi_sconosciuti == {"offerta/ComponenteImpresa/NOVITA"}
