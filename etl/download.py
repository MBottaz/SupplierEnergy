"""Download condizionale dei file grezzi (docs/architettura.md §8).

Regole:

- solo HTTPS e solo host in allowlist;
- timeout, tetto sui byte e temp dir: il file finisce in
  `raw/AAAA-MM-GG/` solo se il download è completo;
- condizionale: `ETag`/`Last-Modified` (304 = niente da fare) e confronto dello
  SHA-256 con quello dell'esecuzione precedente;
- niente mezzi file: si scrive su `.tmp` e si rinomina alla fine.
"""

from __future__ import annotations

import hashlib
import http.client
import shutil
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from etl.tempo import oggi

#: Host da cui l'ETL può scaricare. Nessun altro, nemmeno per reindirizzamenti
#: verso altri domini (il controllo è sull'URL richiesto).
HOST_AMMESSI = frozenset({"www.ilportaleofferte.it"})

MAX_BYTE = 100 * 1024 * 1024
TIMEOUT_SECONDI = 60.0
DIMENSIONE_PEZZO = 64 * 1024
GIORNI_RAW = 90


class UrlNonAmmesso(ValueError):
    """URL non HTTPS o host fuori allowlist."""


class DownloadTroppoGrande(ValueError):
    """Il file supera `max_byte`."""


class DownloadFallito(OSError):
    """Errore di rete, risposta HTTP inattesa o scaricamento interrotto."""


@dataclass(frozen=True)
class EsitoDownload:
    """Esito di un download. `percorso` è `None` se non c'era nulla da fare."""

    percorso: Path | None
    sha256: str | None
    etag: str | None
    ultima_modifica: str | None
    byte: int = 0

    @property
    def non_modificato(self) -> bool:
        """True se il raw non è stato (ri)scritto."""
        return self.percorso is None


def controllo_url(url: str) -> None:
    """Accetta solo HTTPS verso gli host in allowlist."""
    parti = urlsplit(url)
    if parti.scheme != "https":
        raise UrlNonAmmesso(f"schema non ammesso: {parti.scheme or 'assente'!r}")
    host = (parti.hostname or "").lower()
    if host not in HOST_AMMESSI:
        raise UrlNonAmmesso(f"host non ammesso: {host!r}")


def scarica(
    url: str,
    *,
    cartella_raw: str | Path,
    giorno: str | None = None,
    etag: str | None = None,
    ultima_modifica: str | None = None,
    sha256_atteso: str | None = None,
    apri: Callable[..., AbstractContextManager[Any]] | None = None,
    max_byte: int = MAX_BYTE,
    timeout: float = TIMEOUT_SECONDI,
    dimensione_pezzo: int = DIMENSIONE_PEZZO,
) -> EsitoDownload:
    """Scarica `url` in `cartella_raw/AAAA-MM-GG/`, se serve."""
    controllo_url(url)
    giorno = giorno or oggi()
    apri_rete = apri or _apri_predefinito
    richiesta = Request(url, headers=_intestazioni(etag, ultima_modifica), method="GET")

    try:
        risposta = apri_rete(richiesta, timeout=timeout)
    except HTTPError as errore:
        if errore.code == 304:
            return EsitoDownload(
                percorso=None,
                sha256=None,
                etag=etag,
                ultima_modifica=ultima_modifica,
            )
        raise DownloadFallito(f"risposta HTTP {errore.code}") from errore
    except (URLError, TimeoutError) as errore:
        raise DownloadFallito("richiesta non riuscita") from errore

    with risposta:
        intestazioni = getattr(risposta, "headers", None)
        etag_risposta = _intestazione(intestazioni, "ETag") or etag
        ultima_risposta = _intestazione(intestazioni, "Last-Modified") or ultima_modifica
        dichiarati = _intero(_intestazione(intestazioni, "Content-Length"))
        if dichiarati is not None and dichiarati > max_byte:
            raise DownloadTroppoGrande(f"dichiarati {dichiarati} byte, tetto {max_byte}")

        cartella = Path(cartella_raw) / giorno
        cartella.mkdir(parents=True, exist_ok=True)
        nome = _nome_file(url)
        temporaneo = cartella / f"{nome}.tmp"
        sha, byte = _copia(risposta, temporaneo, max_byte, dimensione_pezzo)

        if sha256_atteso is not None and sha == sha256_atteso:
            temporaneo.unlink(missing_ok=True)
            return EsitoDownload(
                percorso=None,
                sha256=sha,
                etag=etag_risposta,
                ultima_modifica=ultima_risposta,
                byte=byte,
            )

        definitivo = cartella / nome
        temporaneo.replace(definitivo)
        return EsitoDownload(
            percorso=definitivo,
            sha256=sha,
            etag=etag_risposta,
            ultima_modifica=ultima_risposta,
            byte=byte,
        )


def pulisci_vecchi(cartella_raw: str | Path, *, oggi: str, giorni: int = GIORNI_RAW) -> int:
    """Rimuove le cartelle raw più vecchie di `giorni`. Ritorna quante ne ha tolte."""
    limite = date.fromisoformat(oggi) - timedelta(days=giorni)
    radice = Path(cartella_raw)
    if not radice.is_dir():
        return 0
    rimosse = 0
    for voce in radice.iterdir():
        if not voce.is_dir():
            continue
        try:
            giorno_voce = date.fromisoformat(voce.name)
        except ValueError:
            continue
        if giorno_voce < limite:
            shutil.rmtree(voce)
            rimosse += 1
    return rimosse


def _copia(
    risposta: Any,
    temporaneo: Path,
    max_byte: int,
    dimensione_pezzo: int,
) -> tuple[str, int]:
    """Copia la risposta sul file temporaneo, calcolando lo SHA-256."""
    sha = hashlib.sha256()
    byte = 0
    try:
        with temporaneo.open("wb") as flusso:
            while True:
                try:
                    pezzo = risposta.read(dimensione_pezzo)
                except http.client.IncompleteRead as errore:
                    raise DownloadFallito("scaricamento interrotto") from errore
                if not pezzo:
                    break
                byte += len(pezzo)
                if byte > max_byte:
                    raise DownloadTroppoGrande(f"scaricati più di {max_byte} byte")
                sha.update(pezzo)
                _scrivi(flusso, pezzo)
    except (OSError, DownloadTroppoGrande):
        temporaneo.unlink(missing_ok=True)
        raise
    return sha.hexdigest(), byte


def _scrivi(flusso: BinaryIO, pezzo: bytes) -> None:
    flusso.write(pezzo)


def _intestazioni(etag: str | None, ultima_modifica: str | None) -> dict[str, str]:
    intestazioni: dict[str, str] = {}
    if etag:
        intestazioni["If-None-Match"] = etag
    if ultima_modifica:
        intestazioni["If-Modified-Since"] = ultima_modifica
    return intestazioni


def _intestazione(intestazioni: Any, nome: str) -> str | None:
    if intestazioni is None:
        return None
    try:
        valore = intestazioni.get(nome)
    except AttributeError:
        return None
    return valore.strip() if isinstance(valore, str) and valore.strip() else None


def _intero(valore: str | None) -> int | None:
    if valore is None:
        return None
    try:
        return int(valore)
    except ValueError:
        return None


def _nome_file(url: str) -> str:
    grezzo = Path(urlsplit(url).path).name or "download"
    ripulito = "".join(
        carattere for carattere in grezzo if carattere.isalnum() or carattere in "._-"
    )
    return ripulito or "download"


def _apri_predefinito(richiesta: Request, timeout: float | None = None) -> Any:
    # Solo HTTPS e host in allowlist: il controllo è in `controllo_url`.
    return urlopen(richiesta, timeout=timeout)
