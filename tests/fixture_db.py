"""Piccoli database SQLite temporanei per i test, con lo schema reale.

Nessun dato reale e nessun XML: poche righe costruite a mano, solo i campi
necessari a coprire la ricerca. Le zone geografiche sono scritte con gli stessi
percorsi che produce l'ETL in `extra_json`, con valori singoli o ripetuti.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_SQL = Path(__file__).resolve().parent.parent / "etl" / "schema.sql"

COLONNE = (
    "piva",
    "cod_offerta",
    "nome",
    "descrizione",
    "tipo_mercato",
    "offerta_singola",
    "tipo_cliente",
    "tipo_offerta",
    "tipologia_att_contr",
    "durata",
    "garanzie",
    "idx_prezzo_energia",
    "data_inizio",
    "data_fine",
    "modalita_pagamento",
    "tipo_dispacciamento",
    "url_sito",
    "url_offerta",
    "telefono",
    "extra_json",
    "snapshot_date",
)

PREFISSO_ZONA = "offerta/ZoneOfferta/"


def zone_a_extra(zone: dict[str, str | list[str]]) -> str | None:
    """Trasforma `{"REGIONE": "Lombardia"}` nel JSON dell'ETL."""
    if not zone:
        return None
    extra = {f"{PREFISSO_ZONA}{chiave}": valore for chiave, valore in zone.items()}
    return json.dumps(extra, ensure_ascii=False, sort_keys=True)


def offerta(
    piva: str,
    cod_offerta: str,
    *,
    nome: str | None = None,
    descrizione: str | None = None,
    tipo_cliente: str = "01",
    tipo_offerta: str = "02",
    idx_prezzo_energia: str | None = "PUN_MENSILE",
    data_inizio: str = "2026-01-01T00:00:00+01:00",
    data_fine: str | None = "2026-12-31T23:59:59+01:00",
    zone: dict[str, str | list[str]] | None = None,
    snapshot_date: str = "2026-10-14",
) -> dict[str, Any]:
    """Una riga di `offerta` pronta per l'inserimento."""
    riga: dict[str, Any] = dict.fromkeys(COLONNE)
    riga.update(
        piva=piva,
        cod_offerta=cod_offerta,
        nome=nome if nome is not None else f"Offerta {cod_offerta}",
        descrizione=descrizione,
        tipo_mercato="01",
        tipo_cliente=tipo_cliente,
        tipo_offerta=tipo_offerta,
        idx_prezzo_energia=idx_prezzo_energia,
        data_inizio=data_inizio,
        data_fine=data_fine,
        extra_json=zone_a_extra(zone or {}),
        snapshot_date=snapshot_date,
    )
    return riga


def crea_db(percorso: Path, offerte: list[dict[str, Any]] | None = None) -> Path:
    """Crea un database temporaneo con lo schema reale e le offerte indicate."""
    conn = sqlite3.connect(percorso)
    try:
        conn.executescript(SCHEMA_SQL.read_text(encoding="utf-8"))
        for riga in offerte or []:
            valori = [riga.get(colonna) for colonna in COLONNE]
            segnaposti = ", ".join(["?"] * len(COLONNE))
            conn.execute(
                f"INSERT INTO offerta ({', '.join(COLONNE)}) VALUES ({segnaposti})",
                valori,
            )
        conn.commit()
    finally:
        conn.close()
    return percorso


def scrivi_etl_run(percorso: Path, fine: str) -> None:
    """Registra un'esecuzione ETL riuscita (per la data del dato)."""
    conn = sqlite3.connect(percorso)
    try:
        conn.execute(
            "INSERT INTO etl_run (inizio, fine, esito, sorgente, sha256, n_offerte,"
            " percorsi_sconosciuti, note) VALUES (?, ?, 'ok', 'test', 'x', 0, 0, NULL)",
            (fine, fine),
        )
        conn.commit()
    finally:
        conn.close()
