# Comandi di sviluppo. `just check` è il comando unico di verifica.
set shell := ["bash", "-uc"]

default: check

# Solo i test.
test:
    uv run pytest

# Lint statico.
lint:
    uv run ruff check .

# Formattazione del codice.
format:
    uv run ruff format .

# Formattazione (verifica, non modifica).
format-check:
    uv run ruff format --check .

# Controllo dei tipi.
types:
    uv run mypy

# Carica la fixture nella directory di build (verifica end-to-end dell'ETL).
etl-fixture:
    uv run python -m etl locale --db build/offerte.db \
        --raw tests/fixtures/offerta_estratto.xml \
        --parametri tests/fixtures/PO_Parametri_Mercato_Libero_E_20261014.csv \
        --snapshot 2026-10-14

# Carica i dati reali dal raw locale (XML completo + CSV dei parametri).
etl-reale:
    uv run python -m etl locale --db build/offerte.db \
        --raw raw/2026-10-14/PO_Offerte_E_MLIBERO_20261014.xml \
        --parametri docs/PO_Parametri_Mercato_Libero_E_20261014.csv \
        --snapshot 2026-10-14

# Scarica l'XML open data del giorno e carica il DB (usa la rete).
etl-scarica:
    uv run python -m etl scarica --db build/offerte.db \
        --raw-dir raw \
        --parametri docs/PO_Parametri_Mercato_Libero_E_20261014.csv

# Scarica il file "Prezzi storici" e aggiorna il PUN mensile nel DB (usa la rete).
etl-pun:
    uv run python -m etl pun --db build/offerte.db --raw-dir raw

# Carica il PUN mensile da un CSV locale: just etl-pun-file PERCORSO.
etl-pun-file FILE:
    uv run python -m etl pun --db build/offerte.db --file "{{FILE}}"

# Lint + tipi + test.
check: lint format-check types test
