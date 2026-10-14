-- Schema del database delle offerte (docs/architettura.md §6).
-- Formato "long": fasce F1/F2/F3 e quote fisse sono righe di `componente`.
-- I CHECK non ripetono i domini di `codifica`: il parser è tollerante e un
-- codice non previsto non deve far fallire il caricamento.

PRAGMA foreign_keys = ON;

-- Un'offerta per (venditore, codice offerta). `extra_json` raccoglie i percorsi
-- XML noti ma senza colonna dedicata e gli elementi non previsti.
CREATE TABLE IF NOT EXISTS offerta (
    piva                 TEXT NOT NULL,
    cod_offerta          TEXT NOT NULL,
    nome                 TEXT,
    descrizione          TEXT,
    tipo_mercato         TEXT,
    offerta_singola      TEXT,
    tipo_cliente         TEXT,
    tipo_offerta         TEXT,
    tipologia_att_contr  TEXT,
    durata               TEXT,
    garanzie             TEXT,
    idx_prezzo_energia   TEXT,
    data_inizio          TEXT,   -- ISO 8601, fuso Europe/Rome
    data_fine            TEXT,   -- ISO 8601, fuso Europe/Rome
    modalita_pagamento   TEXT,
    tipo_dispacciamento  TEXT,
    url_sito             TEXT,
    url_offerta          TEXT,
    telefono             TEXT,
    extra_json           TEXT,
    snapshot_date        TEXT NOT NULL,
    PRIMARY KEY (piva, cod_offerta),
    CHECK (extra_json IS NULL OR json_valid(extra_json)),
    CHECK (data_inizio IS NULL OR data_inizio LIKE '____-__-__T%'),
    CHECK (data_fine IS NULL OR data_fine LIKE '____-__-__T%')
);

-- Componenti di prezzo: una riga per fascia, più le quote fisse.
CREATE TABLE IF NOT EXISTS componente (
    piva          TEXT NOT NULL,
    cod_offerta   TEXT NOT NULL,
    nome          TEXT,
    descrizione   TEXT,
    tipologia     TEXT,
    macroarea     TEXT,
    fascia        TEXT,
    prezzo        REAL,
    unita_misura  TEXT,
    extra_json    TEXT,
    FOREIGN KEY (piva, cod_offerta) REFERENCES offerta (piva, cod_offerta)
        ON DELETE CASCADE,
    CHECK (extra_json IS NULL OR json_valid(extra_json))
);

CREATE INDEX IF NOT EXISTS idx_componente_offerta
    ON componente (piva, cod_offerta);

-- Condizioni contrattuali (recesso, oneri, attivazione…).
CREATE TABLE IF NOT EXISTS condizione (
    piva         TEXT NOT NULL,
    cod_offerta  TEXT NOT NULL,
    tipologia    TEXT,
    descrizione  TEXT,
    limitante    TEXT,
    FOREIGN KEY (piva, cod_offerta) REFERENCES offerta (piva, cod_offerta)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_condizione_offerta
    ON condizione (piva, cod_offerta);

-- Tabelle di decodifica dei codici del tracciato (dominio → codice → descrizione).
CREATE TABLE IF NOT EXISTS codifica (
    dominio     TEXT NOT NULL,
    codice      TEXT NOT NULL,
    descrizione TEXT NOT NULL,
    PRIMARY KEY (dominio, codice)
);

-- Parametri regolati dal CSV PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv.
-- `riferimento` è la data nel nome del file.
CREATE TABLE IF NOT EXISTS parametro (
    nome        TEXT NOT NULL,
    valore      TEXT,
    descrizione TEXT,
    riferimento TEXT NOT NULL,
    PRIMARY KEY (nome, riferimento)
);

-- Metadati dei parametri (unità, categoria cliente, BTA), dalla documentazione
-- ufficiale: non si derivano dai nomi.
CREATE TABLE IF NOT EXISTS parametro_meta (
    nome             TEXT NOT NULL PRIMARY KEY,
    unita            TEXT,
    categoria_cliente TEXT,
    tipologia_bta    TEXT,
    tipo             TEXT
);

-- PUN giornaliero. `serie` dice quale serie è stata salvata.
CREATE TABLE IF NOT EXISTS pun (
    data            TEXT NOT NULL,   -- ISO 8601, giorno
    valore_eur_mwh  REAL,
    serie           TEXT NOT NULL,
    PRIMARY KEY (data, serie)
);

-- Registro delle esecuzioni dell'ETL.
CREATE TABLE IF NOT EXISTS etl_run (
    id                   INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    inizio               TEXT,
    fine                 TEXT,
    esito                TEXT,
    sorgente             TEXT,
    sha256               TEXT,
    n_offerte            INTEGER,
    percorsi_sconosciuti INTEGER,
    note                 TEXT
);
