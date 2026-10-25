"""Trasporto HTTP streamable locale (`--trasporto http`).

Il server deve ascoltare solo su loopback, esporre lo stesso tool dello stdio e
non modificare il database. Il processo viene sempre chiuso al termine del test.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

from mcp import Client

from tests.fixture_db import crea_db, offerta

RADICE = Path(__file__).resolve().parent.parent


def _porta_libera() -> int:
    with socket.socket() as presa:
        presa.bind(("127.0.0.1", 0))
        return int(presa.getsockname()[1])


def _attendi_porta(host: str, porta: int, timeout: float = 30.0) -> None:
    scadenza = time.monotonic() + timeout
    while time.monotonic() < scadenza:
        try:
            with socket.create_connection((host, porta), timeout=1.0):
                return
        except OSError:
            time.sleep(0.2)
    raise AssertionError("il server HTTP non si è avviato")


def _comando(*argomenti: str) -> tuple[list[str], dict[str, str]]:
    comando = [sys.executable, "-m", "offerte.mcp", *argomenti]
    ambiente = {**os.environ, "PYTHONPATH": str(RADICE)}
    return comando, ambiente


def test_http_espone_il_tool_e_non_modifica_il_db(tmp_path: Path) -> None:
    db = crea_db(tmp_path / "offerte.db", [offerta("11111111111", "A1", nome="Luce Casa")])
    porta = _porta_libera()
    comando, ambiente = _comando(
        "--trasporto", "http", "--host", "127.0.0.1", "--port", str(porta), "--db", str(db)
    )
    processo = subprocess.Popen(
        comando,
        cwd=str(RADICE),
        env=ambiente,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _attendi_porta("127.0.0.1", porta)
        prima = hashlib.sha256(db.read_bytes()).hexdigest()

        async def scenario() -> None:
            async with Client(
                f"http://127.0.0.1:{porta}/mcp", raise_exceptions=True, read_timeout_seconds=30
            ) as client:
                strumenti = await client.list_tools()
                assert [tool.name for tool in strumenti.tools] == ["cerca_offerte"]

                risultato = await client.call_tool("cerca_offerte", {"filtri": {}})
                assert risultato.is_error is False
                contenuto = cast(dict[str, Any], risultato.structured_content)
                assert contenuto["numero_risultati"] == 1
                assert contenuto["risultati"][0]["cod_offerta"] == "A1"

        asyncio.run(scenario())
        assert hashlib.sha256(db.read_bytes()).hexdigest() == prima
    finally:
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - difensivo
            processo.kill()
            processo.wait(timeout=10)


def test_host_non_loopback_rifiutato() -> None:
    comando, ambiente = _comando("--trasporto", "http", "--host", "0.0.0.0")
    esito = subprocess.run(
        comando, cwd=str(RADICE), env=ambiente, capture_output=True, text=True, timeout=60
    )
    assert esito.returncode == 2
    assert "loopback" in esito.stderr
    assert "0.0.0.0" in esito.stderr
