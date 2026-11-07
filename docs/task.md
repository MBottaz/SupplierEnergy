# Task: deployment funzionale minima dell'MVP

L'obiettivo immediato non è una produzione autonoma e hardened. È avviare il
server MCP già presente, via **Streamable HTTP**, e collegarlo a un LLM per
provare il tool esistente `cerca_offerte`.

Non si aggiungono tool, calcolo costi, autenticazione o CLI. Il DB deve essere
un artefatto già caricato; l'automazione ETL può essere eseguita manualmente
per preparare il test.

## Confini dell'MVP di prova

- MCP è l'unico punto di contatto per l'LLM.
- L'LLM non riceve shell, filesystem, SQLite o CLI.
- Il solo tool disponibile è `cerca_offerte`.
- Il server apre il DB in sola lettura.
- L'accesso HTTP locale è pubblicato su `127.0.0.1:8000`.
- Per un LLM remoto si usa temporaneamente un Tunnel verso quella porta.
- Il Tunnel di prova non è una configurazione di produzione: l'endpoint è
  pubblico e non autenticato; non usarlo per dati o traffico di terzi.

## Passi strettamente necessari prima della prova

### 1. Preparare un database valido

Usare un DB già prodotto oppure caricare la fixture, senza implementare nuovo
codice. Per eseguire l'ETL della fixture dentro l'immagine Docker:

```bash
docker compose -f compose.yml -f deploy/compose.local.yml run --build --rm offerte-etl
```

In alternativa è sufficiente `just etl-fixture` se si vuole preparare il DB
localmente. La fixture serve a verificare avvio, discovery e chiamata del tool.
È scaduta, quindi può restituire zero offerte con il filtro di validità
predefinito. Per risultati non vuoti usare un DB prodotto da dati reali già
disponibili.

### 2. Avviare MCP in Streamable HTTP

Per la prova locale con la fixture:

```bash
docker compose -f compose.yml -f deploy/compose.local.yml up --build -d offerte-mcp
```

Il servizio ascolta nel container su HTTP, ma la porta dell'host resta
pubblicata solo su loopback.

### 3. Verificare la readiness e il protocollo

```bash
curl -fsS http://127.0.0.1:8000/healthz
just test
```

`just test` verifica anche discovery del tool, chiamate in-memory, integrazione
stdio e integrazione HTTP locale. La readiness deve rispondere solo se il DB è
leggibile; il server non deve creare un DB vuoto.

### 4. Rendere raggiungibile il server dal LLM

Se il LLM è remoto e non può raggiungere la macchina direttamente, avviare
temporaneamente un Tunnel verso la porta già pubblicata su loopback:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Usare nel client MCP dell'LLM l'URL fornito da `cloudflared`, aggiungendo il
percorso `/mcp`, per esempio:

```text
https://<nome-temporaneo>.trycloudflare.com/mcp
```

Non pubblicare la porta 8000 direttamente su Internet e non impostare il bind
non-loopback dell'applicazione per questa prova.

### 5. Eseguire la prova end-to-end

Dal client LLM:

1. connettersi all'endpoint Streamable HTTP `/mcp`;
2. verificare la discovery di `cerca_offerte`;
3. invocare `cerca_offerte` con un filtro semplice;
4. verificare che la risposta sia strutturata e che eventuali errori siano
   restituiti come risultati controllati;
5. verificare che il container MCP non abbia modificato il DB.

La prova è riuscita quando l'LLM completa discovery e chiamata di
`cerca_offerte` attraverso Streamable HTTP.

### 6. Arrestare il test

```bash
docker compose -f compose.yml -f deploy/compose.local.yml down
```

Chiudere il processo `cloudflared` al termine della prova.

## Spostato dopo la prova funzionale

Queste attività non devono bloccare il primo collegamento LLM-MCP e saranno
affrontate solo se il test è utile:

- download automatico del CSV dei parametri;
- timer systemd e retry ETL;
- bootstrap idempotente di una VM di produzione;
- Tunnel nominato e configurazione Cloudflare permanente;
- rate limiting per IP;
- backup, restore, rollback e test periodici su macchina pulita;
- runbook operativo completo e osservabilità;
- verifica della licenza prima di offrire il servizio a terzi;
- directory host definitive, retention raw e gestione completa dei release;
- `dettaglio_offerta`, `pun`, `decodifica`, `stato_dati`;
- `confronta_offerte` e calcolo dei costi;
- CLI locale di debug, solo se sarà utile agli sviluppatori.

## Criterio di chiusura della prova

Prima di considerare l'MVP funzionalmente provato devono passare:

```bash
just check
docker compose -f compose.yml -f deploy/compose.local.yml config
```

Inoltre devono riuscire la readiness locale, la discovery MCP e una chiamata
reale a `cerca_offerte` dall'LLM tramite l'endpoint Streamable HTTP.

## Fuori scope

- autenticazione API key, `authctl`, OAuth, JWKS e identity provider;
- accesso dell'LLM alla shell, al filesystem, al DB o alla CLI;
- SQL libero, codice o comandi eseguiti tramite MCP;
- nuovi tool o nuove formule di calcolo;
- PUN giornaliero, fase B e deployment Kubernetes/database server.
