# Unità systemd e configurazione di deploy (fase 6).

Il deployment prevede **solo Cloudflare Tunnel** (`cloudflared`): la VM apre
solo connessioni in uscita, nessuna porta pubblica e nessun reverse proxy
locale (docs/architettura.md §12).

Serviranno unit systemd con hardening per ETL e server MCP, con utenti di
sistema separati (`offerte-etl` scrive, `offerte-mcp` legge).
