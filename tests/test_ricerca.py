"""Ricerca applicativa condivisa (`offerte.ricerca.cerca_offerte`).

Database temporaneo con poche offerte costruite a mano: coprono zone singole e
ripetute, offerta scaduta, `data_fine` nulla, indicizzate e fisse, testo libero
(bianco e con caratteri speciali di `LIKE`) e il troncamento.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from offerte.db import apri_db
from offerte.errori import FiltroNonSupportato, InputNonValido
from offerte.ricerca import cerca_offerte
from tests.fixture_db import crea_db, offerta

FUTURO = "2999-12-31T23:59:59+01:00"
PASSATO = "2000-01-01T00:00:00+01:00"


@pytest.fixture
def db(tmp_path: Path) -> Path:
    righe = [
        offerta(
            "11111111111",
            "A1",
            nome="Luce Casa",
            descrizione="Offerta per la casa",
            tipo_cliente="01",
            tipo_offerta="02",
            idx_prezzo_energia="PUN_MENSILE",
            data_fine=FUTURO,
            zone={"REGIONE": "Lombardia", "PROVINCIA": "Milano", "COMUNE": "Milano"},
        ),
        offerta(
            "11111111111",
            "A2",
            nome="Luce Business",
            descrizione="Per partita IVA",
            tipo_cliente="02",
            tipo_offerta="01",
            idx_prezzo_energia=None,
            data_fine=FUTURO,
            zone={
                "REGIONE": ["Lombardia", "Piemonte"],
                "PROVINCIA": ["Milano", "Torino"],
                "COMUNE": ["Milano", "Torino"],
            },
        ),
        offerta(
            "22222222222",
            "B1",
            nome="Luce Scaduta",
            tipo_cliente="01",
            tipo_offerta="03",
            idx_prezzo_energia="PUN_MENSILE",
            data_fine=PASSATO,
        ),
        offerta(
            "22222222222",
            "B2",
            nome="Luce Senza Scadenza",
            descrizione="Nessuna data finale",
            tipo_cliente="01",
            tipo_offerta="04",
            idx_prezzo_energia=None,
            data_fine=None,
            zone={"REGIONE": "Lazio", "COMUNE": ["Roma"]},
        ),
        offerta(
            "33333333333",
            "C1",
            nome="100% Luce",
            descrizione="Sconto percentuale",
            tipo_cliente="02",
            tipo_offerta="01",
            idx_prezzo_energia=None,
            data_fine=FUTURO,
            zone={"REGIONE": "Forlì"},
        ),
    ]
    righe.extend(
        offerta("99999999999", f"E{numero:02d}", idx_prezzo_energia=None, data_fine=FUTURO)
        for numero in range(1, 26)
    )
    return crea_db(tmp_path / "offerte.db", righe)


def _cerca(db: Path, **filtri: object) -> dict[str, Any]:
    with apri_db(db) as conn:
        return cerca_offerte(conn, filtri)


def _identificativi(risultato: dict[str, Any]) -> list[tuple[str, str]]:
    return [(riga["piva"], riga["cod_offerta"]) for riga in risultato["risultati"]]


def test_senza_filtri_tronca_e_ordina(db: Path) -> None:
    risultato = _cerca(db)
    assert risultato["limit"] == 20
    assert risultato["troncato"] is True
    assert risultato["numero_risultati"] == 20

    coppie = _identificativi(risultato)
    assert coppie == sorted(coppie)
    assert coppie[0] == ("11111111111", "A1")
    assert coppie[-1] == ("99999999999", "E16")
    assert risultato["dati_aggiornati_al"] == "2026-10-14"
    assert risultato["avvertenze"] == []
    json.dumps(risultato)


def test_filtro_fornitore(db: Path) -> None:
    risultato = _cerca(db, fornitore="11111111111")
    assert _identificativi(risultato) == [("11111111111", "A1"), ("11111111111", "A2")]
    assert risultato["troncato"] is False
    assert any("nome commerciale" in voce for voce in risultato["avvertenze"])


def test_filtro_regione_case_insensitive(db: Path) -> None:
    assert _identificativi(_cerca(db, regione="lombardia")) == [
        ("11111111111", "A1"),
        ("11111111111", "A2"),
    ]
    assert _identificativi(_cerca(db, regione="LAZIO")) == [("22222222222", "B2")]


def test_filtro_provincia_e_comune(db: Path) -> None:
    assert _identificativi(_cerca(db, provincia="TORINO")) == [("11111111111", "A2")]
    assert _identificativi(_cerca(db, comune="roma")) == [("22222222222", "B2")]
    assert _identificativi(_cerca(db, provincia="Piemonte")) == []


def test_geografia_ripetuta_in_lista(db: Path) -> None:
    risultato = _cerca(db, regione="Piemonte")
    assert _identificativi(risultato) == [("11111111111", "A2")]
    assert risultato["risultati"][0]["zone"]["regione"] == ["Lombardia", "Piemonte"]


def test_filtro_regione_con_accento(db: Path) -> None:
    assert _identificativi(_cerca(db, regione="FORLÌ")) == [("33333333333", "C1")]
    assert _identificativi(_cerca(db, regione="forlì")) == [("33333333333", "C1")]


def test_filtro_tipo_cliente(db: Path) -> None:
    assert _identificativi(_cerca(db, tipo_cliente="02")) == [
        ("11111111111", "A2"),
        ("33333333333", "C1"),
    ]


def test_filtro_tipo_offerta(db: Path) -> None:
    assert _identificativi(_cerca(db, tipo_offerta="04")) == [("22222222222", "B2")]


def test_filtro_indicizzata(db: Path) -> None:
    assert _identificativi(_cerca(db, indicizzata=True)) == [("11111111111", "A1")]

    fisse = _identificativi(_cerca(db, indicizzata=False, limit=50))
    assert fisse[:3] == [
        ("11111111111", "A2"),
        ("22222222222", "B2"),
        ("33333333333", "C1"),
    ]
    assert len(fisse) == 28


def test_ricerca_testuale_su_nome_e_descrizione(db: Path) -> None:
    assert _identificativi(_cerca(db, testo="business")) == [("11111111111", "A2")]
    assert _identificativi(_cerca(db, testo="PARTITA IVA")) == [("11111111111", "A2")]
    assert _identificativi(_cerca(db, testo="casa")) == [("11111111111", "A1")]
    assert any("nome e descrizione" in voce for voce in _cerca(db, testo="casa")["avvertenze"])


def test_ricerca_testuale_esegue_l_escape_di_like(db: Path) -> None:
    # Il `%` dell'utente deve essere un carattere, non un jolly.
    assert _identificativi(_cerca(db, testo="100%")) == [("33333333333", "C1")]


def test_combinazione_di_filtri(db: Path) -> None:
    risultato = _cerca(db, fornitore="11111111111", regione="Piemonte", indicizzata=False)
    assert _identificativi(risultato) == [("11111111111", "A2")]


def test_limite_esplicito(db: Path) -> None:
    risultato = _cerca(db, limit=2)
    assert risultato["limit"] == 2
    assert risultato["numero_risultati"] == 2
    assert risultato["troncato"] is True
    assert len(_identificativi(risultato)) == 2

    tutti = _cerca(db, limit=50)
    assert tutti["limit"] == 50
    assert tutti["troncato"] is False
    assert tutti["numero_risultati"] == 29


def test_nessun_risultato(db: Path) -> None:
    risultato = _cerca(db, fornitore="00000000000")
    assert risultato["risultati"] == []
    assert risultato["numero_risultati"] == 0
    assert risultato["troncato"] is False


def test_validita_temporale(db: Path) -> None:
    codici = {cod for _, cod in _identificativi(_cerca(db, limit=50))}
    assert "B1" not in codici  # scaduta
    assert "B2" in codici  # data_fine nulla: valida


@pytest.mark.parametrize(
    "filtri",
    [
        {"limit": 0},
        {"limit": 51},
        {"limit": "venti"},
        {"limit": True},
        {"tipo_cliente": "1"},
        {"tipo_cliente": "abc"},
        {"tipo_offerta": 1},
        {"regione": "  "},
        {"regione": 5},
        {"regione": ["Lombardia"]},
        {"fornitore": ""},
        {"indicizzata": "true"},
        {"indicizzata": 1},
        {"testo": "x" * 201},
    ],
)
def test_input_non_valido(db: Path, filtri: dict[str, object]) -> None:
    with pytest.raises(InputNonValido) as errore, apri_db(db) as conn:
        cerca_offerte(conn, filtri)
    assert errore.value.come_dizionario()["codice"] == "input_non_valido"
    assert errore.value.messaggio


def test_filtro_non_supportato(db: Path) -> None:
    with pytest.raises(FiltroNonSupportato) as errore, apri_db(db) as conn:
        cerca_offerte(conn, {"nome_fornitore": "Enel"})
    assert errore.value.come_dizionario() == {
        "codice": "filtro_non_supportato",
        "messaggio": "filtro non supportato: nome_fornitore",
    }


def test_db_vuoto(tmp_path: Path) -> None:
    vuoto = crea_db(tmp_path / "vuoto.db", [])
    risultato = _cerca(vuoto)
    assert risultato["risultati"] == []
    assert risultato["dati_aggiornati_al"] is None
