"""Integrazione MCP su trasporto stdio.

Avvia `python -m offerte.mcp` come processo figlio (l'harness ufficiale del SDK),
crea un database temporaneo, invoca `cerca_offerte` come client MCP e confronta
l'intero JSON di risposta. Non usa `build/`, non usa la rete.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import Client, StdioServerParameters

from tests.fixture_db import crea_db, offerta

RADICE = Path(__file__).resolve().parent.parent

INIZIO = "2026-01-01T00:00:00+01:00"
FINE = "2999-12-31T23:59:59+01:00"

ATTESO_A1: dict[str, Any] = {
    "piva": "11111111111",
    "cod_offerta": "A1",
    "nome_offerta": "Luce Casa",
    "descrizione_offerta": "Offerta per la casa",
    "testo_venditore_non_fidato": True,
    "tipo_cliente": "01",
    "tipo_offerta": "02",
    "indicizzata": True,
    "data_inizio": INIZIO,
    "data_fine": FINE,
    "zone": {"regione": ["Lombardia"], "provincia": ["Milano"], "comune": ["Milano"]},
}

ATTESO_B1: dict[str, Any] = {
    "piva": "22222222222",
    "cod_offerta": "B1",
    "nome_offerta": "Luce Business",
    "descrizione_offerta": None,
    "testo_venditore_non_fidato": True,
    "tipo_cliente": "02",
    "tipo_offerta": "01",
    "indicizzata": False,
    "data_inizio": INIZIO,
    "data_fine": None,
    "zone": {
        "regione": ["Lombardia", "Piemonte"],
        "provincia": ["Milano", "Torino"],
        "comune": ["Milano", "Torino"],
    },
}


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
                zone={"REGIONE": "Lombardia", "PROVINCIA": "Milano", "COMUNE": "Milano"},
                data_inizio=INIZIO,
                data_fine=FINE,
            ),
            offerta(
                "22222222222",
                "B1",
                nome="Luce Business",
                tipo_cliente="02",
                tipo_offerta="01",
                idx_prezzo_energia=None,
                zone={
                    "REGIONE": ["Lombardia", "Piemonte"],
                    "PROVINCIA": ["Milano", "Torino"],
                    "COMUNE": ["Milano", "Torino"],
                },
                data_inizio=INIZIO,
                data_fine=None,
            ),
        ],
    )


def _parametri(percorso_db: Path) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "offerte.mcp", "--db", str(percorso_db)],
        cwd=str(RADICE),
        env={"PYTHONPATH": str(RADICE)},
    )


def _chiama(percorso_db: Path, filtri: dict[str, Any]) -> dict[str, Any]:
    async def scenario() -> dict[str, Any]:
        async with Client(
            _parametri(percorso_db), raise_exceptions=True, read_timeout_seconds=30
        ) as client:
            strumenti = await client.list_tools()
            assert [tool.name for tool in strumenti.tools] == ["cerca_offerte"]

            risultato = await client.call_tool("cerca_offerte", {"filtri": filtri})
            assert risultato.is_error is False
            assert risultato.structured_content is not None
            return cast(dict[str, Any], risultato.structured_content)

    return asyncio.run(scenario())


def test_risposta_completa_senza_filtri(db: Path) -> None:
    assert _chiama(db, {}) == {
        "risultati": [ATTESO_A1, ATTESO_B1],
        "numero_risultati": 2,
        "limit": 20,
        "troncato": False,
        "dati_aggiornati_al": "2026-10-14",
        "avvertenze": [],
    }


def test_filtro_geografico_con_lista(db: Path) -> None:
    risultato = _chiama(db, {"regione": "piemonte"})
    assert risultato["risultati"] == [ATTESO_B1]
    assert risultato["numero_risultati"] == 1
    assert risultato["limit"] == 20
    assert risultato["troncato"] is False
    assert any("zone" in voce for voce in risultato["avvertenze"])


def test_errore_strutturato_su_stdio(db: Path) -> None:
    async def scenario() -> None:
        async with Client(_parametri(db), raise_exceptions=True, read_timeout_seconds=30) as client:
            risultato = await client.call_tool("cerca_offerte", {"filtri": {"limit": 99}})
            assert risultato.is_error is True
            assert risultato.structured_content == {
                "codice": "input_non_valido",
                "messaggio": "limit deve essere un intero fra 1 e 50",
            }

    asyncio.run(scenario())
