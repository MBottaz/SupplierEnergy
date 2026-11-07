# Obiettivi da implementare

Il primo obiettivo è una prova funzionale dell'MVP già presente: avviare MCP in
**Streamable HTTP** e collegarlo a un LLM. Non si implementano nuove funzioni
prima della prova.

Contesto stabile in `docs/architettura.md`; task operativi in `docs/task.md`;
stato e comandi in `README.md`.

## Decisioni di prodotto e sicurezza

MCP è l'unico punto di contatto fra l'LLM e il database. Nessun agente riceve
accesso a shell, filesystem, SQLite o CLI. Nessun tool accetta codice, SQL
libero o comandi da eseguire.

Il server applicativo resta non autenticato. Non verranno implementati API key,
`authctl`, OAuth, sessioni o un archivio di credenziali. La CLI non è
un'interfaccia per agenti: se servirà, sarà soltanto un adapter locale di debug.

## Stato utilizzabile per la prova

È già disponibile:

- ETL manuale di offerte XML, parametri CSV e PUN mensile;
- database SQLite letto da MCP in sola lettura;
- tool `cerca_offerte` nella libreria e nel server MCP;
- trasporto Streamable HTTP su loopback;
- readiness `/healthz`;
- immagine Docker non-root e Compose;
- fixture locale e test di integrazione HTTP;
- `just check`.

Il primo test usa questa superficie senza aggiungere tool o calcoli.

## Obiettivo 1 — Prova funzionale MCP + LLM

### Passi necessari

1. Preparare un database già valido, oppure caricare la fixture con
   `just etl-fixture`.
2. Avviare l'ETL fixture e il servizio `offerte-mcp` con il Compose locale.
3. Verificare `/healthz` e i test HTTP già presenti.
4. Rendere il servizio raggiungibile dal LLM tramite un Tunnel temporaneo verso
   `127.0.0.1:8000`, senza pubblicare direttamente la porta MCP.
5. Configurare il client MCP dell'LLM con l'endpoint `/mcp` in Streamable HTTP.
6. Verificare discovery e chiamata reale di `cerca_offerte`.

### Criterio di completamento

L'LLM si connette all'endpoint Streamable HTTP, scopre `cerca_offerte`, esegue
una chiamata e riceve una risposta strutturata. `just check`, Compose config,
readiness e test HTTP passano.

Il Tunnel temporaneo è soltanto per la prova: l'endpoint è pubblico e senza
autenticazione, quindi non va usato per dati o traffico di terzi.

## Dopo la prova funzionale

Solo se la prova è riuscita e si decide di continuare, affrontare le attività
operative seguenti:

- download automatico del CSV dei parametri;
- bootstrap idempotente della VM;
- directory host definitive e retention dei raw;
- timer systemd giornalieri/mensili, lock e retry ETL;
- Tunnel nominato e configurazione Cloudflare permanente;
- rate limiting per IP;
- backup, restore, rollback e test su macchina pulita;
- runbook operativo, monitoraggio e gestione dei rilasci;
- verifica della licenza prima di offrire il servizio a terzi.

Queste attività migliorano la produzione, ma non sono necessarie per la prima
prova MCP–LLM.

## Funzioni post-MVP

Dopo la stabilizzazione del deployment minimo si potranno valutare, nell'ordine
che verrà concordato:

- `dettaglio_offerta(piva, cod_offerta)`;
- `pun(da, a, aggregazione="mensile")`;
- `decodifica(dominio, codice?)`;
- `stato_dati()`;
- `confronta_offerte`;
- stima della sola materia energia con `Decimal` e risultati
  `non_calcolabile` espliciti;
- CLI locale per debug, mai per agenti o produzione.

## Fuori scope

- autenticazione API key, `authctl`, OAuth, JWKS e identity provider;
- accesso dell'LLM alla shell, al filesystem, al DB o alla CLI;
- SQL libero, codice o comandi eseguiti tramite MCP;
- spesa totale con componenti regolate (fase B);
- PUN giornaliero dal GME;
- Kubernetes, database server, Redis, code, reverse proxy locale e stack
  separati di metriche/alerting.

## Regola di lavoro

Un task alla volta, piccolo e verificabile. Prima della prova non si aggiungono
feature: si usano i comandi e il codice già presenti. Dopo la prova, ogni
attività operativa o funzionale viene introdotta separatamente e verificata con
`just check` e il test pertinente.
