# EnergySuppliers

Pipeline that downloads the Italian free-market electricity offers, normalizes them into SQLite, and is being built to expose the data read-only to agents.

## How it works

```text
XML/CSV files ──> download ──> streaming parser ──> SQLite database
                                      │
                         validation + atomic database swap
```

The ETL builds `offerte.db.new`, validates it, and replaces the active database only when the checks pass. The previous database is kept as `offerte.db.prev` in the same directory. The PUN-only update uses the same swap: it copies the active database, updates `pun`, and replaces it only if the copy passes the integrity check. Raw downloads are stored by date under the configured raw directory.

The XML parser is streaming and hardened against DTD/external entities. Unknown XML paths are preserved in `extra_json` and reported instead of stopping the load. Prices are parsed with `Decimal` and stored in SQLite as `REAL`.

## Deployment decision

The first production deployment will use one Debian VPS with Docker Compose:
`offerte-mcp` is long-running, `offerte-etl` is a one-shot batch job launched by
an external systemd timer, and `cloudflared` will be the only public ingress.
The MCP service is intentionally unauthenticated; Cloudflare provides the
public edge and IP rate limiting. Agents have no shell, filesystem, database, or
CLI access: MCP is the only agent-facing interface. Kubernetes,
MySQL/PostgreSQL, Parquet, Redis, and message queues are intentionally deferred.

SQLite remains the canonical serving database. The active database, its
previous snapshot and the ETL lock are persistent VPS files; the MCP container
sees only the database read-only. Raw downloads are staging data, not a required
historical archive, and the production policy will remove them after a successful
ETL (or after diagnosing a failed run).

The code is kept compatible with a future hosted MCP platform such as
[Manufact Cloud](https://docs.manufact.com/dashboard/quickstart): application
functions remain independent of the filesystem and provider, the HTTP entry
point is configurable, and `/healthz` is a provider-neutral readiness route.
A future serverless deployment would publish immutable SQLite artifacts to
shared object storage instead of assuming a persistent local database.

## Repository layout

| Path | Purpose |
| --- | --- |
| `etl/` | Download, XML parsing, CSV parameter loading, PUN loading, schema, validation, and atomic swap. Entry point: `python -m etl`. |
| `etl/schema.sql` | SQLite schema for offers, components, conditions, parameters, decodings, PUN, and ETL runs. |
| `etl/pun.py` | Monthly PUN from the Portale Offerte "Prezzi storici" CSV (`PUN_MENSILE` series); it accumulates across database rebuilds. |
| `offerte/` | Single non-ETL package: read-only query and calculation library plus the MCP server (`offerte.mcp`). A CLI, if added, is local-only debugging support and is not an agent or production interface. `offerte.db` is the only read-only database entry point (`mode=ro` plus `PRAGMA query_only=ON`); `offerte.ricerca.cerca_offerte` is the shared application search function; `offerte.mcp` exposes it with structured errors; transport stdio (default) or local streamable HTTP bound to loopback. |
| `tests/` | Unit and integration tests, including XML security, ETL swap cases, MCP tool discovery, and an MCP stdio integration test with the official client. |
| `docs/` | Architecture, the `cerca_offerte` contract, XML validation, open questions, the goals still to implement (`goals.md`), the task breakdown for a goal (`task.md`), and the tracked parameter fixture. |
| `compose.yml` | Docker Compose services `offerte-mcp` and `offerte-etl`, from the single image. |
| `deploy/` | Deployment notes and `compose.local.yml`, the fixture override without named volumes or network. |
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

### Runtime paths and environment

The runtime defaults are suitable for the deployment volume:

| Variable | Default | Used for |
| --- | --- | --- |
| `OFFERTE_DB` | `/var/lib/offerte/db/offerte.db` | active SQLite database (with `.new` and `.prev` beside it) |
| `OFFERTE_RAW_DIR` | `/var/lib/offerte/raw` | dated raw downloads |
| `OFFERTE_PARAMETRI` | unset | parameter CSV, until its automatic download is available |
| `OFFERTE_MCP_HOST` | `127.0.0.1` | MCP HTTP bind address (loopback only in this phase) |
| `OFFERTE_MCP_PORT` | `8000` | MCP HTTP port; takes precedence over `PORT` |
| `PORT` | unset | fallback port convention for hosted HTTP platforms |
| `OFFERTE_MCP_CONSENTI_NON_LOOPBACK` | unset | explicit opt-in to a non-loopback HTTP bind (containers only) |

An explicit command-line option takes precedence over its environment variable.
`--db` remains supported by the MCP server and by the ETL. The MCP process
opens the active database with SQLite `mode=ro` and `PRAGMA query_only=ON`; it
never creates a missing database and has no access to the raw directory. The
ETL creates and swaps `offerte.db.new` and `offerte.db.prev` in the same
configured database directory. Keep that directory on one writable volume for
the ETL and a read-only mount for MCP; the raw directory is a separate ETL-only
mount.

For example, a local run can use paths outside the defaults without changing
code:

```bash
OFFERTE_DB=/tmp/offerte/db/offerte.db \
OFFERTE_RAW_DIR=/tmp/offerte/raw \
OFFERTE_PARAMETRI=tests/fixtures/PO_Parametri_Mercato_Libero_E_20261014.csv \
uv run python -m etl locale --raw tests/fixtures/offerta_estratto.xml --snapshot 2026-10-14
```

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

## Docker image (phase 2)

The repository includes one multi-stage image for both application processes.
The build uses the pinned `uv.lock`, installs production dependencies only, and
copies only `etl/` and `offerte/` into the runtime stage; tests, raw files,
local databases, and development tools are excluded by `.dockerignore`.
Python 3.11 and uv base images are pinned by digest. The image contains the
non-root users `offerte-etl` and `offerte-mcp`, with the latter as the default.

Build it from the repository root:

```bash
docker build --tag offerte:local .
```

The default command is the MCP module. The same image selects the ETL module by
replacing the command and, for a batch run, the user:

```bash
docker run --rm \
  --read-only --tmpfs /tmp \
  --security-opt no-new-privileges --cap-drop ALL \
  --user offerte-mcp \
  -e OFFERTE_DB=/var/lib/offerte/db/offerte.db \
  -v "$PWD/build:/var/lib/offerte/db:ro" \
  offerte:local -m offerte.mcp

docker run --rm --user offerte-etl \
  --security-opt no-new-privileges --cap-drop ALL \
  -v offerte-db:/var/lib/offerte/db \
  -v offerte-raw:/var/lib/offerte/raw \
  -v "$PWD/docs:/var/lib/offerte/parametri:ro" \
  offerte:local -m etl scarica \
  --db /var/lib/offerte/db/offerte.db \
  --raw-dir /var/lib/offerte/raw \
  --parametri /var/lib/offerte/parametri/PO_Parametri_Mercato_Libero_E_20261014.csv
```

This section covers the image only; the Compose services built from it are
described below. The MCP container must keep its database mount read-only and
must not be given a raw mount.

## Docker Compose (phase 3)

`compose.yml` runs both processes from that image:

- `offerte-mcp` is long-running, runs as the non-root `offerte-mcp` user, mounts
the database read-only, has a read-only root filesystem with a `tmpfs` for
`/tmp`, drops all capabilities, and publishes the MCP port only on the host
loopback (`127.0.0.1:${OFFERTE_MCP_PORT:-8000}:8000`). It does not mount the raw
directory. `/healthz` is an unauthenticated HTTP readiness route; the Docker
healthcheck runs `python -m offerte.mcp --verifica`, which reports
`database_assente` (exit 1) or `database_non_leggibile` (exit 2) instead of
creating an empty database.
- `offerte-etl` is a batch job under the `etl` profile, runs as `offerte-etl`,
mounts the database and the dated raw directory read-write, and exits when the
ETL finishes (success or failure). It is never started by `docker compose up`.

The database volume holds `offerte.db`, its `.new` and `.prev` snapshots, and
the `etl.lock` file. The lock (`flock`, released on error or termination) makes
a second concurrent ETL fail immediately with exit code 3 and a structured
`etl_in_corso` error. The parameter CSV is mounted (not baked into the image)
until its automatic download exists; its filename must keep the
`PO_Parametri_..._AAAAMMGG.csv` form because the date is read from it.

Copy `.env.example` to `.env` to override the port and the parameter CSV
location, then build and start MCP (the database volume must already contain a
database produced by the ETL):

```bash
cp .env.example .env
docker compose build
docker compose up -d offerte-mcp
```

Run the ETL manually:

```bash
docker compose --profile etl run --rm offerte-etl
```

For a local fixture without named volumes and without network downloads, use the
override that bind-mounts `build/`:

```bash
just etl-fixture
docker compose -f compose.yml -f deploy/compose.local.yml up --build offerte-mcp
docker compose -f compose.yml -f deploy/compose.local.yml run --rm offerte-etl
```

The local override runs as the host UID/GID (set `OFFERTE_LOCAL_UID` and
`OFFERTE_LOCAL_GID` if yours differ from `1000`) and adds `:z` to the bind mounts
for SELinux hosts. External scheduling (systemd timer), the operational restore
procedure, and the repeatable clean-VM smoke test are the next phase, described
in `docs/task.md`.

## Future Manufact Cloud deployment

Manufact can deploy this repository from GitHub using the Python runtime or the
committed `Dockerfile`, with a configurable start command, port, and
per-environment variables. When this option is evaluated, configure the MCP
process explicitly as HTTP rather than using its local stdio default:

```text
start command: python -m offerte.mcp --trasporto http
port: 3000
OFFERTE_MCP_HOST=0.0.0.0
OFFERTE_MCP_PORT=3000
OFFERTE_MCP_CONSENTI_NON_LOOPBACK=1
```

Do not configure a production deployment to depend on a local persistent DB or
raw directory. The future serverless adapter must download a validated,
immutable SQLite artifact from shared object storage. Preview deployments must
use separate non-production data and secrets. See `docs/architettura.md` §12.5
for the boundaries and the official Manufact references.

## MCP server (read-only)

The server exposes a single tool, `cerca_offerte`, backed by the shared search
function (`offerte.ricerca.cerca_offerte`). MCP is the only interface available
to agents. A future CLI, if useful for debugging, is local-only and is never
invoked by MCP or included as a production access path. MCP opens the database
read-only (`mode=ro` plus `PRAGMA query_only=ON`) and never writes to it. The database path comes from `--db`, otherwise from `$OFFERTE_DB`, otherwise
`/var/lib/offerte/db/offerte.db`. HTTP host and port come from `--host` and
`--port`, then `$OFFERTE_MCP_HOST` and `$OFFERTE_MCP_PORT` (with `$PORT` as a
platform fallback). Non-loopback hosts are refused unless
`--consenti-bind-non-loopback` (or
`$OFFERTE_MCP_CONSENTI_NON_LOOPBACK`) asks for them explicitly, as the Compose
service does inside the container.

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

Out of scope for now: cost calculation, extra tools
(`confronta_offerte`, `dettaglio_offerta`, `pun`, `decodifica`, `stato_dati`),
external scheduling, systemd units, and production hardening. For the first
functional trial, the loopback HTTP service may be reached by a temporary
`cloudflared tunnel --url http://127.0.0.1:8000`; this is an unauthenticated,
public test endpoint, not a production ingress.

## Current scope

The implemented scope is the ETL (offers, parameters, and the monthly PUN series), its validation on the fixture and real XML summary, the read-only database access layer, the shared `cerca_offerte` search function (filters, limits, stable ordering, structured errors), the MCP server (`mcp==2.3.0`, official Python SDK v2 line) on stdio or Streamable HTTP, a reproducible non-root Docker image for MCP and ETL, and the Compose services `offerte-mcp` and `offerte-etl` (read-only MCP on host loopback, batch ETL with an exclusive lock and atomic swap). The immediate goal is a functional LLM trial using an already loaded DB and, if needed, a temporary Cloudflare Tunnel. Automatic parameter download, external scheduling, permanent public ingress, IP rate limiting, backup/restore, and production deployment units are later work. Additional MCP tools and cost calculation are post-MVP. A CLI is not an agent interface or deployment requirement; application authentication is intentionally not planned. The daily PUN series (GME) is out of scope for now.

Read `docs/architettura.md` for the design and data model, `docs/contratto_cerca_offerte.md` for the `cerca_offerte` contract, `docs/validazione_xml.md` for the aggregate validation of the real XML, `docs/questioni_aperte.md` for unresolved source and calculation questions, `docs/goals.md` for the goals still to implement, and `docs/task.md` for the task breakdown of a goal.
