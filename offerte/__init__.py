"""Libreria `offerte`: query tipizzate e calcolo dei costi (sola lettura).

Un solo pacchetto per tutto ciò che non è ETL. I frontend sono sottomoduli e
importano le librerie pesanti solo quando servono (fase 4/5):

- query e calcolo (funzioni pure, `Decimal`) — nessun I/O di rete;
- `offerte.cli` → CLI `python -m offerte <comando> --json` per agenti locali;
- `offerte.mcp` → server MCP `python -m offerte.mcp` per agenti remoti;
- `offerte.auth` → gestione delle API key (`authctl`).

Il pacchetto non scrive mai il DB: ogni accesso è in sola lettura.
"""
