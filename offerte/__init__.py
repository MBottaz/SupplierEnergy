"""Libreria `offerte`: query tipizzate e calcolo dei costi (sola lettura).

Un solo pacchetto per tutto ciò che non è ETL. I frontend sono sottomoduli e
importano le librerie pesanti solo quando servono (fase 4/5):

- query e calcolo (funzioni pure, `Decimal`) — nessun I/O di rete;
- `offerte.mcp` → server MCP `python -m offerte.mcp`, unico punto di contatto per gli agenti;
- una eventuale CLI locale è solo un adapter di debug e non è un'interfaccia per agenti.

Il pacchetto non scrive mai il DB: ogni accesso è in sola lettura.
"""
