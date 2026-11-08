# Architecture: electricity-offer database and agent interfaces

Stable context document. Objectives still to implement are in `docs/roadmap.md`; deployment detail in `docs/deployment.md`; current state and commands in `README.md`.

## 1. Objective

A minimal system that:

1. periodically downloads the Italian free-market electricity offers (open-data XML, ~22 MB), the regulated-parameters file (CSV) and the PUN;
2. normalizes and loads them into a SQLite database (a single file);
3. exposes them read-only to **AI agents** through the MCP server only, with functions such as `confronta_offerte`. The library may have a local debug CLI, but the CLI is not an agent interface and is not exposed in the deployment.

The users are agents, not people: names, descriptions and output formats are designed for an LLM that reads them.

## 2. Principles

- **Minimalism**: few dependencies, no heavy frameworks, no service that needs continuous maintenance.
- **Portability**: Linux (stable Debian as the target), FreeBSD where possible. The first installation is a VM with Docker Compose; the code must not depend on a specific provider.
- **Separation of privileges**: ETL (writes the DB) and interfaces (read it) are distinct processes with distinct users.
- **The DB is rebuildable** from scratch by downloading the sources again. Raw files are operational staging, not a mandatory historical archive; the DB and schema stay portable as SQLite artifacts.
- **Do not guess**: track codes and calculation formulas come from the official documentation.
- **Cost calculation lives in Python**, with `Decimal`, tested.

## 3. Architecture

```
[systemd timer] → etl: fetch → parse → normalize → offerte.db.new → validation → atomic rename
                                                              │
                                                    offerte.db (opened read-only)
                                                              │
                              `offerte` package (no network I/O in the library)
                               ├── optional local CLI           → application debugging only
                               └── MCP server on 127.0.0.1       → the only agent access path
                                                              │
        cloudflared (Tunnel: outbound connection only) ←→ Cloudflare (proxy: DDoS, WAF, per-IP rate limit) ←→ agents
```

| Component | Does | Does NOT do |
|---|---|---|
| `etl` | downloads, validates, parses, writes the new DB, atomic swap, records `etl_run` | does not serve requests, opens no ports |
| `offerte` library | typed queries and cost calculation (`calc`, pure functions) | no network access |
| optional local CLI | debug adapter for library functions | is not an agent interface and is not part of the deployment |
| MCP server | the only agent access path, exposes functions as read-only tools | does not write the DB, handles no authentication or sessions |
| Cloudflare + Tunnel | DDoS, WAF, per-IP rate limit, public TLS | does not modify the DB and needs no local reverse proxy |

There is a single non-ETL Python package, `offerte`: the library (queries and calculation) and the MCP server. A local CLI may be added as a debug adapter, but it is not an agent frontend and not a deployment component. Separation of privileges is at the process level, not the namespace level.

## 4. Data sources (URLs must be verified, never invented)

1. **Offers XML**: Portale Offerte by ARERA (open data), electricity, free market. Find the official URL and the **official track** with the decoding tables. Conditional download (ETag / If-Modified-Since); if the SHA-256 matches the last run, do nothing. Verify the terms of use.
2. **Parameters CSV**: `PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv`, columns `nome_parametro,valore,descrizione`, ~100 rows. The date in the filename is the reference date: store it with the values.
3. **PUN**: two sources, both to be verified for terms of use. *Monthly series* (used by most indexed offers): the "Prezzi storici - indici a pubblica diffusione" CSV from the Portale Offerte Open Data page, column `PUN (€/kWh)`, one value per month; `python -m etl pun` downloads it and updates `pun` (series `PUN_MENSILE`), the URL is not dated and lives in `etl/pun.py`. *Daily series*: the GME API service (official technical guide of October 2025, with authentication: a user registration is required). Alternative: the "MGP – Download" files. Since 2025 the index is the PUN Index GME: verify the definition and record in `pun` which series you use. **Out of scope for now**: only the monthly series is loaded; the GME daily series is added when it is actually needed. **Verify the terms of use of both sources** (commercial use, redistribution) and note them in `docs/open_questions.md`: they constrain how the service may be offered to third parties.

Many indexed offers use the monthly average PUN, not the daily one: read the definition of the index (`IDX_PREZZO_ENERGIA`) from the track.

## 5. Parser development strategy

The full XML is never read by the agent. The procedure is:

1. The parser is built from the **official track** and the fixture `tests/fixtures/offerta_estratto.xml` (a single variable-price offer).
2. It is **tolerant**: every unexpected path or element goes into `extra_json` and is counted in `etl_run.percorsi_sconosciuti`. It never fails the load.
3. Validation on real data happens **after** the first full-XML load, with aggregate SQL queries on the DB (unknown paths, distinct code values, repeated elements, empty fields, date range, duplicates). The result is a summary in `docs/xml_validation.md`.
4. If validation discovers structures not yet modelled (for example how fixed-price offers are represented, of which the fixture is no example), extend the schema and rebuild the DB from the raw files.

## 6. Data model (SQLite)

"Long" format: F1/F2/F3 bands and fixed charges are simple rows of `component`.

- `offerta(piva, cod_offerta, nome, descrizione, tipo_mercato, offerta_singola, tipo_cliente, tipo_offerta, tipologia_att_contr, durata, garanzie, idx_prezzo_energia, data_inizio, data_fine, modalita_pagamento, tipo_dispacciamento, url_sito, url_offerta, telefono, extra_json, snapshot_date)`, key `(piva, cod_offerta)`
- `componente(piva, cod_offerta, nome, descrizione, tipologia, macroarea, fascia, prezzo, unita_misura, extra_json)`
- `condizione(piva, cod_offerta, tipologia, descrizione, limitante)`
- `codifica(dominio, codice, descrizione)`
- `parametro(nome, valore, descrizione, riferimento)`, key `(nome, riferimento)`. The parameter metadata (`unita`, `categoria_cliente`, BTA) arrives in phase B, with a dedicated table compiled from the official documentation: no empty table is added now.
- `pun(data, valore_eur_mwh, serie)`, key `(data, serie)`. Two series are planned: `PUN_MENSILE` (monthly average, from the Portale Offerte "Prezzi storici" file, loaded by `python -m etl pun`) and, if needed, `PUN_GIORNALIERO` (from the GME).
- `etl_run(id, inizio, fine, esito, sorgente, sha256, n_offerte, percorsi_sconosciuti, note)`

Normalization:
- dates `dd/mm/yyyy_hh:mm:ss` → ISO 8601, time zone Europe/Rome; default queries filter `data_fine >= today`;
- prices read with `Decimal`, stored `REAL`, with the original unit of measure;
- free text from sellers: strip control characters and truncate.

The DB is rebuilt from scratch on every run from the latest raw file, copying from the previous one only `parametro`, `pun` and `etl_run`. The PUN-only update (`python -m etl pun`) does not rebuild the offers: it starts from a copy of the active DB, updates `pun`, and goes through the same atomic swap, so even this command never modifies the active DB in place.

## 7. Parameters file

From the file `PO_Parametri_Mercato_Libero_E_20260928.csv` (100 rows):

- Names follow a pattern: component prefix (`acc`, `arim`, `asos`, `dis`, `iva`, `pcv`…), customer category (`_d`/`_nd`/`_a`, `_dr`/`_dnr`, `_b1`…`_b6`) and type (`_c` energy, `_f` fixed charge, `_p` power).
- **The units are not in the file**: €/kWh, €/year or €/POD/year, €/kW/year, odd amounts (`acc_a_h_h` = 4820.0, `gamma` = -73.5737) and dimensionless values (`lambda` = 0.1) coexist. The metadata (unit, customer category, BTA) will be derived from the official documentation in phase B, not inferred from the names.
- All rows are always loaded as-is; metadata arrives in a second pass (phase B), so a change in the naming scheme does not break the load.
- The BTA classification (`_b1`…`_b6`) is mapped to customer power/use from the official document; if it cannot be found, ask the user. This mapping is for phase B, not for loading the parameters.
- Mandatory parameters checked by the ETL (at least `pcv_a`, `pcv_c`, `iva_a`, `iva_c`, `lambda`): if missing, the swap is blocked.

## 8. ETL

1. Download into a temporary folder with timeout, size limit (e.g. 100 MB), allowlisted hosts only, HTTPS only.
2. Raw files are saved temporarily under `raw/AAAA-MM-GG/` during the ETL. Production policy does not require retention: after a successful swap they may be removed; on error they remain only until diagnosis and are then removed. Automatic cleanup is a deployment activity, not a responsibility of the MCP server.
3. Hardened XML parser (external entities and network disabled: `defusedxml`, or `lxml` with `resolve_entities=False, no_network=True`), streaming with `iterparse`, memory freed at every `<offerta>`.
4. New DB → `PRAGMA integrity_check` → checks: offers ≥ 50% of the previous run, no null or duplicate keys, mandatory parameters present, latest PUN recent (warning only).
5. If everything passes: atomic rename, previous version as `offerte.db.prev`. If not: active DB untouched, error recorded in `etl_run`, exit code ≠ 0.
6. Idempotent.

Scheduling (systemd timer, Europe/Rome): offers and parameters once a day; monthly PUN once a month, after the publication of the "Prezzi storici" file. (A possible daily PUN from the GME will follow the official publication time.)

## 9. Cost calculation

Phase A: **estimate of the energy-supply cost**: offer components (energy/spread per band × consumption per band, fixed charges and commercialization); for indexed offers, the index resolved with a scenario PUN. It always returns the assumptions used.

Phase B (after user confirmation): **estimated total cost** with the regulated components from the parameters file (transport, charges, excise, VAT), following the official Portale Offerte methodology, which must be found and cited in the code.

Rules: pure functions, `Decimal`; a non-computable offer (unsupported structure, unknown component) goes into `non_calcolabili` with the reason, never with an invented cost; tests on hand-computed cases and, where possible, compared with the Portale simulator.

## 10. Agent interfaces

A single library and a thin MCP server, which is the only point of contact between agents and the DB. One implementation per operation — validation, limits, errors, output schema — and MCP only translates the protocol format: no duplicated rules. A local CLI can help debugging, but it is not a supported agent interface, is not exposed in production, and does not need contractual parity with MCP. Design guidelines, valid for any harness (even small ones, such as Pi):

- **Structured output, not prose**: JSON with self-explanatory field names and explicit units (`_eur`, `_eur_mwh`, `_kwh`). In the MCP server, declare the output schema where the SDK supports it.
- **Few, well-documented tools**: each tool and parameter description must be enough for an agent to use it without reading anything else (allowed enums, units, examples, limits). Tools are discovered from the documentation.
- **Composable**: stable identifiers (`piva`, `cod_offerta`) returned by one function and accepted by the others; `confronta_offerte` accepts an optional `cod_offerte` list to narrow the comparison.
- **Small output**: hard limits (`n` ≤ 25, `limit` ≤ 50, a character cap with truncation signalled), pagination where needed.
- **Seller text = untrusted data**: in marked fields (e.g. `descrizione_venditore`), never concatenated into instructions or messages generated by the server.
- **Structured errors** (`codice`, `messaggio`), with no stack traces or paths.

MCP functions (stable names, read-only annotation):

- `confronta_offerte(tipo_cliente, consumo_annuo_kwh, ripartizione_fasce?, potenza_kw?, tipo_prezzo?, pun_scenario_eur_mwh?, cod_offerte?, n=10)` → ranking with `costo_annuo_eur`, `dettaglio_componenti`, `ipotesi`, `non_calcolabili`, `dati_aggiornati_al`, `avvertenze`
- `cerca_offerte(venditore?, tipo_cliente?, tipo_prezzo?, indicizzata?, testo?, limit=20)`
- `dettaglio_offerta(piva, cod_offerta)`
- `pun(da, a, aggregazione=mensile)` (the daily PUN is out of scope for now)
- `decodifica(dominio, codice?)`
- `stato_dati()` → last update dates of offers, parameters and PUN, number of offers

The DB is opened with `file:...?mode=ro` and `PRAGMA query_only=ON`. No function accepts free SQL.

Stack: Python, the official `mcp` SDK (FastMCP) with streamable HTTP transport, `uv`, pinned versions; verify the current SDK and MCP specification documentation before implementing.

## 11. Public access and rate limiting

The MCP server is intentionally public and implements no authentication, API key, OAuth, session or credential handling. The private mode uses the same process and the same Compose setup but publishes MCP on loopback only.

When the service is public, `cloudflared` creates the only ingress from the VM and Cloudflare applies per-IP rate limiting, plus TLS and network protections. No application-level rate limiter, Redis or local reverse proxy is added. The server stays stateless; it logs no consumption parameters and no data not needed for diagnosis. `/healthz` requires no authentication and returns only DB readiness.

## 12. Security checklist

- Download from allowlist only, HTTPS, size and timeout limits; hardened XML parser.
- DB swap only after validation; the active DB is never touched on error.
- Read-only interfaces; no free SQL; inputs with hard limits.
- No application authentication; per-IP rate limiting at the gateway and no consumption data in logs.
- Seller text sanitized and marked as untrusted.
- Origin unreachable unless through Cloudflare.
- Errors with no internal detail.

## 13. Verification

- Parser tested on the fixture; calculation functions on hand-computed cases (three equal bands, different bands, fixed charge, indexed with scenario PUN, non-computable).
- Security tests: writing to the DB impossible from the interfaces; per-IP rate limiting verified at the gateway; out-of-limit input rejected; external XML entities not resolved; corrupt or truncated XML does not replace the active DB.
- ETL idempotent.
- `just check` (lint, types, tests) is the single verification command; `just` rebuilds everything from scratch.
