"""Download condizionale: allowlist, limiti, sha256, raw datati."""

from __future__ import annotations

import hashlib
import http.client
from collections.abc import Callable
from contextlib import AbstractContextManager
from http.client import HTTPMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from etl.download import (
    DownloadFallito,
    DownloadTroppoGrande,
    EsitoDownload,
    UrlNonAmmesso,
    controllo_url,
    pulisci_vecchi,
    scarica,
)

URL = "https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv/offerteML/2026_10/PO_Offerte_E_MLIBERO_20261014.xml"
CONTENUTO = b"<ListaOfferteMercatoLibero/>"
GIORNO = "2026-10-14"


class RispostaFinta:
    """Risposta HTTP finta: solo quello che serve al download."""

    def __init__(self, contenuto: bytes, intestazioni: dict[str, str] | None = None) -> None:
        self._contenuto = contenuto
        self._posizione = 0
        self.headers = HTTPMessage()
        for chiave, valore in (intestazioni or {}).items():
            self.headers[chiave] = valore

    def read(self, quanti: int = -1) -> bytes:
        if quanti is None or quanti < 0:
            quanti = len(self._contenuto) - self._posizione
        pezzo = self._contenuto[self._posizione : self._posizione + quanti]
        self._posizione += len(pezzo)
        return pezzo

    def __enter__(self) -> RispostaFinta:
        return self

    def __exit__(self, *_scarti: object) -> None:
        return None


def _apri_con(
    risposta: RispostaFinta | None = None, errore: Exception | None = None
) -> tuple[Callable[..., AbstractContextManager[RispostaFinta]], list[Request]]:
    richieste: list[Request] = []

    def finto_apri(request: Request, timeout: float | None = None) -> RispostaFinta:
        richieste.append(request)
        if errore is not None:
            raise errore
        assert risposta is not None
        return risposta

    return finto_apri, richieste


def _file_scaricati(radice: Path) -> list[Path]:
    """I file presenti sotto `radice` (le cartelle vuote non contano)."""
    return [percorso for percorso in radice.rglob("*") if percorso.is_file()]


def test_url_ammesso() -> None:
    controllo_url(URL)
    with pytest.raises(UrlNonAmmesso):
        controllo_url("http://www.ilportaleofferte.it/opendata.xml")
    with pytest.raises(UrlNonAmmesso):
        controllo_url("https://example.com/opendata.xml")
    with pytest.raises(UrlNonAmmesso):
        controllo_url("ftp://www.ilportaleofferte.it/opendata.xml")
    with pytest.raises(UrlNonAmmesso):
        controllo_url("https://www.ilportaleofferte.it.evil.example/opendata.xml")


def test_download_salva_il_raw_datato(tmp_path: Path) -> None:
    apri, _ = _apri_con(RispostaFinta(CONTENUTO, {"ETag": '"abc"', "Last-Modified": "ieri"}))
    esito = scarica(URL, cartella_raw=tmp_path, giorno=GIORNO, apri=apri)

    atteso = tmp_path / GIORNO / "PO_Offerte_E_MLIBERO_20261014.xml"
    assert esito.percorso == atteso
    assert esito.non_modificato is False
    assert esito.sha256 == hashlib.sha256(CONTENUTO).hexdigest()
    assert esito.etag == '"abc"'
    assert esito.ultima_modifica == "ieri"
    assert esito.byte == len(CONTENUTO)
    assert atteso.read_bytes() == CONTENUTO
    assert list(atteso.parent.glob("*.tmp")) == []


def test_download_invia_le_intestazioni_condizionali(tmp_path: Path) -> None:
    apri, richieste = _apri_con(RispostaFinta(CONTENUTO))
    scarica(URL, cartella_raw=tmp_path, giorno=GIORNO, apri=apri)
    assert richieste[0].get_header("If-none-match") is None

    apri, richieste = _apri_con(RispostaFinta(CONTENUTO))
    scarica(
        URL,
        cartella_raw=tmp_path,
        giorno=GIORNO,
        etag='"abc"',
        ultima_modifica="ieri",
        apri=apri,
    )
    assert richieste[0].get_header("If-none-match") == '"abc"'
    assert richieste[0].get_header("If-modified-since") == "ieri"


def test_risposta_304_non_riscarica(tmp_path: Path) -> None:
    apri, _ = _apri_con(errore=HTTPError(URL, 304, "Non modificato", HTTPMessage(), None))
    esito = scarica(URL, cartella_raw=tmp_path, giorno=GIORNO, etag='"abc"', apri=apri)
    assert esito.non_modificato is True
    assert esito.percorso is None
    assert esito.etag == '"abc"'
    assert list(tmp_path.rglob("*")) == []


def test_sha256_uguale_non_sostituisce_il_raw(tmp_path: Path) -> None:
    apri, _ = _apri_con(RispostaFinta(CONTENUTO))
    esito = scarica(
        URL,
        cartella_raw=tmp_path,
        giorno=GIORNO,
        sha256_atteso=hashlib.sha256(CONTENUTO).hexdigest(),
        apri=apri,
    )
    assert esito.non_modificato is True
    assert esito.percorso is None
    assert _file_scaricati(tmp_path) == []


def test_limite_di_dimensione_dall_intestazione(tmp_path: Path) -> None:
    contenuto = b"x" * 100
    apri, _ = _apri_con(RispostaFinta(contenuto, {"Content-Length": "100"}))
    with pytest.raises(DownloadTroppoGrande):
        scarica(URL, cartella_raw=tmp_path, giorno=GIORNO, max_byte=50, apri=apri)
    assert _file_scaricati(tmp_path) == []


def test_limite_di_dimensione_durante_lo_streaming(tmp_path: Path) -> None:
    apri, _ = _apri_con(RispostaFinta(b"x" * 100))
    with pytest.raises(DownloadTroppoGrande):
        scarica(URL, cartella_raw=tmp_path, giorno=GIORNO, max_byte=50, apri=apri)
    assert _file_scaricati(tmp_path) == []


def test_scaricamento_interrotto_non_lascia_mezzi_file(tmp_path: Path) -> None:
    class Rotta(RispostaFinta):
        def read(self, quanti: int = -1) -> bytes:
            raise http.client.IncompleteRead(b"parziale", 100)

    apri, _ = _apri_con(Rotta(b""))
    with pytest.raises(DownloadFallito):
        scarica(URL, cartella_raw=tmp_path, giorno=GIORNO, apri=apri)
    assert _file_scaricati(tmp_path) == []


def test_errore_di_rete(tmp_path: Path) -> None:
    apri, _ = _apri_con(errore=URLError("niente rete"))
    with pytest.raises(DownloadFallito):
        scarica(URL, cartella_raw=tmp_path, giorno=GIORNO, apri=apri)
    assert _file_scaricati(tmp_path) == []


def test_url_non_ammesso_non_viene_scaricato(tmp_path: Path) -> None:
    apri, richieste = _apri_con(RispostaFinta(CONTENUTO))
    with pytest.raises(UrlNonAmmesso):
        scarica("https://example.com/x.xml", cartella_raw=tmp_path, giorno=GIORNO, apri=apri)
    assert richieste == []


def test_pulisci_vecchi(tmp_path: Path) -> None:
    for giorno in ("2026-01-01", "2026-08-01", GIORNO):
        (tmp_path / giorno).mkdir()
    (tmp_path / GIORNO / "x.xml").write_text("x")

    rimosse = pulisci_vecchi(tmp_path, oggi=GIORNO, giorni=90)
    assert rimosse == 1
    assert not (tmp_path / "2026-01-01").exists()
    assert (tmp_path / "2026-08-01").is_dir()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-08-01", GIORNO]


def test_esito_download_e_immutabile() -> None:
    esito = EsitoDownload(percorso=None, sha256=None, etag=None, ultima_modifica=None)
    assert esito.non_modificato is True
    assert esito.byte == 0
