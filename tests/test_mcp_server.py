"""Verifica dello stack MCP: il server espone l'unico tool previsto.

Nessuna interrogazione del database: qui si controlla solo che il server si
istanzi, che un client MCP in-memory lo scopra e che lo schema degli input sia
quello del contratto (`docs/contratto_cerca_offerte.md`).
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp import Client

from offerte.mcp import crea_server

FILTRI_ATTESI = {
    "fornitore",
    "regione",
    "provincia",
    "comune",
    "tipo_cliente",
    "tipo_offerta",
    "indicizzata",
    "testo",
    "limit",
}


def test_il_server_espone_solo_cerca_offerte() -> None:
    async def scenario() -> None:
        async with Client(crea_server(), raise_exceptions=True) as client:
            elenco = await client.list_tools()
            assert [tool.name for tool in elenco.tools] == ["cerca_offerte"]

            tool = elenco.tools[0]
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.open_world_hint is False

            schema: dict[str, Any] = tool.input_schema
            assert schema["type"] == "object"
            assert set(schema["properties"]) == {"filtri"}

            riferimento = schema["properties"]["filtri"]["anyOf"][0]["$ref"]
            nome_modello = riferimento.rsplit("/", 1)[-1]
            filtri = schema["$defs"][nome_modello]
            assert filtri["type"] == "object"
            assert set(filtri["properties"]) == FILTRI_ATTESI
            assert filtri["additionalProperties"] is True
            assert filtri["properties"]["tipo_cliente"]["enum"] == [
                "domestico",
                "altri usi",
                "condominio uso domestico (gas)",
            ]
            assert filtri["properties"]["tipo_offerta"]["enum"] == [
                "fisso",
                "variabile",
                "flat",
                "mista",
            ]
            assert filtri["properties"]["indicizzata"]["enum"] == [True, False]

            descrizione = " ".join((tool.description or "").split())
            for nome in FILTRI_ATTESI:
                assert nome in descrizione
            assert "Il nome commerciale NON è nel modello dati" in descrizione
            assert "domestico" in descrizione
            assert "altri usi" in descrizione
            assert "variabile" in descrizione

    asyncio.run(scenario())
