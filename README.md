# EnergySuppliers

Pipeline that downloads the Italian free-market electricity offers (XML), the regulated parameters (CSV) and the PUN, normalizes them into a single SQLite database, and exposes the data read-only to AI agents through the MCP server only. A CLI, if any, is a local debug adapter and never an agent entry point.

## How it works

```text
XML/CSV files ──> download ──> streaming parser ──> SQLite database
                                      │
                         validation + atomic database swap
```

The ETL builds `offerte.db.new`, validates it, and replaces the active database only when the checks pass. The previous database is kept as `offerte.db.prev` in the same directory. The PUN-only update uses the same swap: it copies the active database, updates `pun`, and replaces it only if the copy passes the integrity check. Raw downloads are stored by date under the configured raw directory.

The XML parser is streaming and hardened against DTD/external entities. Unknown XML paths are preserved in `extra_json` and reported instead of stopping the load. Prices are parsed with `Decimal` and stored in SQLite as `REAL`. The database is the canonical serving artifact: it is rebuildable from the sources, while raw files are operational staging.

## Repository layout

| Path | Purpose |
| --- | --- |
| `etl/` | Download, XML parsing, CSV parameter loading, PUN loading, schema, validation, and atomic swap. Entry point: `python -m etl`. |
| `etl/schema.sql` | SQLite schema for offers, components, conditions, parameters, decodings, PUN, and ETL runs. |
| `etl/pun.py` | Monthly PUN from the Portale Offerte "Prezzi storici" CSV (`PUN_MENSILE` series); it accumulates across database rebuilds. |
| `offerte/` | Single non-ETL package: read-only query and calculation library plus the MCP server (`offerte.mcp`). A CLI, if added, is local-only debugging support and is not an agent or production interface. `offerte.db` is the only read-only database entry point (`mode=ro` plus `PRAGMA query_only=ON`); `offerte.ricerca.cerca_offerte` is the shared application search function; `offerte.mcp` exposes it with structured errors; transport stdio (default) or local streamable HTTP bound to loopback. |
| `tests/` | Unit and integration tests, including XML security, ETL swap cases, MCP tool discovery, and an MCP stdio integration test with the official client. |
| `docs/` | Architecture, the `cerca_offerte` contract, XML validation, deployment, open questions and the roadmap. See `docs/index.md`. |
| `compose.yml` | Docker Compose services `offerte-mcp` and `offerte-etl`, from the single image. |
| `deploy/` | Deployment configuration and `compose.local.yml`, the fixture override without named volumes or network. |
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

## Commands

Run the complete verification suite (lint, formatting, type checking, tests):

```bash
just check
```

Load the small checked-in fixture into `build/offerte.db`:

```bash
just etl-fixture
```

Load a previously downloaded complete XML and its parameter CSV. This expects `raw/2026-10-14/PO_Offerte_E_MLIBERO_20261014.xml` and `docs/PO_Parametri_Mercato_Libero_E_20261014.csv`:

```bash
just etl-reale
```

Download the current XML from the allowlisted Portale Offerte host and load it:

```bash
just etl-scarica
```

Update the PUN series without reloading the offers (the command copies the active database and applies the same atomic swap as the ETL):

```bash
just etl-pun                          # downloads the Portale Offerte CSV
just etl-pun-file path/to/prezzi.csv  # loads a file already downloaded
```

The network command still takes the parameter CSV from `docs/`; check `justfile` before using it with a different snapshot. The ETL can also be run directly; commands print structured JSON, and a failed validation leaves the active database unchanged and returns a non-zero exit code:

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

## Configuration

The runtime defaults are suitable for the deployment volume:

| Variable | Default | Used for |
| --- | --- | --- |
| `OFFERTE_DB` | `/var/lib/offerte/db/offerte.db` | active SQLite database (with `.new` and `.prev` beside it) |
| `OFFERTE_RAW_DIR` | `/var/lib/offerte/raw` | dated raw downloads |
| `OFFERTE_PARAMETRI` | unset | parameter CSV; v1 mounts the current snapshot and updates it manually (automatic download is a production task) |
| `OFFERTE_MCP_HOST` | `127.0.0.1` | MCP HTTP bind address (loopback only in this phase) |
| `OFFERTE_MCP_PORT` | `8000` | MCP HTTP port; takes precedence over `PORT` |
| `PORT` | unset | fallback port convention for hosted HTTP platforms |
| `OFFERTE_MCP_CONSENTI_NON_LOOPBACK` | unset | explicit opt-in to a non-loopback HTTP bind (containers only) |

An explicit command-line option takes precedence over its environment variable. `--db` remains supported by the MCP server and by the ETL. The MCP process opens the active database with SQLite `mode=ro` and `PRAGMA query_only=ON`; it never creates a missing database and has no access to the raw directory. The ETL creates and swaps `offerte.db.new` and `offerte.db.prev` in the same configured database directory. Keep that directory on one writable volume for the ETL and a read-only mount for MCP; the raw directory is a separate ETL-only mount.

A local run can use paths outside the defaults without changing code:

```bash
OFFERTE_DB=/tmp/offerte/db/offerte.db \
OFFERTE_RAW_DIR=/tmp/offerte/raw \
OFFERTE_PARAMETRI=tests/fixtures/PO_Parametri_Mercato_Libero_E_20261014.csv \
uv run python -m etl locale --raw tests/fixtures/offerta_estratto.xml --snapshot 2026-10-14
```

## MCP server (read-only)

The server exposes a single tool, `cerca_offerte`, backed by the shared search function (`offerte.ricerca.cerca_offerte`). MCP is the only interface available to agents; a future CLI, if useful for debugging, is local-only and is never invoked by MCP or included as a production access path. MCP opens the database read-only and never writes to it. The database path comes from `--db`, otherwise from `$OFFERTE_DB`, otherwise `/var/lib/offerte/db/offerte.db`. HTTP host and port come from `--host` and `--port`, then `$OFFERTE_MCP_HOST` and `$OFFERTE_MCP_PORT` (with `$PORT` as a platform fallback). Non-loopback hosts are refused unless `--consenti-bind-non-loopback` (or `$OFFERTE_MCP_CONSENTI_NON_LOOPBACK`) asks for them explicitly, as the Compose service does inside the container.

Local stdio (default), for a host that launches the process itself:

```bash
uv run python -m offerte.mcp --db build/offerte.db
```

Local streamable HTTP on loopback; any non-loopback `--host` is refused:

```bash
uv run python -m offerte.mcp --db build/offerte.db --trasporto http --port 8000
# endpoint: http://127.0.0.1:8000/mcp
```

`cerca_offerte` filters, all optional, are passed inside a `filtri` object: `fornitore` (exact VAT number; the commercial name is not in the data model), `regione`, `provincia`, `comune` (case-insensitive exact match on the zones the offer declares), `tipo_cliente` (`domestico`, `altri usi` or `condominio uso domestico (gas)`), `tipo_offerta` (`fisso`, `variabile`, `flat` or `mista`), `indicizzata`, `testo` (searched in the offer name and description) and `limit` (1-50, default 20). Seller text is returned in fields marked as untrusted. Input errors come back as structured results (`{"codice": "...", "messaggio": "..."}`). The full contract is in `docs/cerca_offerte_contract.md`.

The checked-in fixture offer expired on 2026-10-10, so with the contract's default validity filter (`data_fine >= today`) a search on the fixture database returns no results; it is still useful to smoke-test that the tool starts and answers. Use real data for a non-empty search. The MCP tests (tool discovery, in-memory calls, stdio integration, loopback HTTP) run as part of `just test`.

## Docker and Compose

Build the single image used by both processes and start the read-only MCP service, which publishes the port only on `127.0.0.1`:

```bash
docker compose build
docker compose up -d offerte-mcp
```

Run the batch ETL job (exclusive lock, atomic swap, exits when finished):

```bash
docker compose --profile etl run --rm offerte-etl
```

For a local fixture without named volumes and without network downloads, use the override that bind-mounts `build/`:

```bash
just etl-fixture
docker compose -f compose.yml -f deploy/compose.local.yml up --build offerte-mcp
docker compose -f compose.yml -f deploy/compose.local.yml run --rm offerte-etl
```

Stop the service, keeping the data volume:

```bash
docker compose stop offerte-mcp     # stop the service, keep the container and the volumes
docker compose down                 # stop and remove the containers, keep the named volumes
```

The full deploy and shut-down runbook for a local machine and for the VPS (build, ETL, verify, Tunnel, update, backup, teardown, host-directory persistence) is in `docs/deployment.md`. The image, the Compose service details, the runtime layout and the lock/readiness behaviour are there too. Deployment follows Path A (Cloudflare at the edge, Python at the origin; see `docs/roadmap.md`): for now there is no own domain, so debugging uses a temporary Cloudflare Tunnel with the default `*.trycloudflare.com` URL and is not for third-party traffic; a named Tunnel on an own domain is the production step.

## Documentation

Start from `docs/index.md`: `architecture.md` (design and data model), `cerca_offerte_contract.md` (tool contract), `xml_validation.md` (validation of the real XML), `deployment.md` (image, Compose, VPS), `open_questions.md` (unresolved points) and `roadmap.md` (objectives and tasks still to implement).
