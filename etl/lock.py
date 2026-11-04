"""Lock esclusivo dell'ETL, sul volume del database.

Impedisce che due esecuzioni ETL (offerte o PUN) leggano e sostituiscano lo
stesso database insieme. Il lock è un file nella directory del database e usa
`flock`: viene rilasciato anche se il processo termina per errore o segnale.

Nessun caso d'uso dal server MCP: il lock serve solo a chi scrive.
"""

from __future__ import annotations

import errno
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

#: Nome del file di lock, nella directory del database attivo.
NOME_LOCK = "etl.lock"


class ETLInCorso(Exception):
    """Un'altra esecuzione ETL tiene già il lock."""


@contextmanager
def blocco_etl(percorso_db: str | Path) -> Iterator[Path]:
    """Acquisisce il lock esclusivo non bloccante e lo rilascia sempre.

    Il file di lock vive accanto al database, quindi sullo stesso volume
    persistente: due container vedono lo stesso file. Se il lock è già tenuto,
    solleva `ETLInCorso` senza aspettare.
    """
    file_lock = Path(percorso_db).parent / NOME_LOCK
    file_lock.parent.mkdir(parents=True, exist_ok=True)
    descrittore = file_lock.open("a+")
    try:
        try:
            fcntl.flock(descrittore.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise ETLInCorso(f"lock ETL già acquisito: {file_lock.name}") from exc
            raise
        try:
            yield file_lock
        finally:
            fcntl.flock(descrittore.fileno(), fcntl.LOCK_UN)
    finally:
        descrittore.close()
