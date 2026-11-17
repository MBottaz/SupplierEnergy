# Documentation index

The root `README.md` is the overview, commands and current state; `AGENTS.md` holds the working rules. This folder holds the detail.

## System design

- `architecture.md` — stable design: objective, principles, data model, ETL, cost calculation, agent interfaces, security and verification. Align the code to it.
- `cerca_offerte_contract.md` — contract of the implemented `cerca_offerte` function and MCP tool.
- `xml_validation.md` — aggregate validation of the real XML loaded by the ETL.
- `deployment.md` — Docker image, Compose services, deploy/shut-down runbook (local machine and VPS), runtime layout, lock and readiness, target VPS + Cloudflare, future Manufact compatibility.

## Open points and next work

- `open_questions.md` — unresolved codes, formulas, sources and terms of use.
- `roadmap.md` — objectives not yet implemented and their operational tasks.

## Reference data

- `PO_Parametri_Mercato_Libero_E_20261014.csv` — parameter CSV snapshot used by the `etl-*` commands.
