# EnergySuppliers

Pipeline that downloads the Italian free-market electricity offers, normalizes them into SQLite, and is being built to expose the data read-only to agents.

## How it works

```text
XML/CSV files ──> download ──> streaming parser ──> SQLite database
                                      │
                         validation + atomic database swap
```

The ETL builds `offerte.db.new`, validates it, and replaces the active database only when the checks pass. The previous database is kept as `offerte.db.prev`. The PUN-only update uses the same swap: it copies the active database, updates `pun`, and replaces it only if the copy passes the integrity check. Raw downloads are stored by date under `raw/`.

The XML parser is streaming and hardened against DTD/external entities. Unknown XML paths are preserved in `extra_json` and reported instead of stopping the load. Prices are parsed with `Decimal` and stored in SQLite as `REAL`.

## Repository layout

| Path | Purpose |
| --- | --- |
| `etl/` | Download, XML parsing, CSV parameter loading, PUN loading, schema, validation, and atomic swap. Entry point: `python -m etl`. |
| `etl/schema.sql` | SQLite schema for offers, components, conditions, parameters, decodings, PUN, and ETL runs. |
| `etl/pun.py` | Monthly PUN from the Portale Offerte "Prezzi storici" CSV (`PUN_MENSILE` series); it accumulates across database rebuilds. |
| `offerte/` | Single non-ETL package: read-only query and calculation library, with the CLI, MCP server, and API-key management as submodules (`offerte.cli`, `offerte.mcp`, `offerte.auth`). `offerte.db` is the only read-only database entry point (`mode=ro` plus `PRAGMA query_only=ON`); `offerte.ricerca.cerca_offerte` is the shared application search function; `offerte.mcp` is the MCP server exposing it as the `cerca_offerte` tool with structured errors; transport stdio (default) or local streamable HTTP bound to loopback. |
| `tests/` | Unit and integration tests, including XML security, ETL swap cases, MCP tool discovery, and an MCP stdio integration test with the official client. |
| `docs/` | Architecture, the `cerca_offerte` contract, XML validation, open questions, and the tracked parameter fixture. |
| `build/` | Local generated database files; ignored by Git. |
| `raw/` | Local dated XML downloads; ignored by Git. |

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- [`just`](https://just.systems/) for the project commands

Install the locked environment with:

```bash
uv sync
```

## Run and verify

Run the complete verification suite (lint, formatting, type checking, and tests):

```bash
just check
```

Load the small checked-in fixture into `build/offerte.db`:

```bash
just etl-fixture
```

Load a previously downloaded complete XML and its parameter CSV:

```bash
just etl-reale
```

This expects:

- `raw/2026-10-14/PO_Offerte_E_MLIBERO_20261014.xml`
- `docs/PO_Parametri_Mercato_Libero_E_20261014.csv`

Download the current XML from the allowlisted Portale Offerte host and load it:

```bash
just etl-scarica
```

Update the PUN series without reloading the offers (the command copies the
active database and applies the same atomic swap as the ETL):

```bash
just etl-pun                        # downloads the Portale Offerte CSV
just etl-pun-file path/to/prezzi.csv  # loads a file already downloaded
```

The network command still takes the parameter CSV from `docs/`; check `justfile` before using it with a different snapshot.

The ETL can also be run directly:

```bash
uv run python -m etl locale \
  --db build/offerte.db \
  --raw path/to/offerte.xml \
  --parametri path/to/PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv \
  --snapshot YYYY-MM-DD

uv run python -m etl scarica \
  --db build/offerte.db \
  --raw-dir raw \
  --parametri path/to/PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv

uv run python -m etl pun \
  --db build/offerte.db \
  --raw-dir raw
```

Commands print structured JSON. A failed validation leaves the active database unchanged and returns a non-zero exit code.

## MCP server (read-only)

The server exposes a single tool, `cerca_offerte`, backed by the same search
function (`offerte.ricerca.cerca_offerte`) that the future CLI will use. It opens
the database read-only (`mode=ro` plus `PRAGMA query_only=ON`) and never writes to
it. The database path comes from `--db`, otherwise from `$OFFERTE_DB`, otherwise
`build/offerte.db`.

Local stdio (default), for a host that launches the process itself:

```bash
uv run python -m offerte.mcp --db build/offerte.db
```

Local streamable HTTP on loopback; any non-loopback `--host` is refused:

```bash
uv run python -m offerte.mcp --db build/offerte.db --trasporto http --port 8000
# endpoint: http://127.0.0.1:8000/mcp
```

`cerca_offerte` filters, all optional, are passed inside a `filtri` object:
`fornitore` (exact VAT number; the commercial name is not in the data model),
`regione`, `provincia`, `comune` (case-insensitive exact match on the zones the
offer declares), `tipo_cliente` (`domestico`, `altri usi` or `condominio uso
domestico (gas)`) and `tipo_offerta` (`fisso`, `variabile`, `flat` or `mista`),
`indicizzata`, `testo` (searched in the offer name and description) and `limit`
(1-50, default 20). Seller text is returned in fields marked as untrusted. Input
errors come back as structured results (`{"codice": "...", "messaggio": "..."}`).
The full contract is in `docs/contratto_cerca_offerte.md`.

The checked-in fixture offer expired on 2026-10-10, so with the contract's
default validity filter (`data_fine >= today`) a search on the fixture database
returns no results; it is still useful to smoke-test that the tool starts and
answers. Use real data for a non-empty search.

The MCP tests (tool discovery, in-memory calls, stdio integration, loopback HTTP)
run as part of:

```bash
just test
```

Out of scope for now: authentication/API keys, cost calculation, extra tools
(`confronta_offerte`, `dettaglio_offerta`, `pun`, `decodifica`, `stato_dati`),
and deployment (Cloudflare Tunnel, systemd). The HTTP transport is meant for
local use only: do not expose it beyond loopback.

## Current scope

The implemented scope is the ETL (offers, parameters, and the monthly PUN series), its validation on the fixture and real XML summary, the read-only database access layer, the shared `cerca_offerte` search function (filters, limits, stable ordering, structured errors), and the MCP server (`mcp==2.3.0`, official Python SDK v2 line) on stdio or local loopback HTTP, exposing `cerca_offerte` with structured errors while keeping the database read-only. The CLI, cost calculation, authentication, and deployment units are planned work, not runnable features yet; the daily PUN series (GME) is out of scope for now.

Read `docs/architettura.md` for the design and data model, `docs/contratto_cerca_offerte.md` for the `cerca_offerte` contract, `PROMPT.md` for the planned phases, `docs/validazione_xml.md` for the aggregate validation of the real XML, and `docs/questioni_aperte.md` for unresolved source and calculation questions.
