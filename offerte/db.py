"""Accesso in sola lettura al database delle offerte.

Un solo punto di apertura: URI SQLite `mode=ro` più `PRAGMA query_only=ON`.
Nessuna scrittura, migrazione o creazione automatica: se il file non c'è, non è
leggibile o non è un database SQLite valido, si solleva `DatabaseNonDisponibile`
senza toccarlo.

Questo modulo non conosce MCP: la logica di protocollo sta in `offerte.mcp`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from offerte.errori import DatabaseNonDisponibile

#: Percorso di default del database, coerente con le ricette `just` dell'ETL.
NOME_DB_DEFAULT = "build/offerte.db"

_MESSAGGIO_NON_DISPONIBILE = "il database delle offerte non è disponibile in sola lettura"


def _uri_ro(percorso: Path) -> str:
    """URI SQLite di sola lettura, con il percorso codificato per l'URI."""
    return f"file:{quote(str(percorso), safe='/')}?mode=ro"


@contextmanager
def apri_db(percorso: str | Path) -> Iterator[sqlite3.Connection]:
    """Apre il database in sola lettura e lo chiude sempre.

    Il controllo di esistenza anticipa l'errore SQLite per non far trapelare
    percorsi locali nel messaggio; una lettura minima di `sqlite_master`
    verifica che il file sia davvero un database.
    """
    file_db = Path(percorso)
    if not file_db.is_file():
        raise DatabaseNonDisponibile(_MESSAGGIO_NON_DISPONIBILE)

    try:
        conn = sqlite3.connect(_uri_ro(file_db.resolve()), uri=True)
    except sqlite3.Error as exc:  # pragma: no cover - dipende dai permessi
        raise DatabaseNonDisponibile(_MESSAGGIO_NON_DISPONIBILE) from exc

    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.Error as exc:
        conn.close()
        raise DatabaseNonDisponibile(_MESSAGGIO_NON_DISPONIBILE) from exc

    try:
        yield conn
    finally:
        conn.close()
