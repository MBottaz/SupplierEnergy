"""Verifica che struttura e strumenti siano in piedi.

Il test più utile che si possa scrivere prima di avere codice: se `just check`
è verde su questo, lint, tipi e test girano davvero.
"""

import importlib

import pytest


@pytest.mark.parametrize("pacchetto", ["etl", "offerte"])
def test_pacchetti_importabili(pacchetto: str) -> None:
    assert importlib.import_module(pacchetto) is not None
