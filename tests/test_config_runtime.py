"""Configurazione dei percorsi runtime per ETL e server MCP."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest
from mcp import Client

from etl.__main__ import main
from offerte import config
from offerte.db import apri_db
from offerte.mcp import _argomenti, crea_server, percorso_db_da_ambiente
from tests.fixture_db import crea_db, offerta

FIXTURE_XML = Path(__file__).parent / "fixtures" / "offerta_estratto.xml"
FIXTURE_CSV = Path(__file__).parent / "fixtures" / "PO_Parametri_Mercato_Libero_E_20261014.csv"


def test_etl_usa_i_percorsi_runtime_dall_ambiente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "db" / "attivo.db"
    parametri = tmp_path / "PO_Parametri_Mercato_Libero_E_20261014.csv"
    parametri.write_bytes(FIXTURE_CSV.read_bytes())
    monkeypatch.setenv("OFFERTE_DB", str(db))
    monkeypatch.setenv("OFFERTE_PARAMETRI", str(parametri))

    assert main(["locale", "--raw", str(FIXTURE_XML), "--snapshot", "2026-10-14"]) == 0

    risultato: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert risultato["esito"] == "ok"
    assert risultato["n_parametri"] == 6
    assert db.is_file()
    assert not (tmp_path / "db" / "attivo.db.new").exists()


def test_ambiente_configura_raw_parametri_e_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFFERTE_DB", "/srv/offerte/db/attivo.db")
    monkeypatch.setenv("OFFERTE_RAW_DIR", "/srv/offerte/raw")
    monkeypatch.setenv("OFFERTE_PARAMETRI", "/srv/offerte/parametri.csv")
    monkeypatch.setenv("OFFERTE_MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("OFFERTE_MCP_PORT", "8123")

    assert percorso_db_da_ambiente() == Path("/srv/offerte/db/attivo.db")
    assert config.percorso_raw_da_ambiente() == Path("/srv/offerte/raw")
    assert config.percorso_parametri_da_ambiente() == Path("/srv/offerte/parametri.csv")
    argomenti = _argomenti([])
    assert argomenti.host == "127.0.0.1"
    assert argomenti.port == 8123


def test_server_usa_db_da_ambiente_in_sola_lettura(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = crea_db(
        tmp_path / "non-predefinito.db",
        [offerta("11111111111", "A1", data_fine="2099-12-31T23:59:59+01:00")],
    )
    monkeypatch.setenv("OFFERTE_DB", str(db))
    prima = hashlib.sha256(db.read_bytes()).hexdigest()

    async def scenario() -> None:
        async with Client(crea_server(), raise_exceptions=True) as client:
            risultato = await client.call_tool("cerca_offerte", {"filtri": {}})
            contenuto = cast(dict[str, Any], risultato.structured_content)
            assert contenuto["numero_risultati"] == 1

    asyncio.run(scenario())
    assert hashlib.sha256(db.read_bytes()).hexdigest() == prima

    with apri_db(percorso_db_da_ambiente()) as conn, pytest.raises(sqlite3.Error):
        conn.execute("CREATE TABLE tentativo_mcp (id INTEGER)")
