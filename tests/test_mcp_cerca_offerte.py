"""Comportamento del tool MCP `cerca_offerte` (client in-memory, senza stdio).

Verifica che il server deleghi alla libreria, che le risposte siano JSON
strutturati, che gli errori siano strutturati e che il database non venga mai
modificato.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp.types import CallToolResult, TextContent

from offerte.mcp import crea_server
from tests.fixture_db import crea_db, offerta


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return crea_db(
        tmp_path / "offerte.db",
        [
            offerta(
                "11111111111",
                "A1",
                nome="Luce Casa",
                descrizione="Offerta per la casa",
                zone={"REGIONE": "Lombardia", "PROVINCIA": "Milano"},
            ),
            offerta(
                "22222222222",
                "B1",
                nome="Luce Business",
                tipo_cliente="02",
                idx_prezzo_energia=None,
            ),
        ],
    )


def _chiama(percorso_db: Path, filtri: dict[str, Any]) -> CallToolResult:
    async def scenario() -> CallToolResult:
        async with Client(crea_server(percorso_db), raise_exceptions=True) as client:
            return await client.call_tool("cerca_offerte", {"filtri": filtri})

    return asyncio.run(scenario())


def _testo(risultato: CallToolResult) -> str:
    blocco = risultato.content[0]
    assert isinstance(blocco, TextContent)
    return blocco.text


def test_chiamata_valida(db: Path) -> None:
    risultato = _chiama(db, {"fornitore": "11111111111"})
    assert risultato.is_error is False
    contenuto = risultato.structured_content
    assert contenuto is not None
    assert contenuto["numero_risultati"] == 1
    assert contenuto["troncato"] is False
    assert contenuto["dati_aggiornati_al"] == "2026-10-14"

    riga = contenuto["risultati"][0]
    assert riga["piva"] == "11111111111"
    assert riga["cod_offerta"] == "A1"
    assert riga["testo_venditore_non_fidato"] is True
    assert riga["zone"]["regione"] == ["Lombardia"]

    assert json.loads(_testo(risultato)) == contenuto


def test_senza_filtri(db: Path) -> None:
    risultato = _chiama(db, {})
    assert risultato.is_error is False
    assert risultato.structured_content is not None
    assert risultato.structured_content["numero_risultati"] == 2


def test_nessun_risultato(db: Path) -> None:
    risultato = _chiama(db, {"fornitore": "00000000000"})
    assert risultato.is_error is False
    assert risultato.structured_content is not None
    assert risultato.structured_content["risultati"] == []
    assert risultato.structured_content["troncato"] is False


@pytest.mark.parametrize(
    ("filtri", "codice"),
    [
        ({"limit": 0}, "input_non_valido"),
        ({"limit": "venti"}, "input_non_valido"),
        ({"regione": ["Lombardia"]}, "input_non_valido"),
        ({"nome_fornitore": "Enel"}, "filtro_non_supportato"),
    ],
)
def test_errore_strutturato(db: Path, filtri: dict[str, Any], codice: str) -> None:
    risultato = _chiama(db, filtri)
    assert risultato.is_error is True
    assert risultato.structured_content is not None
    assert risultato.structured_content["codice"] == codice
    assert risultato.structured_content["messaggio"]
    assert json.loads(_testo(risultato)) == risultato.structured_content


def test_database_non_disponibile(tmp_path: Path) -> None:
    risultato = _chiama(tmp_path / "manca.db", {})
    assert risultato.is_error is True
    assert risultato.structured_content is not None
    assert risultato.structured_content["codice"] == "database_non_disponibile"


def test_database_non_modificato(db: Path) -> None:
    prima = hashlib.sha256(db.read_bytes()).hexdigest()
    _chiama(db, {})
    _chiama(db, {"limit": 0})
    _chiama(db, {"nome_fornitore": "Enel"})
    assert hashlib.sha256(db.read_bytes()).hexdigest() == prima
