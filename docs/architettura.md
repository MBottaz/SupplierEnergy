# Architettura: database offerte luce e interfacce per agenti

Documento di contesto, stabile nel tempo. Va in `docs/architettura.md`. Gli obiettivi non ancora implementati sono in `docs/goals.md`; i task operativi in `docs/task.md`.

## 1. Obiettivo

Un sistema minimale che:

1. scarica periodicamente le offerte di energia elettrica del mercato libero (XML open data, ~22 MB), il file dei parametri regolati (CSV) e il PUN;
2. li normalizza e li carica in un database SQLite (un solo file);
3. li espone in sola lettura ad **agenti AI** tramite il solo server MCP, con funzioni come `confronta_offerte`. La libreria può avere una CLI locale di debug, ma la CLI non è un'interfaccia per agenti e non viene esposta nel deployment.

Gli utilizzatori sono agenti, non persone: nomi, descrizioni e formati di output vanno pensati per un LLM che li legge.

## 2. Principi

- **Minimalismo**: poche dipendenze, nessun framework pesante, nessun servizio che richieda manutenzione continua.
- **Portabilità**: Linux (Debian stabile come target), FreeBSD per quanto possibile. La prima installazione è su una VM con Docker Compose; il codice non deve dipendere da un provider specifico.
- **Separazione dei privilegi**: ETL (scrive il DB) e interfacce (lo leggono) sono processi distinti con utenti distinti.
- **Il DB è ricostruibile** da zero scaricando di nuovo le fonti. I raw sono staging operativo, non un archivio storico obbligatorio; il DB e lo schema restano portabili come artefatti SQLite.
- **Non indovinare**: codici del tracciato e formule di calcolo vengono dalla documentazione ufficiale.
- **Il calcolo del costo sta in Python**, con `Decimal`, testato.

## 3. Architettura

```
[systemd timer] → etl: fetch → parse → normalizza → offerte.db.new → validazione → rename atomico
                                                              │
                                                    offerte.db (aperto in sola lettura)
                                                              │
                              pacchetto `offerte` (nessun I/O di rete nella libreria)
                               ├── CLI locale opzionale         → solo debug dell'applicazione
                               └── server MCP su 127.0.0.1       → unico accesso degli agenti
                                                              │
        cloudflared (Tunnel: solo connessione in uscita) ←→ Cloudflare (proxy: DDoS, WAF, rate limit per IP) ←→ agenti
```

| Componente | Cosa fa | Cosa NON fa |
|---|---|---|
| `etl` | scarica, valida, parsa, scrive il DB nuovo, swap atomico, registra `etl_run` | non serve richieste, non apre porte |
| libreria `offerte` | query tipizzate e calcolo dei costi (`calc`, funzioni pure) | non accede alla rete |
| CLI locale opzionale | adapter di debug per le funzioni della libreria | non è un'interfaccia per agenti e non fa parte del deployment |
| server MCP | unico accesso degli agenti, espone le funzioni come tool in sola lettura | non scrive il DB, non gestisce autenticazione o sessioni |
| Cloudflare + Tunnel | DDoS, WAF, rate limit per IP, TLS pubblico | non modifica il DB e non richiede un reverse proxy locale |

Un solo pacchetto Python non-ETL, `offerte`: la libreria (query e calcolo) e il
server MCP. Una CLI locale può essere aggiunta come adapter di debug, ma non è
un frontend per agenti né un componente del deployment. La separazione dei
privilegi è a livello di processo, non di namespace.

## 4. Fonti dati (gli URL vanno verificati, non inventati)

1. **Offerte XML**: Portale Offerte di ARERA (open data), elettricità, mercato libero. Trova l'URL ufficiale e il **tracciato ufficiale** con le tabelle di decodifica. Download condizionale (ETag / If-Modified-Since); se lo SHA-256 coincide con quello dell'ultima esecuzione, non fare nulla. Verifica la licenza d'uso.
2. **Parametri CSV**: `PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv`, colonne `nome_parametro,valore,descrizione`, ~100 righe. La data nel nome è la data di riferimento: salvala con i valori.
3. **PUN**: due fonti, entrambe da verificare nei termini d'uso. *Serie mensile* (serve alla maggior parte delle offerte indicizzate): CSV "Prezzi storici - indici a pubblica diffusione" della pagina Open Data del Portale Offerte, colonna `PUN (€/kWh)`, un valore per mese; `python -m etl pun` lo scarica e aggiorna `pun` (serie `PUN_MENSILE`), l'URL non è datato e sta in `etl/pun.py`. *Serie giornaliera*: servizio API del GME (guida tecnica ufficiale di ottobre 2025, con autenticazione: serve una registrazione dell'utente). Alternativa: file della sezione "MGP – Download". Dal 2025 l'indice è il PUN Index GME: verifica la definizione e salva in `pun` quale serie usi. **Fuori scope per ora**: si carica solo la serie mensile; il giornaliero dal GME si aggiunge quando servirà davvero. **Verifica i termini d'uso di entrambe le fonti** (uso commerciale, ridistribuzione) e annotali in `docs/questioni_aperte.md`: vincolano il modo in cui il servizio può essere offerto a terzi.

Molte offerte indicizzate usano la media mensile del PUN, non il giornaliero: leggi la definizione dell'indice (`IDX_PREZZO_ENERGIA`) dal tracciato.

## 5. Strategia di sviluppo del parser

L'XML completo non viene letto dall'agente. Si procede così:

1. Il parser si costruisce dal **tracciato ufficiale** e dalla fixture `tests/fixtures/offerta_estratto.xml` (una sola offerta a prezzo variabile).
2. È **tollerante**: ogni percorso o elemento non previsto finisce in `extra_json` e viene contato in `etl_run.percorsi_sconosciuti`. Non fa mai fallire il caricamento.
3. La validazione sui dati reali avviene **dopo** il primo caricamento dell'XML completo, con query SQL aggregate sul DB (percorsi sconosciuti, valori distinti dei codici, elementi che si ripetono, campi vuoti, intervallo date, duplicati). Il risultato è un riassunto in `docs/validazione_xml.md`.
4. Se la validazione scopre strutture non previste (per esempio come sono rappresentate le offerte a prezzo fisso, di cui la fixture non è un esempio), si estende lo schema e si ricostruisce il DB dai raw.

## 6. Modello dati (SQLite)

Formato "long": fasce F1/F2/F3 e quote fisse sono semplici righe di `componente`.

- `offerta(piva, cod_offerta, nome, descrizione, tipo_mercato, offerta_singola, tipo_cliente, tipo_offerta, tipologia_att_contr, durata, garanzie, idx_prezzo_energia, data_inizio, data_fine, modalita_pagamento, tipo_dispacciamento, url_sito, url_offerta, telefono, extra_json, snapshot_date)`, chiave `(piva, cod_offerta)`
- `componente(piva, cod_offerta, nome, descrizione, tipologia, macroarea, fascia, prezzo, unita_misura, extra_json)`
- `condizione(piva, cod_offerta, tipologia, descrizione, limitante)`
- `codifica(dominio, codice, descrizione)`
- `parametro(nome, valore, descrizione, riferimento)`, chiave `(nome, riferimento)`. I metadati dei parametri (`unita`, `categoria_cliente`, BTA) arrivano in fase B, con una tabella dedicata compilata dalla documentazione ufficiale: non si aggiunge una tabella vuota adesso.
- `pun(data, valore_eur_mwh, serie)`, chiave `(data, serie)`. Due serie previste: `PUN_MENSILE` (media mensile, dal file Prezzi storici del Portale Offerte, caricata da `python -m etl pun`) e, se servirà, `PUN_GIORNALIERO` (dal GME).
- `etl_run(id, inizio, fine, esito, sorgente, sha256, n_offerte, percorsi_sconosciuti, note)`

Normalizzazione:
- date `dd/mm/yyyy_hh:mm:ss` → ISO 8601, fuso Europe/Rome; le query di default filtrano `data_fine >= oggi`;
- prezzi letti con `Decimal`, salvati REAL, con l'unità di misura originale;
- testo libero dei venditori: rimuovi caratteri di controllo e tronca.

Il DB si ricostruisce da zero a ogni esecuzione dall'ultimo raw, copiando dal precedente solo `parametro`, `pun` ed `etl_run`. L'aggiornamento del solo PUN (`python -m etl pun`) non ricostruisce le offerte: parte da una copia del DB in uso, aggiorna `pun` e passa dallo stesso swap atomico, così anche questo comando non modifica mai in place il DB in uso.

## 7. File dei parametri

Dal file `PO_Parametri_Mercato_Libero_E_20260928.csv` (100 righe):

- I nomi seguono uno schema: prefisso della componente (`acc`, `arim`, `asos`, `dis`, `iva`, `pcv`…), categoria cliente (`_d`/`_nd`/`_a`, `_dr`/`_dnr`, `_b1`…`_b6`) e tipo (`_c` energia, `_f` quota fissa, `_p` potenza).
- **Le unità non sono nel file**: convivono €/kWh, €/anno o €/POD/anno, €/kW/anno, importi anomali (`acc_a_h_h` = 4820.0, `gamma` = -73.5737) e adimensionali (`lambda` = 0.1). I metadati (unità, categoria cliente, BTA) si ricaveranno dalla documentazione ufficiale in fase B, non per induzione dai nomi.
- Si caricano sempre tutte le righe così come sono; i metadati arrivano in un secondo passaggio (fase B), così un cambio di schema dei nomi non rompe il caricamento.
- La classificazione BTA (`_b1`…`_b6`) va mappata a potenza/uso del cliente dal documento ufficiale; se non è reperibile, chiedi all'utente. Questa mappatura serve alla fase B, non al caricamento dei parametri.
- Parametri obbligatori controllati dall'ETL (almeno `pcv_a`, `pcv_c`, `iva_a`, `iva_c`, `lambda`): se mancano, lo swap è bloccato.

## 8. ETL

1. Download in cartella temporanea con timeout, limite di dimensione (es. 100 MB), solo host in allowlist, solo HTTPS.
2. Raw salvati temporaneamente in `raw/AAAA-MM-GG/` durante l'ETL. La policy di produzione non richiede conservazione: dopo uno swap riuscito possono essere rimossi; in caso di errore restano solo fino alla diagnosi e poi vengono rimossi. La pulizia automatica è un'attività del deployment, non una responsabilità del server MCP.
3. Parser XML hardened (entità esterne e rete disabilitate: `defusedxml` oppure `lxml` con `resolve_entities=False, no_network=True`), in streaming con `iterparse`, memoria liberata a ogni `<offerta>`.
4. DB nuovo → `PRAGMA integrity_check` → controlli: offerte ≥ 50% dell'esecuzione precedente, nessuna chiave nulla o duplicata, parametri obbligatori presenti, ultimo PUN recente (solo warning).
5. Se tutto passa: rename atomico, versione precedente in `offerte.db.prev`. Se no: DB in uso intatto, errore in `etl_run`, exit code ≠ 0.
6. Idempotente.

Pianificazione (systemd timer, Europe/Rome): offerte e parametri una volta al giorno; PUN mensile una volta al mese, dopo la pubblicazione del file Prezzi storici. (Un eventuale PUN giornaliero dal GME seguirà l'orario di pubblicazione ufficiale.)

## 9. Calcolo del costo

Fase A: **stima della spesa per la materia energia**: componenti dell'offerta (energia/spread per fascia × consumi per fascia, quote fisse e di commercializzazione); per le indicizzate, l'indice risolto con un PUN di scenario. Restituisce sempre le ipotesi usate.

Fase B (dopo conferma dell'utente): **spesa totale stimata** con le componenti regolate del file parametri (trasporto, oneri, accise, IVA), seguendo la metodologia ufficiale del Portale Offerte, che va trovata e citata nel codice.

Regole: funzioni pure, `Decimal`; un'offerta non calcolabile (struttura non supportata, componente sconosciuta) va in `non_calcolabili` con il motivo, mai con un costo inventato; test su casi calcolati a mano e, se possibile, confrontati con il simulatore del Portale.

## 10. Interfacce per agenti

Un'unica libreria e un server MCP sottile, che costituisce l'unico punto di
contatto degli agenti con il DB. Una sola implementazione per operazione —
validazione, limiti, errori, schema di output — e MCP traduce solo il formato
del protocollo: niente regole duplicate. Una CLI locale può essere utile per il
debug, ma non è un'interfaccia supportata per agenti, non è esposta in
produzione e non richiede una parità contrattuale con MCP. Linee guida di
design, valide per qualunque harness (anche piccoli, come Pi):

- **Output strutturato, non prosa**: JSON con campi dai nomi autoesplicativi e unità esplicite (`_eur`, `_eur_mwh`, `_kwh`). Nel server MCP, dichiara lo schema di output dove l'SDK lo supporta.
- **Pochi tool, ben documentati**: la descrizione di ogni tool e di ogni parametro deve bastare a un agente per usarlo senza leggere altro (enum ammessi, unità, esempi, limiti). I tool si scoprono dalla documentazione.
- **Componibili**: identificatori stabili (`piva`, `cod_offerta`) restituiti da una funzione e accettati dalle altre; `confronta_offerte` accetta una lista opzionale `cod_offerte` per restringere il confronto.
- **Output piccolo**: limiti rigidi (`n` ≤ 25, `limit` ≤ 50, tetto sui caratteri con segnalazione del troncamento), paginazione dove serve.
- **Testo dei venditori = dato non fidato**: in campi marcati (es. `descrizione_venditore`), mai concatenato in istruzioni o messaggi generati dal server.
- **Errori strutturati** (`codice`, `messaggio`), senza stack trace né percorsi.

Funzioni MCP (nomi stabili, annotazione di sola lettura):

- `confronta_offerte(tipo_cliente, consumo_annuo_kwh, ripartizione_fasce?, potenza_kw?, tipo_prezzo?, pun_scenario_eur_mwh?, cod_offerte?, n=10)` → classifica con `costo_annuo_eur`, `dettaglio_componenti`, `ipotesi`, `non_calcolabili`, `dati_aggiornati_al`, `avvertenze`
- `cerca_offerte(venditore?, tipo_cliente?, tipo_prezzo?, indicizzata?, testo?, limit=20)`
- `dettaglio_offerta(piva, cod_offerta)`
- `pun(da, a, aggregazione=mensile)` (il PUN giornaliero è fuori scope per ora)
- `decodifica(dominio, codice?)`
- `stato_dati()` → date di ultimo aggiornamento di offerte, parametri e PUN, numero di offerte

Il DB si apre con `file:...?mode=ro` e `PRAGMA query_only=ON`. Nessuna funzione accetta SQL libero.

Stack: Python, SDK ufficiale `mcp` (FastMCP) con transport streamable HTTP, `uv`, versioni pinnate; verifica la documentazione attuale dell'SDK e della specifica MCP prima di implementare.

## 11. Accesso pubblico e rate limiting

Il server MCP è intenzionalmente pubblico e non implementa autenticazione,
API key, OAuth, sessioni o gestione di credenziali. La modalità privata usa lo
stesso processo e lo stesso Compose, ma pubblica MCP solo su loopback.

Quando il servizio è pubblico, `cloudflared` crea l'unico ingresso dalla VM e
Cloudflare applica il rate limit per IP, oltre a TLS e alle protezioni di rete.
Non si aggiunge un rate limiter applicativo, Redis o un reverse proxy locale.
Il server resta stateless; non registra parametri di consumo né dati che non
servono alla diagnosi. `/healthz` non richiede autenticazione e restituisce
solo la readiness del DB.

## 12. Rete e deployment

### 12.1 Layout runtime e configurazione dei container

Il layout runtime previsto per i volumi è:

```text
/var/lib/offerte/db/offerte.db
/var/lib/offerte/db/offerte.db.new
/var/lib/offerte/db/offerte.db.prev
/var/lib/offerte/raw/YYYY-MM-DD/
/var/lib/offerte/db/etl.lock
```

`offerte.db`, `.new` e `.prev` restano nella stessa directory e sullo stesso
volume: l'ETL completa le validazioni e poi usa il rename atomico già previsto.
Database e raw sono directory separate. Il servizio ETL monta entrambe in
lettura/scrittura; il servizio MCP monta solo il database in sola lettura e non
monta i raw. Non esiste un volume auth: il deployment non usa credenziali o
sessioni applicative.

I percorsi e il bind HTTP sono configurabili senza modificare il codice. I
valori di una specifica opzione CLI prevalgono sull'ambiente:

| Variabile | Default | Significato |
|---|---|---|
| `OFFERTE_DB` | `/var/lib/offerte/db/offerte.db` | database attivo |
| `OFFERTE_RAW_DIR` | `/var/lib/offerte/raw` | radice dei raw datati |
| `OFFERTE_PARAMETRI` | non impostata | CSV dei parametri fornito al job ETL |
| `OFFERTE_MCP_HOST` | `127.0.0.1` | interfaccia HTTP MCP, solo loopback in questa fase |
| `OFFERTE_MCP_PORT` | `8000` | porta HTTP MCP; precede la convenzione di piattaforma `PORT` |
| `PORT` | non impostata | fallback della porta per piattaforme HTTP gestite |
| `OFFERTE_MCP_CONSENTI_NON_LOOPBACK` | non impostata | apertura esplicita del bind non-loopback (container) |

L'utente `offerte-etl` è proprietario della directory del database e dei raw;
`offerte-mcp` appartiene al gruppo condiviso di lettura del database. La
protezione effettiva del mount read-only di MCP è responsabilità della
configurazione Docker/systemd, oltre a `mode=ro` e `PRAGMA query_only=ON` nel
codice. Non è previsto un file di credenziali per MCP.

### 12.2 Immagine Docker

`Dockerfile` costruisce una sola immagine multi-stage: la fase di build crea
l'ambiente Python con `uv.lock` (`--locked --no-dev`), mentre la fase runtime
contiene solo l'ambiente virtuale, i pacchetti `etl` e `offerte` e le directory
runtime. L'immagine usa basi Python e uv fissate per digest, non include test,
raw, database locali o strumenti di sviluppo, e parte come utente non-root
`offerte-mcp`.

L'entrypoint è `python` con default `-m offerte.mcp`; il job batch seleziona lo
stesso artefatto con `-m etl scarica` e la configurazione Docker seleziona
`offerte-etl` senza duplicare l'immagine. La limitazione del filesystem a sola
lettura, `no-new-privileges`, il drop delle capability e il `tmpfs` per `/tmp`
sono applicati dai servizi Docker, non implicitamente dal processo applicativo.

### 12.3 Servizi Docker Compose

`compose.yml` avvia i due processi dalla stessa immagine:

- `offerte-mcp` (long-running, utente `offerte-mcp`) monta il database in sola
  lettura e non monta i raw; pubblica la porta solo su
  `127.0.0.1:${OFFERTE_MCP_PORT:-8000}:8000`; ha filesystem di sola lettura,
  `tmpfs` per `/tmp`, `no-new-privileges` e nessuna capability; usa
  `restart: unless-stopped`. Nel container ascolta su `0.0.0.0`, perché solo così
  la porta pubblicata raggiunge il processo: l'apertura non-loopback è resa
  esplicita da `OFFERTE_MCP_CONSENTI_NON_LOOPBACK`, mai implicita. Un healthcheck
  esegue `python -m offerte.mcp --verifica`.
- `offerte-etl` (batch, utente `offerte-etl`, profilo `etl`) monta database e raw
  in lettura/scrittura, usa `restart: "no"` e termina al termine dell'ETL. Non
  parte con `docker compose up` e non è avviato da MCP.

### 12.4 Lock ETL e readiness

Due ETL sovrapposti non devono mai leggere e sostituire lo stesso database. Il
lock è un file `etl.lock` nella directory del database (`flock` esclusivo non
bloccante), acquisito prima della lettura e dello swap: vive sullo stesso volume
persistente, è condiviso fra container e viene rilasciato anche in caso di
errore o terminazione. Se è già tenuto, l'ETL esce con codice 3 e un errore
strutturato `etl_in_corso`, senza toccare il database.

La readiness del processo MCP è `python -m offerte.mcp --verifica`: esce 0 se il
database è leggibile in sola lettura, 1 se manca, 2 se non è leggibile. Non crea
mai un database vuoto: un volume non inizializzato resta un errore controllato,
non un database silenziosamente vuoto.

- Una VM Linux (Debian stabile) in un provider UE scelto dall'utente. Aggiornamenti di sicurezza automatici, SSH con chiave. Kubernetes e altri orchestratori non fanno parte della prima fase.
- **Cloudflare davanti come proxy**: DDoS, WAF e rate limit per IP. L'origine non deve essere raggiungibile direttamente (altrimenti la protezione si aggira). **Solo Cloudflare Tunnel** (`cloudflared`), preferibilmente come servizio Compose: la VM apre solo connessioni in uscita, nessuna porta pubblica, il server MCP ascolta su `127.0.0.1` in HTTP semplice. Niente reverse proxy locale (Caddy) e nessuna 443 pubblica.
  - Nota: nelle chiamate MCP (POST JSON-RPC dinamiche) la cache non serve; il valore di Cloudflare è nella mitigazione di DDoS e abusi.
- Utenti di sistema separati: `offerte-etl` (scrive in `/var/lib/offerte`) e `offerte-mcp` (legge il DB). Unit systemd con hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `ReadWritePaths` minimi, `MemoryMax`.
- Persistenza VPS: preferire directory host esplicite (`/var/lib/offerte/db`, `/var/lib/offerte/raw`) ai volumi Docker opachi, per semplificare backup e restore. In entrambi i casi DB attivo, `.new`, `.prev` e lock devono restare sullo stesso filesystem.
- Backup: il DB è ricostruibile; salvare almeno configurazione e database attivo/precedente. I raw non sono conservati come requisito funzionale.
- `/healthz` è una rotta HTTP senza autenticazione e senza dati applicativi: restituisce 200 solo quando il DB è leggibile, altrimenti 503; serve a Docker, systemd e futuri provider gestiti.

### 12.5 Decisione di deployment e compatibilità futura con Manufact

La prima produzione è **VPS + Docker Compose**. Il traffico iniziale è previsto
basso, ma può avere picchi brevi e non prevedibili perché i client sono agenti.
La VM offre il percorso più semplice per il DB SQLite, lo swap atomico e il
restore; Cloudflare e il rate limit per IP limitano gli abusi. Non si
introducono MySQL, PostgreSQL, Parquet, Redis, Kubernetes o code di messaggi.

La migrazione futura a un servizio gestito/serverless, incluso Manufact Cloud,
resta possibile se i confini del codice rimangono questi:

- la logica applicativa (`offerte.ricerca`, futuro `calc`) riceve una connessione
  SQLite e non conosce filesystem, Docker, Cloudflare o il provider;
- `offerte.mcp` resta un adapter MCP sottile; l'endpoint HTTP è `/mcp`, mentre
  `/healthz` non autenticato espone solo la readiness;
- il processo HTTP ascolta su `0.0.0.0` solo quando il deployment lo richiede e
  usa `OFFERTE_MCP_PORT`, con fallback alla variabile convenzionale `PORT`;
- nessun dato importante viene conservato nel filesystem locale del processo
  MCP: su una piattaforma senza storage persistente il DB futuro sarà un
  artefatto SQLite immutabile in Object Storage, scaricato in `/tmp` e aperto
  in sola lettura;
- la sorgente del DB va isolata dietro un confine futuro (`local path` nella
  VPS, `object artifact` nel serverless) senza duplicare query o calcoli;
- il rate limit per IP deve stare al gateway; lo stato locale dell'applicazione
  non può essere usato come limite globale se esistono più istanze;
- il processo deve chiudersi correttamente su `SIGINT`: i client MCP devono
  poter riconnettersi se una piattaforma sostituisce una deployment.

Manufact Cloud documenta il deploy da GitHub con runtime Python oppure con un
`Dockerfile` personalizzato, start command, porta e variabili per ambiente; il
`Dockerfile` attuale è quindi una base compatibile, ma la configurazione di
produzione dovrà selezionare esplicitamente il trasporto HTTP, per esempio:

```text
start command: python -m offerte.mcp --trasporto http
port: 3000
OFFERTE_MCP_HOST=0.0.0.0
OFFERTE_MCP_PORT=3000
OFFERTE_MCP_CONSENTI_NON_LOOPBACK=1
```

La modalità `stdio` resta il default per i client locali e non va sostituita.
Le preview Manufact devono usare un DB non-produttivo; le variabili e i segreti
vanno configurati nella piattaforma, mai committati nel repository. I deploy
automatici vanno subordinati a `just check` e a uno smoke test MCP.

Prima di migrare occorre inoltre validare il trasporto Streamable HTTP con le
sessioni MCP e l'eventuale interruzione controllata degli stream durante un
deploy. La documentazione Manufact indica una finestra massima di shutdown di
300 secondi e richiede che i client possano riconnettersi.

Fonti ufficiali consultate:

- [Manufact Cloud quickstart](https://docs.manufact.com/dashboard/quickstart)
- [Manufact build e deployment](https://docs.manufact.com/dashboard/deployments)
- [Manufact environment variables](https://docs.manufact.com/dashboard/environment-variables)
- [Manufact server settings](https://docs.manufact.com/dashboard/settings)
- [MCP Python SDK: deploy e scale](https://py.sdk.modelcontextprotocol.io/run/deploy/)
- [MCP Python SDK: custom health route](https://py.sdk.modelcontextprotocol.io/run/asgi/)

Questa compatibilità è un vincolo di progettazione futuro, non un deployment
Manufact già attivo. L'adapter Object Storage e l'eventuale gestione condivisa
delle chiavi saranno task separati quando la migrazione sarà realmente utile.

## 13. Checklist di sicurezza

- Download solo da allowlist, HTTPS, limiti di dimensione e timeout; parser XML hardened.
- Swap del DB solo dopo validazione; DB in uso mai toccato in caso di errore.
- Interfacce in sola lettura; nessun SQL libero; input con limiti rigidi.
- Nessuna autenticazione applicativa; rate limit per IP al gateway e nessun dato
  di consumo nei log.
- Testo dei venditori sanificato e marcato come non fidato.
- Origine non raggiungibile se non attraverso Cloudflare.
- Errori senza dettagli interni.

## 14. Verifica

- Parser testato sulla fixture; funzioni di calcolo su casi calcolati a mano (tre fasce uguali, fasce diverse, quota fissa, indicizzata con PUN di scenario, non calcolabile).
- Test di sicurezza: scrittura sul DB impossibile dalle interfacce; rate limit per IP verificato al gateway; input fuori limite rifiutato; entità XML esterne non risolte; XML corrotto o troncato non sostituisce il DB in uso.
- ETL idempotente.
- `just check` (lint, tipi, test) è il comando unico di verifica; `just` ricrea tutto da zero.
