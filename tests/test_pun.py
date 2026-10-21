"""PUN mensile: lettura del CSV dei prezzi storici, caricamento idempotente."""

from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from etl.db import apri_db
from etl.pun import (
    SERIE,
    EsitoPun,
    carica_pun,
    leggi_pun,
    nome_file_raw,
    righe_del_db,
    serie_mensile,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pun_storico_estratto.csv"


def _scrivi(percorso: Path, contenuto: str, *, codifica: str = "cp1252") -> Path:
    percorso.write_text(contenuto, encoding=codifica, newline="")
    return percorso


def test_legge_la_fixture_in_eur_mwh() -> None:
    lettura = leggi_pun(FIXTURE)
    assert [riga.data for riga in lettura.righe] == [
        "2020-01-01",
        "2020-02-01",
        "2022-08-01",
        "2022-10-01",
    ]
    assert [riga.valore_eur_mwh for riga in lettura.righe] == [
        Decimal("47.470"),
        Decimal("39.300"),
        Decimal("543.154"),
        Decimal("211.500"),
    ]
    assert {riga.serie for riga in lettura.righe} == {SERIE}
    assert lettura.n_scartate == 1


def test_legge_unita_eur_mwh(tmp_path: Path) -> None:
    percorso = _scrivi(
        tmp_path / "pun.csv",
        "AnnoMese;PUN (EUR/MWh)\r\n202001;47,47\r\n",
    )
    lettura = leggi_pun(percorso)
    assert lettura.righe[0].valore_eur_mwh == Decimal("47.47")


def test_unita_assente_e_unita_ignota(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unità di misura assente"):
        leggi_pun(_scrivi(tmp_path / "a.csv", "AnnoMese;PUN\r\n202001;0,1\r\n"))
    with pytest.raises(ValueError, match="unità di misura non prevista"):
        leggi_pun(_scrivi(tmp_path / "b.csv", "AnnoMese;PUN (€/Smc)\r\n202001;0,1\r\n"))


def test_periodo_malformato_duplicato_o_colonne_mancanti(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="periodo non valido"):
        leggi_pun(_scrivi(tmp_path / "a.csv", "AnnoMese;PUN (€/kWh)\r\n20201;0,1\r\n"))
    with pytest.raises(ValueError, match="periodo non valido"):
        leggi_pun(_scrivi(tmp_path / "b.csv", "AnnoMese;PUN (€/kWh)\r\n202013;0,1\r\n"))
    with pytest.raises(ValueError, match="periodo duplicato"):
        leggi_pun(
            _scrivi(
                tmp_path / "c.csv",
                "AnnoMese;PUN (€/kWh)\r\n202001;0,1\r\n202001;0,2\r\n",
            )
        )
    with pytest.raises(ValueError, match="colonne `pun` trovate: 0"):
        leggi_pun(_scrivi(tmp_path / "d.csv", "AnnoMese;PSV (€/Smc)\r\n202001;0,1\r\n"))
    with pytest.raises(ValueError, match="colonne `annomese` trovate: 0"):
        leggi_pun(_scrivi(tmp_path / "e.csv", "Mese;PUN (€/kWh)\r\n202001;0,1\r\n"))
    with pytest.raises(ValueError, match="colonne `pun` trovate: 2"):
        leggi_pun(
            _scrivi(
                tmp_path / "f.csv",
                "AnnoMese;PUN (€/kWh);PUN (€/MWh)\r\n202001;0,1;100\r\n",
            )
        )
    with pytest.raises(ValueError, match="file dei prezzi storici vuoto"):
        leggi_pun(_scrivi(tmp_path / "g.csv", ""))


def test_numero_non_valido(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="formato numerico non atteso"):
        leggi_pun(_scrivi(tmp_path / "a.csv", "AnnoMese;PUN (€/kWh)\r\n202001;1.2,3\r\n"))
    with pytest.raises(ValueError, match="formato numerico non atteso"):
        leggi_pun(_scrivi(tmp_path / "b.csv", "AnnoMese;PUN (€/kWh)\r\n202001;abc\r\n"))


def test_colonne_in_surpiu_e_righe_vuote_ignorate(tmp_path: Path) -> None:
    percorso = _scrivi(
        tmp_path / "a.csv",
        "AnnoMese;PUN (€/kWh);PSV (€/Smc)\r\n202001;0,047;\r\n\r\n202002;0,03;0,1\r\n",
    )
    lettura = leggi_pun(percorso)
    assert [riga.data for riga in lettura.righe] == ["2020-01-01", "2020-02-01"]
    assert lettura.n_scartate == 0


def test_caricamento_idempotente_e_aggiornamento(tmp_path: Path) -> None:
    conn = apri_db(tmp_path / "offerte.db")
    try:
        primo = carica_pun(conn, FIXTURE)
        assert primo == EsitoPun(
            n_righe=4,
            n_scartate=1,
            serie=SERIE,
            prima="2020-01-01",
            ultima="2022-10-01",
        )
        carica_pun(conn, FIXTURE)
        assert conn.execute("SELECT count(*) FROM pun").fetchone()[0] == 4

        rivisto = _scrivi(
            tmp_path / "rivisto.csv",
            "AnnoMese;PUN (€/kWh)\r\n202210;0,999\r\n",
        )
        carica_pun(conn, rivisto)
        assert conn.execute("SELECT count(*) FROM pun").fetchone()[0] == 4
        valore = conn.execute(
            "SELECT valore_eur_mwh FROM pun WHERE data = '2022-10-01' AND serie = ?", (SERIE,)
        ).fetchone()[0]
        assert valore == pytest.approx(999.0)
    finally:
        conn.close()


def test_caricamento_si_accumula_a_un_altra_serie(tmp_path: Path) -> None:
    conn = apri_db(tmp_path / "offerte.db")
    try:
        carica_pun(conn, FIXTURE)
        with conn:
            conn.execute(
                "INSERT INTO pun (data, valore_eur_mwh, serie) VALUES ('2022-10-01', 1.0, ?)",
                ("PUN_GIORNALIERO",),
            )
        assert [riga[0] for riga in righe_del_db(conn)] == [
            "2020-01-01",
            "2020-02-01",
            "2022-08-01",
            "2022-10-01",
        ]
        assert list(righe_del_db(conn, "PUN_GIORNALIERO")) == [("2022-10-01", 1.0)]
    finally:
        conn.close()


def test_serie_mensile_e_nome_file_raw() -> None:
    assert serie_mensile("PUN_MENSILE")
    assert not serie_mensile("PUN_GIORNALIERO")
    assert nome_file_raw("2026-10-21") == "PO_Prezzi_Storici_20261021.csv"


def test_leggi_pun_non_modifica_il_db(tmp_path: Path) -> None:
    conn = apri_db(tmp_path / "offerte.db")
    try:
        leggi_pun(FIXTURE)
        assert conn.execute("SELECT count(*) FROM pun").fetchone()[0] == 0
    finally:
        conn.close()


def test_tabelle_del_db_intatte_dopo_il_caricamento(tmp_path: Path) -> None:
    conn = apri_db(tmp_path / "offerte.db")
    try:
        carica_pun(conn, FIXTURE)
        riga = conn.execute("PRAGMA integrity_check").fetchone()
        assert riga[0] == "ok"
    finally:
        conn.close()


def test_pun_mensile_assente_da_avviso(tmp_path: Path) -> None:
    conn: sqlite3.Connection = apri_db(tmp_path / "offerte.db")
    try:
        carica_pun(conn, FIXTURE)
        conn.execute("DELETE FROM pun WHERE data > '2022-08-01'")
        conn.commit()
        assert "PUN_MENSILE fermo al 2022-08-01" in (_nota(conn, "2026-10-21") or "")
        assert _nota(conn, "2022-09-05") is None
    finally:
        conn.close()


def _nota(conn: sqlite3.Connection, giorno: str) -> str | None:
    from etl.esegui import _nota_pun

    return _nota_pun(conn, giorno=giorno)
