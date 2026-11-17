# Roadmap

Objectives not yet implemented, in order, and their operational tasks. Stable context in `docs/architecture.md`; deployment commands in `docs/deployment.md`; current state and commands in `README.md`.

No new functions are implemented before the functional trial (Objective 1), and deployment (Objectives 2–3) takes precedence over new tools or calculations.

## Product and security decisions

MCP is the only point of contact between the LLM and the database. No agent gets access to a shell, filesystem, SQLite or CLI. No tool accepts code, free SQL or commands to execute.

The application server stays unauthenticated. No API keys, `authctl`, OAuth, sessions or credential store will be implemented. The CLI is not an agent interface: if it is ever needed, it will only be a local debug adapter.

## Deployment decision — Path A (locked)

The deployment path is **Cloudflare at the edge, Python at the origin**: a single Linux host (Debian, EU provider chosen by the user) runs the existing Docker image with Compose (`offerte-mcp` long-running, `offerte-etl` one-shot), and Cloudflare provides only the public edge (Tunnel ingress, TLS, DDoS/WAF, per-IP rate limiting). The SQLite file on the host volume is the canonical database artifact; the ETL and MCP server stay pure Python and provider-agnostic (environment variables + filesystem layout only).

Explicitly **not** Path A, and out of scope for these objectives: Cloudflare Workers (Python or TypeScript) as the MCP runtime, D1 / Durable Objects / R2 as the serving database, and any TypeScript rewrite of the query/calculation logic. Worker CPU/memory/startup limits and the absence of a filesystem/`sqlite3` in that runtime do not fit the 22 MB XML ETL or the file-based SQLite design; D1/DO would only ever be derived projections of the SQLite artifact. The portability boundary is therefore kept minimal on purpose: no Repository/publisher abstractions, no provider SDKs in `etl/` or `offerte/` — a future migration, if ever needed, starts from the SQLite artifact + `etl/schema.sql`.

Current state: the target host is **not yet provisioned**, and **no own domain is configured on Cloudflare yet**. Objectives 1–2 therefore use the Cloudflare default temporary URL (`*.trycloudflare.com`) for debugging only. A named Tunnel on an own domain is a production task (Objective 3), not a prerequisite for debugging.

Parameters CSV (v1 decision): the current snapshot `docs/PO_Parametri_Mercato_Libero_E_20261014.csv` is mounted into the ETL job and **updated manually** (replace the file, keep the `PO_Parametri_..._AAAAMMGG.csv` name, rerun the ETL). Automatic parameter download is deferred to the production objective.

## Usable state for the trial

Already available:

- manual ETL of the offers XML, the parameters CSV and the monthly PUN;
- SQLite database read by MCP read-only;
- `cerca_offerte` tool in the library and in the MCP server;
- Streamable HTTP transport on loopback;
- `/healthz` readiness;
- non-root Docker image and Compose services;
- local fixture and HTTP integration tests;
- `just check`.

The first trial uses this surface without adding tools or calculations.

## Objective 1 — Functional MCP + LLM trial

### Steps

1. Prepare a valid **real-data** database (`just etl-scarica` / `etl-reale`). The checked-in fixture is only a smoke test: it expired on 2026-10-10, so the default validity filter returns no results on it.
2. Start the ETL and the `offerte-mcp` service with the local Compose override (commands in `docs/deployment.md`).
3. Verify `/healthz` and the existing HTTP tests.
4. Make the service reachable by the LLM through a temporary Tunnel to `127.0.0.1:8000` (auto-generated `*.trycloudflare.com` URL; no own domain), without publishing the MCP port directly.
5. Configure the LLM's MCP client with the `/mcp` endpoint over Streamable HTTP.
6. Verify discovery and a real call to `cerca_offerte`.

### Completion criterion

The LLM connects to the Streamable HTTP endpoint, discovers `cerca_offerte`, performs a call and receives a structured response. `just check`, Compose config, readiness and the HTTP tests pass.

The temporary Tunnel is only for the trial: the endpoint is public and unauthenticated, so it must not be used for third-party data or traffic.

## Objective 2 — Debugging deployment on the target host (no own domain)

Deploy the same image + Compose to the (to-be-provisioned) target host, still behind a temporary Tunnel with the Cloudflare default URL. This proves the production shape (host, volumes, users, ETL on the host) without needing a domain.

### Steps

1. Provision the host: stable Debian, Docker, key-based SSH, automatic security updates. No public MCP port.
2. Create host directories `/var/lib/offerte/db` and `/var/lib/offerte/raw`; copy `.env.example` to `.env`, pointing `OFFERTE_PARAMETRI_DIR`/`OFFERTE_PARAMETRI_NOME` at the mounted current param snapshot.
3. Build the image and run the ETL **on the host** (`docker compose --profile etl run --rm offerte-etl`) against real data, then start MCP (`docker compose up -d offerte-mcp`). Verify `/healthz` on the host.
4. Expose it with a temporary Tunnel (`cloudflared tunnel --url http://127.0.0.1:8000`) and verify from outside: `/healthz`, tool discovery and a real `cerca_offerte` call via the auto-generated `https://<temporary-name>.trycloudflare.com/mcp` URL.
5. Record the run in the operations notes (host, image tag/commit, DB snapshot date, param snapshot date). No third-party traffic on this endpoint.

### Completion criterion

From a clean external client, the debugging endpoint answers `/healthz` (200), lists `cerca_offerte` and returns a structured result on real data. `just check` passes locally; Compose config and readiness pass on the host.

## Objective 3 — Production deployment (own domain)

Only after Objective 2. Each item is introduced separately and verified.

- own domain on Cloudflare + named Tunnel (`cloudflared` as a Compose service) → `mcp.<domain>`; origin reachable only through the Tunnel;
- per-IP rate limiting on `/mcp` at the Cloudflare edge (plus default WAF);
- daily offers/parameters + monthly PUN scheduling via host systemd timers running the `offerte-etl` Compose profile (ETL lock and atomic swap already in code);
- **automatic parameter CSV download**, replacing the manually mounted snapshot (manual replacement remains the fallback until this lands);
- host bootstrap idempotency, backup/restore/rollback (active + previous DB, config; raw files are not a functional requirement), clean-machine restore test;
- operations runbook, basic monitoring/observability criteria, release management;
- licence/terms-of-use verification before offering the service to third parties.

Completion criterion: the public endpoint on the own domain survives a host reboot and a full ETL + PUN cycle unattended, with backup restore verified.

## Readability simplification (after Objective 2, before new features)

No behaviour change; one refactor at a time, each verified with `just check` and the MCP/ETL tests. Goal: keep two packages, one image, one DB file — and resist new abstractions.

1. `offerte/mcp.py`: separate the concerns already in one file (tool schema `Filtri`/`DESCRIZIONE_TOOL`, server factory, host validation, CLI parsing/`main`). Keep the `python -m offerte.mcp` entry point and all imports used by Dockerfile/Compose/tests unchanged.
2. `etl/__main__.py`: separate argument parsing, command dispatch (`locale`/`scarica`/`pun`), and JSON result printing.
3. `etl/esegui.py`: extract the validation and atomic-swap helpers from `esegui()` (the PUN path `esegui_pun` is already separate).
4. Trim docstrings/comments that duplicate `README.md`/`docs/` verbatim; keep only non-obvious intent in code. Do not add Repository/publisher/manifest abstractions, new packages, or new dependencies in this track.

## Post-MVP functions (after Objectives 1–3, in an order to be agreed)

- `dettaglio_offerta(piva, cod_offerta)`;
- `pun(da, a, aggregazione="mensile")`;
- `decodifica(dominio, codice?)`;
- `stato_dati()`;
- `confronta_offerte`;
- energy-supply-only estimate with `Decimal` and explicit `non_calcolabile` results;
- local debug CLI, only if useful to developers, never for agents or production.

## Out of scope

- API key authentication, `authctl`, OAuth, JWKS and identity providers;
- LLM access to the shell, filesystem, DB or CLI;
- free SQL, code or commands executed through MCP;
- total cost with regulated components (phase B);
- daily PUN from the GME;
- Kubernetes, database servers, Redis, queues, local reverse proxy and separate metrics/alerting stacks;
- Cloudflare Workers/D1/Durable Objects/R2 as runtime or database, TypeScript rewrite, Manufact Cloud as the initial deployment, and provider-abstraction layers (Repository/publisher/manifest) — see the Path A decision above;
- new tools or new calculation formulas before the functional trial.

## Working rule

One task at a time, small and verifiable. Before the trial no features are added: use the commands and code already present. After the trial, deployment tasks come before new functions; every operational or functional activity is introduced separately and verified with `just check` and its own test.
