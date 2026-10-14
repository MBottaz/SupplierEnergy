# Comandi di sviluppo. `just check` è il comando unico di verifica.
set shell := ["bash", "-uc"]

default: check

# Solo i test.
test:
    uv run pytest

# Lint statico.
lint:
    uv run ruff check .

# Formattazione (verifica, non modifica).
format-check:
    uv run ruff format --check .

# Controllo dei tipi.
types:
    uv run mypy

# Carica la fixture nella directory di build (verifica end-to-end dell'ETL).
etl-fixture:
    uv run python -m etl --db build/offerte.db tests/fixtures/offerta_estratto.xml

# Lint + tipi + test.
check: lint format-check types test
