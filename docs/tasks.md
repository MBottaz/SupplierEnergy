# Task di implementazione: server MCP minimale per la ricerca delle offerte

## 1. Obiettivo della prima iterazione

Implementare e verificare lo stack minimo per esporre le offerte tramite MCP, senza
introdurre ancora calcolo dei costi, autenticazione o funzionalità non necessarie.

Il server deve esporre un solo tool di sola lettura:

```text
cerca_offerte
```

Il tool deve permettere a un agente di filtrare le offerte presenti nel database
SQLite, per esempio per fornitore, area geografica, tipo di cliente e tipo di
offerta, e deve restituire un JSON piccolo e strutturato.

La prima validazione deve dimostrare che:

1. il database viene aperto solo in lettura;
2. il server MCP parte correttamente;
3. un client MCP può scoprire il tool;
4. il client può invocarlo con filtri validi;
5. input non validi o risultati oltre i limiti vengono gestiti senza eccezioni
   interne esposte all'agente;
6. il server non implementa né calcolo né scrittura dei dati.

---

## 2. Fuori scope

Non implementare in questa iterazione:

- `confronta_offerte`;
- qualsiasi calcolo di costo o uso di `Decimal` per il calcolo;
- `dettaglio_offerta` come tool separato;
- gestione del PUN come tool;
- `decodifica` come tool;
- `stato_dati` come tool;
- autenticazione API key;
- OAuth, JWKS o identity provider;
- rate limiting applicativo;
- Cloudflare Tunnel, systemd e deployment;
- modifica dello schema SQLite;
- SQL libero fornito dal client;
- download o accesso alla rete dalla libreria o dal server;
- applicazione di sconti, promozioni, componenti regolate o imposte.

Il trasporto HTTP locale può essere aggiunto dopo la validazione del trasporto
stdio. In ogni caso il server di questa iterazione non deve essere configurato
per ascoltare su interfacce pubbliche.

---

## 3. Vincoli da rispettare

### Dati e sicurezza

- Il database deve essere aperto con URI SQLite `mode=ro`.
- La connessione deve impostare `PRAGMA query_only=ON`.
- Nessuna funzione esposta deve accettare SQL o frammenti SQL.
- Le query devono essere parametrizzate.
- Non usare dati provenienti dal testo delle offerte come istruzioni.
- Il testo libero restituito deve essere chiaramente marcato come dato non
  fidato.
- Gli errori restituiti al client non devono contenere stack trace, percorsi
  locali o dettagli interni non necessari.
- Non registrare nei log parametri di consumo, token o segreti. In questa
  iterazione non sono previsti token.
- Il server non deve modificare il database neppure in caso di errore.

### Progetto

- Mantenere un unico pacchetto non-ETL: `offerte`.
- Tenere separati il livello di query e l'adattatore MCP.
- Il futuro frontend CLI e il futuro server completo dovranno poter riusare la
  stessa funzione applicativa di ricerca.
- Non duplicare la logica di validazione tra libreria e server.
- Aggiungere una dipendenza MCP solo dopo aver verificato la documentazione
  corrente dell'SDK ufficiale; la versione deve essere pinnata in
  `pyproject.toml` e `uv.lock`.
- Non aggiungere framework web o dipendenze non necessarie oltre all'SDK MCP.
- Scrivere prima i test del comportamento atteso e poi l'implementazione.
- Alla fine di ogni task eseguire il controllo indicato.
- Prima del commit aggiornare `README.md` se cambiano comandi, struttura o
  comportamento del repository.

---

## 4. Contratto funzionale di `cerca_offerte`

Il contratto definitivo deve essere documentato nella descrizione del tool MCP,
nei test e nell'eventuale funzione applicativa condivisa.

### Filtri minimi

Prevedere questi filtri opzionali, con nomi espliciti:

- `fornitore`: corrispondenza esatta con `offerta.piva`.
  Il modello dati attuale non contiene il nome commerciale del fornitore: non
  inventare un campo `nome_fornitore`. Se l'utente deve cercare per nome, questa
  limitazione deve essere dichiarata nell'output o nella documentazione del tool.
- `regione`: valore presente nei dati geografici normalizzati in `extra_json`.
- `provincia`: valore presente in `extra_json`.
- `comune`: valore presente in `extra_json`.
- `tipo_cliente`: codice del tracciato, per esempio `01` o `02`.
- `tipo_offerta`: codice del tracciato, per esempio `01`, `02` o `04`.
- `indicizzata`: filtro booleano basato sulla presenza di
  `idx_prezzo_energia`.
- `testo`: ricerca limitata nei campi testuali dell'offerta, almeno `nome` e
  `descrizione`.
- `limit`: numero massimo di risultati, default 20, massimo 50.

Il tool può esporre alias più descrittivi, ma il mapping verso le colonne e i
percorsi JSON deve essere esplicito e testato.

### Geografia

La validazione deve verificare come sono rappresentati in `extra_json` i valori
`REGIONE`, `PROVINCIA` e `COMUNE` e deve gestire sia un valore singolo sia una
lista di valori, perché alcuni percorsi XML si ripetono.

La ricerca geografica deve essere:

- case-insensitive in modo deterministico;
- parametrizzata;
- limitata ai percorsi geografici già raccolti dall'ETL;
- priva di interpretazioni geografiche aggiuntive o geocoding.

Se la versione di SQLite disponibile non rende affidabile la ricerca su liste
JSON con una query diretta, è ammesso selezionare un insieme candidato limitato
e filtrare in Python, purché il limite massimo e il costo dell'operazione siano
controllati e documentati. Non è ammesso caricare senza limite l'intero DB in
memoria per ogni richiesta.

### Validità temporale

Per default la ricerca deve seguire la regola del progetto per le offerte
pubblicate: escludere le offerte con `data_fine` precedente a oggi.

Se si decide di filtrare anche `data_inizio`, la scelta deve essere esplicitata
nel contratto, nei test e nella descrizione del tool; non deve essere una
conseguenza implicita dell'implementazione.

### Risultato

Ogni risultato deve contenere almeno:

- `piva`;
- `cod_offerta`;
- `nome_offerta`;
- `descrizione_offerta` in un campo marcato come testo non fidato;
- `tipo_cliente`;
- `tipo_offerta`;
- `indicizzata`;
- `data_inizio`;
- `data_fine`;
- le informazioni geografiche disponibili e pertinenti al filtro.

Il contenitore della risposta deve contenere inoltre:

- `risultati`;
- `numero_risultati`;
- `limit`;
- `troncato`;
- `dati_aggiornati_al`, derivato dal database;
- `avvertenze`, quando un filtro o un campo non è disponibile nel modello.

L'ordinamento deve essere stabile, per esempio per `piva`, `cod_offerta`, e deve
essere definito nei test.

### Errori

Gli input fuori contratto devono produrre un errore strutturato con almeno:

```json
{
  "codice": "input_non_valido",
  "messaggio": "..."
}
```

Gestire almeno:

- `limit` minore di 1 o maggiore di 50;
- tipi JSON errati;
- stringhe oltre la lunghezza massima stabilita;
- codici con formato non valido quando il formato è noto;
- database mancante o non leggibile;
- filtro non supportato.

Il messaggio non deve includere SQL, stack trace o percorsi interni.

---

## 5. Task operativi

### T1 — Verifica dello stack MCP e definizione del contratto

**Obiettivo**

Verificare la versione corrente dell'SDK ufficiale MCP compatibile con Python
3.11 e definire il modo minimo per:

- dichiarare un tool;
- avviare il trasporto stdio;
- avviare, in un secondo momento, il trasporto HTTP streamable locale;
- usare il client/test client ufficiale nei test.

**Vincoli**

- Consultare la documentazione corrente dell'SDK prima di codificare.
- Non introdurre una propria astrazione MCP o un framework web.
- Pinnare la versione scelta.
- Il contratto di `cerca_offerte` deve essere scritto prima del server.

**Controllo**

- Il progetto deve poter installare l'SDK con `uv sync`.
- Deve esistere almeno un test minimale che istanzia il server e verifica la
  scoperta del tool, senza ancora interrogare il database.
- `just lint`, `just types` e il test aggiunto devono passare.

**Stato: completato.** SDK ufficiale verificato sulla documentazione corrente:
`mcp==2.3.0` (linea v2, Python ≥ 3.10, `MCPServer`, trasporti stdio e streamable
HTTP, client in-memory per i test). Pinnato in `pyproject.toml` e `uv.lock`.
Contratto scritto in `docs/contratto_cerca_offerte.md`. Aggiunti
`offerte/mcp.py` (scheletro del server con l'unico tool `cerca_offerte`, corpo
ancora non collegato alla libreria) e `tests/test_mcp_server.py` (scoperta del
tool e schema degli input via client in-memory). `just check` verde.

---

### T2 — Livello di accesso read-only al database

**Obiettivo**

Creare il componente della libreria `offerte` che apre il database in sola
lettura e fornisce alla funzione di ricerca i dati necessari.

**Vincoli**

- Nessuna logica MCP nel livello database.
- Connessione tramite `mode=ro` e `PRAGMA query_only=ON`.
- Query parametrizzate e senza SQL proveniente dall'utente.
- Chiusura corretta della connessione.
- Nessuna scrittura, migrazione o creazione automatica del database.
- Usare soltanto le tabelle già esistenti (`offerta`, eventualmente
  `etl_run` per la data del dato).
- Per i valori geografici usare esclusivamente i percorsi già presenti in
  `extra_json`.

**Controllo**

Scrivere test che:

1. costruiscano un piccolo database temporaneo con lo schema esistente;
2. verifichino una ricerca base;
3. provino una scrittura tramite la connessione della libreria e verifichino
   che fallisca;
4. verifichino che il database resti invariato dopo una ricerca e dopo un
   errore;
5. verifichino il comportamento per file inesistente o non leggibile.

**Stato: completato.** Aggiunti `offerte/errori.py` (errori strutturati con
codice stabile) e `offerte/db.py` (`apri_db`, l'unico punto di apertura:
`mode=ro`, `PRAGMA query_only=ON`, `row_factory`, chiusura garantita; file
mancante, non leggibile o non-database → `database_non_disponibile` senza
percorsi nel messaggio). Test in `tests/test_db.py` con database temporanei
costruiti dallo schema reale (`tests/fixture_db.py`): ricerca base,
query_only attivo, scrittura rifiutata, database invariato dopo ricerca ed
errore, file inesistente/directory/non-database/non leggibile. `just check`
verde.

---

### T3 — Funzione applicativa condivisa di ricerca

**Obiettivo**

Implementare una funzione di dominio/applicazione riutilizzabile dal server
MCP e, in futuro, dalla CLI.

**Vincoli**

- Validazione centralizzata degli input.
- Limiti rigidi e documentati.
- Nessun calcolo di costo.
- Nessun accesso alla rete.
- Nessun ritorno di oggetti SQLite o strutture non serializzabili.
- Risultato deterministico e ordinato.
- Distinguere chiaramente dati identificativi, campi codificati e testo libero.
- Gestire l'assenza di dati geografici senza trattarla come errore globale.

**Controllo**

Aggiungere test unitari per:

- ricerca senza filtri;
- filtro per `fornitore`/PIVA;
- filtro per regione, provincia e comune;
- filtro per tipo cliente;
- filtro per tipo offerta;
- filtro `indicizzata=true` e `indicizzata=false`;
- ricerca testuale;
- combinazione di più filtri;
- limite e ordinamento stabili;
- nessun risultato;
- risultati troncati;
- data di validità;
- input fuori limite e con tipo errato;
- testo geografico ripetuto in lista JSON.

**Stato: completato.** Aggiunta `offerte/ricerca.py` con
`cerca_offerte(conn, filtri)`: validazione centralizzata (chiavi ammesse, tipi,
lunghezze, codici a due cifre, `limit` 1–50), query parametrizzate con
`json_each` per le zone (valore singolo o lista), `casefold` Unicode registrato
su SQLite per maiuscole/accenti, escape di `LIKE`, filtro di default su
`data_fine` (nulla = valida, `data_inizio` non filtrata), ordinamento
`piva`/`cod_offerta`, troncamento, `dati_aggiornati_al` e `avvertenze`.
`tests/test_ricerca.py` copre tutti i casi della checklist (27 test).
`just check` verde.

---

### T4 — Server MCP su trasporto stdio

**Obiettivo**

Esporre la funzione applicativa come unico tool MCP `cerca_offerte` su
trasporto stdio.

**Vincoli**

- Il server deve esporre un solo tool funzionale.
- La descrizione del tool deve indicare filtri, enum, unità, limiti, semantica
  dei dati geografici e limitazioni del modello.
- Il server deve delegare validazione e ricerca alla funzione condivisa.
- Lo stdout deve contenere soltanto il protocollo MCP; eventuali log devono
  andare su stderr e non contenere dati sensibili.
- Nessun tool deve accettare SQL.
- Nessun token o autenticazione in questa iterazione.

**Controllo**

Usare il client/test client MCP per verificare che:

1. il server parta su stdio;
2. il client elenchi esattamente il tool previsto;
3. il client veda lo schema degli input;
4. una chiamata con filtro valido restituisca risultati;
5. una chiamata senza risultati restituisca una risposta valida;
6. una chiamata con input errato restituisca un errore strutturato;
7. il processo non scriva sul database.

**Stato: completato (esclusa la verifica stdio, in T5).** `offerte/mcp.py` collega
il tool a `offerte.ricerca.cerca_offerte` e traduce gli errori in un risultato
con `isError = true` e `structuredContent` `{codice, messaggio}`. Il percorso del
database arriva da `--db` o da `OFFERTE_DB`. Aggiunti
`tests/test_mcp_cerca_offerte.py` (client in-memory: chiamata valida, senza
filtri, nessun risultato, errori strutturati, database assente, database
invariato) e `main()` su stdio. `just check` verde.

---

### T5 — Fixture e test d'integrazione MCP

**Obiettivo**

Rendere i test ripetibili senza dipendere dal DB generato localmente o dai dati
reali non presenti in Git.

**Vincoli**

- Non leggere XML o CSV grandi nei test dell'agente.
- Usare fixture piccole o database SQLite temporanei costruiti con poche righe.
- Inserire solo i campi necessari a coprire la ricerca.
- Coprire almeno un'offerta con dati geografici singoli e una con valori
  geografici ripetuti.
- Non usare la rete nei test automatici.

**Controllo**

Un test di integrazione deve avviare il server o il relativo harness ufficiale,
creare il DB temporaneo, invocare `cerca_offerte` come client MCP e verificare
l'intero JSON di risposta. Il test deve passare su una macchina senza dati in
`build/` e senza accesso alla rete.

**Stato: completato.** `tests/test_mcp_stdio.py` avvia `python -m offerte.mcp`
come processo figlio con `StdioServerParameters` (harness ufficiale del SDK),
usa un DB temporaneo creato dallo schema reale e invoca `cerca_offerte` come
client MCP: verifica l'intero JSON senza filtri (offerta con zone singole e
offerta con zone ripetute), il filtro geografico su lista e l'errore strutturato.
Nessun uso di `build/`, nessuna rete. `just check` verde.

---

### T6 — Trasporto HTTP locale opzionale, dopo stdio

**Obiettivo**

Aggiungere il trasporto HTTP streamable solo dopo che il trasporto stdio e tutti
i test MCP sono verdi.

**Vincoli**

- Ascoltare esclusivamente su `127.0.0.1`.
- Non aggiungere un reverse proxy.
- Non implementare ancora Cloudflare Tunnel.
- Rifiutare o impedire configurazioni che espongano il server su `0.0.0.0` o
  su un'interfaccia pubblica.
- Mantenere identico il tool e identico il contratto dello stdio.
- Nessuna autenticazione in questa task: l'uso è solo locale e temporaneo.

**Controllo**

- Avviare il server su una porta temporanea locale.
- Usare un client MCP per elencare il tool e chiamarlo via HTTP.
- Verificare che una connessione verso l'indirizzo configurato funzioni e che
  il server non modifichi il DB.
- Verificare la configurazione di bind con un test o con un controllo di
  avvio.
- Chiudere sempre il server al termine del test.

---

### T7 — Documentazione e comando di verifica

**Obiettivo**

Documentare come avviare e provare il server minimale e lasciare il repository
in uno stato verificabile da un altro agente.

**Vincoli**

- Aggiornare `README.md` perché il server diventa una funzionalità realmente
  disponibile.
- Documentare chiaramente che autenticazione, calcolo e deployment sono ancora
  fuori scope.
- Indicare il percorso del DB e il fatto che il server opera in sola lettura.
- Non documentare comandi che non sono stati verificati.
- Mantenere `just check` come verifica unica del progetto; se serve aggiungere
  un comando dedicato ai test MCP, deve essere richiamabile e documentato.

**Controllo**

Eseguire e riportare l'esito di:

```text
just check
```

In aggiunta, verificare manualmente il percorso completo:

```text
creazione/caricamento fixture → avvio server → list tools → cerca_offerte
```

La task è conclusa solo se il percorso funziona senza rete e senza modificare il
DB.

---

## 6. Criterio di accettazione complessivo

La prima iterazione è accettata quando:

- `just check` è verde;
- il server MCP espone soltanto `cerca_offerte`;
- un client MCP di test lo scopre e lo invoca con successo;
- la ricerca supporta almeno fornitore/PIVA, area geografica, tipo cliente,
  tipo offerta, indicizzazione, testo e limite;
- le risposte sono JSON strutturati e con dimensione limitata;
- gli errori di input sono strutturati;
- il DB viene aperto in sola lettura e non viene modificato;
- il trasporto stdio funziona;
- il trasporto HTTP, se implementato nella stessa iterazione, ascolta solo su
  `127.0.0.1`;
- non esistono ancora calcolo, autenticazione, SQL libero o accesso alla rete;
- `README.md` descrive il comportamento effettivamente implementato.

Dopo questa verifica ci si fermerà per validare lo stack prima di introdurre
calcolo, ulteriori tool, autenticazione o deployment.
