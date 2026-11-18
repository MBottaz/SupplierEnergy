"""Tabelle e risoluzione geografica (`offerte.zone`).

I codici sono ISTAT; i nomi sono quelli ufficiali, confrontati senza distinzione
fra maiuscole/minuscole, accenti e apostrofi. Non si usa il database.
"""

from __future__ import annotations

import pytest

from offerte.errori import InputNonValido
from offerte.zone import (
    PROVINCE,
    REGIONE_DI_PROVINCIA,
    REGIONI,
    codice_provincia,
    codice_regione,
    elenco_province,
    elenco_regioni,
    nome_provincia,
    nome_regione,
    regione_di_provincia,
)


def test_dimensioni_tabelle() -> None:
    assert len(REGIONI) == 20
    assert len(PROVINCE) == 107


def test_chiavi_e_nomi_univoci() -> None:
    assert list(REGIONI) == [f"{numero:02d}" for numero in range(1, 21)]
    assert all(len(codice) == 3 and codice.isdigit() for codice in PROVINCE)
    assert len(set(REGIONI.values())) == 20
    assert len(set(PROVINCE.values())) == 107


@pytest.mark.parametrize(
    ("valore", "atteso"),
    [
        ("Lombardia", "03"),
        ("lombardia", "03"),
        ("LOMBARDIA", "03"),
        ("Valle d'Aosta/Vallée d'Aoste", "02"),
        ("Valle d\u2019Aosta/Vallée d\u2019Aoste", "02"),
        ("valle d'aosta/vallee d'aoste", "02"),
        ("03", "03"),
        ("3", "03"),
    ],
)
def test_codice_regione(valore: str, atteso: str) -> None:
    assert codice_regione(valore) == atteso


@pytest.mark.parametrize(
    ("valore", "atteso"),
    [
        ("Milano", "015"),
        ("milano", "015"),
        ("Forlì-Cesena", "040"),
        ("forli-cesena", "040"),
        ("Reggio nell'Emilia", "035"),
        ("Bolzano/Bozen", "021"),
        ("015", "015"),
        ("15", "015"),
    ],
)
def test_codice_provincia(valore: str, atteso: str) -> None:
    assert codice_provincia(valore) == atteso


@pytest.mark.parametrize("valore", ["Atlantide", "", "99", "9999", "  "])
def test_regione_non_valida(valore: str) -> None:
    with pytest.raises(InputNonValido):
        codice_regione(valore)


@pytest.mark.parametrize("valore", ["Piemonte", "Atlantide", "", "9999"])
def test_provincia_non_valida(valore: str) -> None:
    with pytest.raises(InputNonValido):
        codice_provincia(valore)


def test_nomi_inversi() -> None:
    assert nome_regione("03") == "Lombardia"
    assert nome_provincia("015") == "Milano"
    assert nome_regione("99") is None
    assert nome_provincia("999") is None


def test_regione_di_provincia() -> None:
    assert regione_di_provincia("015") == "03"
    assert regione_di_provincia("058") == "12"
    assert regione_di_provincia("999") is None
    assert set(REGIONE_DI_PROVINCIA) == set(PROVINCE)
    assert set(REGIONE_DI_PROVINCIA.values()) <= set(REGIONI)


def test_elenchi() -> None:
    assert "Lombardia" in elenco_regioni()
    assert "Milano" in elenco_province()
