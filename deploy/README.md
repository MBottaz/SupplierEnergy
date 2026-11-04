# Deployment

Contesto: `docs/architettura.md` §12; stato e comandi nel `README.md` di radice.
Questa cartella raccoglie la configurazione di esecuzione; non contiene segreti.

## Topologia Docker

Due processi, una sola immagine (`Dockerfile`), due utenti non-root:

| Servizio | Utente | Filesystem | Rete | Vita |
| --- | --- | --- | --- | --- |
| `offerte-mcp` | `offerte-mcp` | root `read_only`, `tmpfs /tmp`, database in sola lettura, niente raw | porta pubblicata solo su `127.0.0.1` | long-running (`restart: unless-stopped`) |
| `offerte-etl` | `offerte-etl` (proprietario di database e raw) | root `read_only`, database e raw in lettura/scrittura | solo in uscita per i download | batch, profilo `etl`, non parte con `up` |

Volumi nominati: `offerte-db` (database, `.new`, `.prev`, `etl.lock`) e
`offerte-raw` (raw datati). Il CSV dei parametri è montato in sola lettura
finché non esiste il download automatico; il nome del file porta la data di
riferimento e va conservato. Entrambi i servizi aggiungono
`no-new-privileges` e azzerano le capability.

```bash
docker compose build
docker compose up -d offerte-mcp
docker compose --profile etl run --rm offerte-etl
```

`deploy/compose.local.yml` è l'override per la fixture locale: bind mount di
`build/`, nessuna rete, UID/GID host e `:z` per SELinux.

## Ancora da fare (fase successiva)

- timer systemd che esegue l'ETL con una sola esecuzione alla volta e retry;
- `cloudflared` come unico ingresso, quando ci sarà l'autenticazione: solo
  Tunnel, nessuna porta pubblica, nessun reverse proxy locale;
- unit systemd con hardening per MCP ed ETL.
