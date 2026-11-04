"""Percorsi e impostazioni runtime condivisi da ETL e interfacce.

I default sono quelli previsti per i container. In sviluppo si possono usare
sempre le opzioni CLI oppure sovrascriverli con le variabili d'ambiente; le
opzioni CLI hanno precedenza sulle variabili.
"""

from __future__ import annotations

import os
from pathlib import Path

VARIABILE_DB = "OFFERTE_DB"
VARIABILE_RAW_DIR = "OFFERTE_RAW_DIR"
VARIABILE_PARAMETRI = "OFFERTE_PARAMETRI"
VARIABILE_MCP_HOST = "OFFERTE_MCP_HOST"
VARIABILE_MCP_PORT = "OFFERTE_MCP_PORT"
VARIABILE_MCP_CONSENTI_NON_LOOPBACK = "OFFERTE_MCP_CONSENTI_NON_LOOPBACK"

NOME_DB_DEFAULT = Path("/var/lib/offerte/db/offerte.db")
NOME_RAW_DEFAULT = Path("/var/lib/offerte/raw")
HOST_MCP_DEFAULT = "127.0.0.1"
PORTA_MCP_DEFAULT = 8000

#: Valori accettati come "vero" per le variabili booleane d'ambiente.
_VERI = frozenset({"1", "true", "yes", "on"})


def _booleano_env(nome: str) -> bool:
    return os.environ.get(nome, "").strip().lower() in _VERI


def _percorso_env(nome: str, default: Path) -> Path:
    valore = os.environ.get(nome)
    return Path(valore) if valore else default


def percorso_db_da_ambiente() -> Path:
    """Restituisce il database attivo configurato dall'ambiente."""
    return _percorso_env(VARIABILE_DB, NOME_DB_DEFAULT)


def percorso_raw_da_ambiente() -> Path:
    """Restituisce la radice dei raw configurata dall'ambiente."""
    return _percorso_env(VARIABILE_RAW_DIR, NOME_RAW_DEFAULT)


def percorso_parametri_da_ambiente() -> Path | None:
    """Restituisce il CSV parametri, se configurato dall'ambiente."""
    valore = os.environ.get(VARIABILE_PARAMETRI)
    return Path(valore) if valore else None


def host_mcp_da_ambiente() -> str:
    """Restituisce l'interfaccia HTTP MCP configurata dall'ambiente."""
    return os.environ.get(VARIABILE_MCP_HOST, HOST_MCP_DEFAULT)


def porta_mcp_da_ambiente() -> str:
    """Restituisce la porta HTTP MCP come testo per il parsing di argparse."""
    return os.environ.get(VARIABILE_MCP_PORT, str(PORTA_MCP_DEFAULT))


def consenti_bind_non_loopback_da_ambiente() -> bool:
    """True solo se l'apertura non-loopback è richiesta in modo esplicito.

    È il caso dei container, dove il server deve ascoltare su `0.0.0.0` mentre
    la porta viene pubblicata soltanto sul loopback dell'host. Senza questa
    variabile (o con essa falsa) l'interfaccia resta solo loopback.
    """
    return _booleano_env(VARIABILE_MCP_CONSENTI_NON_LOOPBACK)
