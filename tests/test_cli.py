"""CLI dell'ETL: `python -m etl locale` e `python -m etl scarica`."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from http.client import HTTPMessage
from pathlib import Path
from urllib.request import Request

import pytest

from etl.__main__ import main

FIXTURE = Path(__file__).parent / "fixtures" / "offerta_estratto.xml"
CSV = Path(__file__).parent / "fixtures" / "PO_Parametri_Mercato_Libero_E_20261014.csv"
URL = (
    "https://www.ilportaleofferte.it/portaleOfferte/resources/opendata/csv/offerteML/"
    "2026_10/PO_Offerte_E_MLIBERO_20261014.xml"
)


class RispostaFinta:
    def __init__(self, contenuto: bytes) -> None:
        self._contenuto = contenuto
        self._posizione = 0
        self.headers = HTTPMessage()

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


def rete_finta(contenuto: bytes) -> Callable[..., AbstractContextManager[RispostaFinta]]:
    def apri(_richiesta: Request, timeout: float | None = None) -> RispostaFinta:
        return RispostaFinta(contenuto)

    return apri


def _output(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    contenuto: dict[str, object] = json.loads(capsys.readouterr().out)
    return contenuto


def test_locale_carica_la_fixture(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "offerte.db"
    assert main(["locale", "--db", str(db), "--raw", str(FIXTURE)]) == 0

    esito = _output(capsys)
    assert esito["esito"] == "ok"
    assert esito["n_offerte"] == 1
    assert esito["percorsi_sconosciuti"] == []
    assert db.is_file()

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM offerta").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM componente").fetchone() == (4,)
        assert conn.execute("SELECT count(*) FROM condizione").fetchone() == (1,)


def test_locale_con_parametri_e_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "offerte.db"
    assert (
        main(
            [
                "locale",
                "--db",
                str(db),
                "--raw",
                str(FIXTURE),
                "--parametri",
                str(CSV),
                "--snapshot",
                "2026-10-14",
            ]
        )
        == 0
    )
    esito = _output(capsys)
    assert esito["snapshot_date"] == "2026-10-14"
    assert esito["n_parametri"] == 6
    assert esito["note"] == []


def test_locale_xml_non_valido(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rotto = tmp_path / "rotto.xml"
    rotto.write_text(FIXTURE.read_text(encoding="utf-8")[:200], encoding="utf-8")
    db = tmp_path / "offerte.db"

    assert main(["locale", "--db", str(db), "--raw", str(rotto)]) == 1

    catturato = capsys.readouterr()
    errore = json.loads(catturato.err)
    assert errore["esito"] == "errore"
    assert errore["codice"] == "xml_non_valido"
    assert errore["messaggio"]
    assert "Traceback" not in catturato.err
    assert str(tmp_path) not in catturato.err
    assert catturato.out == ""
    assert not db.exists()


def test_locale_file_inesistente(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["locale", "--db", str(tmp_path / "offerte.db"), "--raw", "/tmp/manco.xml"]) == 1
    assert json.loads(capsys.readouterr().err)["codice"] == "file_non_leggibile"


def test_locale_parametri_obbligatori_mancanti(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    parziale = tmp_path / "PO_Parametri_Mercato_Libero_E_20261014.csv"
    parziale.write_text("nome_parametro,valore,descrizione\npcv_a,23.04,Quota fissa\n")

    assert (
        main(
            [
                "locale",
                "--db",
                str(tmp_path / "offerte.db"),
                "--raw",
                str(FIXTURE),
                "--parametri",
                str(parziale),
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().err)["codice"] == "parametri_mancanti"


def test_scarica_salva_il_raw_e_carica(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "offerte.db"
    raw = tmp_path / "raw"
    contenuto = FIXTURE.read_bytes()

    assert (
        main(
            [
                "scarica",
                "--db",
                str(db),
                "--raw-dir",
                str(raw),
                "--url",
                URL,
                "--parametri",
                str(CSV),
                "--snapshot",
                "2026-10-14",
            ],
            apri=rete_finta(contenuto),
        )
        == 0
    )

    esito = _output(capsys)
    assert esito["esito"] == "ok"
    assert esito["n_offerte"] == 1
    assert esito["sha256"] == hashlib.sha256(contenuto).hexdigest()
    assert (raw / "2026-10-14" / "PO_Offerte_E_MLIBERO_20261014.xml").read_bytes() == contenuto


def test_scarica_non_fa_nulla_se_lo_sha_non_cambia(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "offerte.db"
    raw = tmp_path / "raw"
    contenuto = FIXTURE.read_bytes()
    argomenti = [
        "scarica",
        "--db",
        str(db),
        "--raw-dir",
        str(raw),
        "--url",
        URL,
        "--parametri",
        str(CSV),
        "--snapshot",
        "2026-10-14",
    ]
    assert main(argomenti, apri=rete_finta(contenuto)) == 0
    capsys.readouterr()

    assert main(argomenti, apri=rete_finta(contenuto)) == 0
    esito = _output(capsys)
    assert esito["esito"] == "non_modificato"
    assert esito["sha256"] == hashlib.sha256(contenuto).hexdigest()

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM etl_run").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM offerta").fetchone() == (1,)


def test_scarica_url_non_ammesso(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "scarica",
                "--db",
                str(tmp_path / "offerte.db"),
                "--raw-dir",
                str(tmp_path / "raw"),
                "--url",
                "https://example.com/opendata.xml",
            ],
            apri=rete_finta(b"x"),
        )
        == 1
    )
    errore = json.loads(capsys.readouterr().err)
    assert errore["codice"] == "url_non_ammesso"
