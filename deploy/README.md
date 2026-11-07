# Deployment

Contesto: `docs/architettura.md` §12; stato e comandi nel `README.md` di radice.
Questa cartella raccoglie la configurazione di esecuzione; non contiene segreti.

Il primo obiettivo è una prova funzionale del server MCP già presente, via
Streamable HTTP e con un LLM. Non è ancora la procedura di produzione: non
include scheduling, backup, restore o rate limiting permanente.

## Topologia Docker della prova MVP

La prima produzione usa una sola VM Debian e Docker Compose. Non usa Kubernetes,
un database server o un processo scheduler dentro un container. Due processi,
una sola immagine (`Dockerfile`), due utenti non-root:

| Servizio | Utente | Filesystem | Rete | Vita |
| --- | --- | --- | --- | --- |
| `offerte-mcp` | `offerte-mcp` | root `read_only`, `tmpfs /tmp`, database in sola lettura, niente raw | porta pubblicata solo su `127.0.0.1` | long-running (`restart: unless-stopped`) |
| `offerte-etl` | `offerte-etl` (proprietario di database e raw) | root `read_only`, database e raw in lettura/scrittura | solo in uscita per i download | batch, profilo `etl`, non parte con `up` |

Il Compose locale usa volumi nominati: `offerte-db` (database, `.new`, `.prev`,
`etl.lock`) e `offerte-raw` (raw datati). In produzione sono preferibili directory
host esplicite sotto `/var/lib/offerte/`, perché rendono backup e restore del
file SQLite immediati. Il CSV dei parametri è montato in sola lettura finché non
esiste il download automatico; il nome del file porta la data di riferimento e
va conservato. I raw sono staging e non devono essere conservati come archivio
storico: la pulizia dopo il job riuscito è parte del deployment. Entrambi i
servizi aggiungono `no-new-privileges` e azzerano le capability.

```bash
docker compose build
docker compose up -d offerte-mcp
docker compose --profile etl run --rm offerte-etl
```

`deploy/compose.local.yml` è l'override per la fixture locale: bind mount di
`build/`, nessuna rete, UID/GID host e `:z` per SELinux.

## Prova Streamable HTTP con un LLM

Dopo aver caricato un DB valido, avviare il servizio con il Compose locale:

```bash
docker compose -f compose.yml -f deploy/compose.local.yml run --build --rm offerte-etl
docker compose -f compose.yml -f deploy/compose.local.yml up --build -d offerte-mcp
curl -fsS http://127.0.0.1:8000/healthz
```

Per un LLM remoto, usare soltanto durante la prova un Tunnel temporaneo:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Configurare nel client MCP l'URL restituito con il suffisso `/mcp`, per esempio
`https://<nome-temporaneo>.trycloudflare.com/mcp`. La porta MCP non deve essere
pubblicata direttamente su Internet. Il Tunnel temporaneo è pubblico e senza
autenticazione: chiuderlo al termine della prova e non usarlo per traffico di
terzi.

## Operatività post-prova

Dopo la prova funzionale si potranno aggiungere, separatamente:

- timer systemd, lock, retry e hardening operativo;
- Tunnel nominato e rate limiting Cloudflare per IP;
- backup, restore e rollback delle directory host e del DB attivo/precedente;
- verifica della licenza prima di offrire il servizio a terzi;
- runbook e smoke test su una VM pulita.

## Compatibilità futura con Manufact Cloud

Manufact non è il deployment iniziale. Il repository resta però adatto a una
futura migrazione perché il provider può usare il `Dockerfile` o il runtime
Python, configurare start command, porta e variabili per ambiente. Anche lì il
servizio resta pubblico e senza autenticazione applicativa; il rate limiting
va configurato al gateway del provider.

La configurazione futura dovrà avviare HTTP, non stdio:

```text
python -m offerte.mcp --trasporto http
OFFERTE_MCP_HOST=0.0.0.0
OFFERTE_MCP_PORT=3000
OFFERTE_MCP_CONSENTI_NON_LOOPBACK=1
```

Una deployment Manufact non può assumere che `/var/lib/offerte/db` o `/raw`
siano persistenti. Prima di usarla servirà un adapter che pubblichi un artefatto
SQLite validato in storage condiviso e lo scarichi nel filesystem temporaneo del
server MCP. Le preview devono usare dati e segreti separati dalla produzione.
I dettagli, i confini del codice e le fonti ufficiali sono in
`docs/architettura.md` §12.5.
