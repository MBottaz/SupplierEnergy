# Roadmap

Objectives not yet implemented, in order, and their operational tasks. Stable context in `docs/architecture.md`; deployment commands in `docs/deployment.md`; current state and commands in `README.md`.

The first objective is a functional trial of the existing MVP: start MCP over **Streamable HTTP** and connect it to an LLM. No new functions are implemented before that trial.

## Product and security decisions

MCP is the only point of contact between the LLM and the database. No agent gets access to a shell, filesystem, SQLite or CLI. No tool accepts code, free SQL or commands to execute.

The application server stays unauthenticated. No API keys, `authctl`, OAuth, sessions or credential store will be implemented. The CLI is not an agent interface: if it is ever needed, it will only be a local debug adapter.

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

1. Prepare an already valid database, or load the fixture with `just etl-fixture`.
2. Start the fixture ETL and the `offerte-mcp` service with the local Compose override (commands in `docs/deployment.md`).
3. Verify `/healthz` and the existing HTTP tests.
4. Make the service reachable by the LLM through a temporary Tunnel to `127.0.0.1:8000`, without publishing the MCP port directly.
5. Configure the LLM's MCP client with the `/mcp` endpoint over Streamable HTTP.
6. Verify discovery and a real call to `cerca_offerte`.

### Completion criterion

The LLM connects to the Streamable HTTP endpoint, discovers `cerca_offerte`, performs a call and receives a structured response. `just check`, Compose config, readiness and the HTTP tests pass.

The temporary Tunnel is only for the trial: the endpoint is public and unauthenticated, so it must not be used for third-party data or traffic.

## After the functional trial

Only if the trial succeeds and the decision is to continue, address the following, each introduced separately and verified with `just check` and the relevant test.

Operational:

- automatic parameter CSV download;
- final host directories, raw retention and complete release management;
- idempotent production VM bootstrap;
- daily/monthly systemd timers, ETL lock and retry;
- named Tunnel and permanent Cloudflare configuration;
- per-IP rate limiting;
- backup, restore, rollback and periodic clean-machine tests;
- operations runbook, monitoring and observability;
- licence verification before offering the service to third parties.

Post-MVP functions, in an order to be agreed:

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
- new tools or new calculation formulas before the functional trial.

## Working rule

One task at a time, small and verifiable. Before the trial no features are added: use the commands and code already present. After the trial, every operational or functional activity is introduced separately and verified with `just check` and its own test.
