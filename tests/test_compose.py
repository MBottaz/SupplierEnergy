"""Configurazione Docker Compose: servizi, permessi e nessuna porta pubblica.

I controlli sul testo sono statici e girano sempre; la validazione con
`docker compose config` viene saltata dove Docker non è disponibile.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent
COMPOSE = RADICE / "compose.yml"
COMPOSE_LOCALE = RADICE / "deploy" / "compose.local.yml"
ENV_ESEMPIO = RADICE / ".env.example"


def test_mcp_pubblica_la_porta_solo_sul_loopback() -> None:
    testo = COMPOSE.read_text(encoding="utf-8")

    assert "127.0.0.1:${OFFERTE_MCP_PORT:-8000}:8000" in testo
    assert "0.0.0.0:8000:8000" not in testo
    # Il bind non-loopback del container è esplicito, mai implicito.
    assert "OFFERTE_MCP_HOST: 0.0.0.0" in testo
    assert "OFFERTE_MCP_CONSENTI_NON_LOOPBACK" in testo


def test_mcp_usa_http_e_non_avvia_etl() -> None:
    testo = COMPOSE.read_text(encoding="utf-8")

    assert 'command: ["-m", "offerte.mcp", "--trasporto", "http"]' in testo
    # Il job ETL è sotto profilo: `docker compose up` da solo non lo esegue.
    assert 'profiles: ["etl"]' in testo
    assert 'restart: "no"' in testo


def test_utenti_e_permessi_separano_mcp_e_etl() -> None:
    testo = COMPOSE.read_text(encoding="utf-8")

    assert "user: offerte-mcp" in testo
    assert "user: offerte-etl" in testo
    # MCP monta il database in sola lettura; non riceve i raw.
    assert "offerte-db:/var/lib/offerte/db:ro" in testo
    assert "offerte-raw" in testo
    assert "read_only: true" in testo
    assert "no-new-privileges:true" in testo
    assert "cap_drop" in testo


def test_etl_usa_il_nome_del_csv_parametri_con_la_data() -> None:
    testo = COMPOSE.read_text(encoding="utf-8")

    assert "OFFERTE_PARAMETRI_DIR" in testo
    assert "OFFERTE_PARAMETRI_NOME" in testo
    assert "PO_Parametri_Mercato_Libero_E_" in testo


def test_esempio_env_senza_credenziali() -> None:
    testo = ENV_ESEMPIO.read_text(encoding="utf-8")

    assert "OFFERTE_MCP_PORT=" in testo
    assert "OFFERTE_PARAMETRI_DIR=" in testo
    for vietato in ("TOKEN", "SECRET", "PASSWORD", "API_KEY"):
        assert vietato not in testo


def test_override_locale_esiste_e_non_pubblica() -> None:
    testo = COMPOSE_LOCALE.read_text(encoding="utf-8")

    assert "compose.local.yml" in testo
    assert "ports:" not in testo


def test_docker_compose_config_valido() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker non disponibile")

    esito = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "--profile", "etl", "config"],
        cwd=str(RADICE),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert esito.returncode == 0, esito.stderr
    assert "offerte-mcp" in esito.stdout
    assert "offerte-etl" in esito.stdout
    assert "host_ip: 127.0.0.1" in esito.stdout
