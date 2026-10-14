"""Accesso al database SQLite.

L'ETL scrive; le interfacce (CLI, MCP) apriranno il DB in sola lettura con
`apri_db_lettura` (fase 4/5). Nessuna funzione qui accetta SQL libero.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")


def applica_schema(conn: sqlite3.Connection) -> None:
    """Crea le tabelle mancanti. Idempotente."""
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))


def apri_db(percorso: str | Path) -> sqlite3.Connection:
    """Apre (creando se serve) il DB di scrittura con lo schema applicato."""
    percorso = Path(percorso)
    percorso.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(percorso)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    applica_schema(conn)
    conn.commit()
    return conn
