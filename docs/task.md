# Task: scheduling esterno e documentazione operativa del deployment

`compose.yml` definisce i due servizi applicativi da una sola immagine:
`offerte-mcp` (long-running, sola lettura) e `offerte-etl` (batch, swap atomico,
profilo `etl`). Questa parte del deployment è completata; qui resta il passo
successivo: lo scheduling esterno e la documentazione operativa.

Confine di questa fase: nessuna autenticazione API key, nessun Cloudflare
Tunnel, nessuna esposizione pubblica. Il server non deve essere pubblicato su
Internet finché non è completato l'obiettivo di autenticazione. La topologia
Docker e la distinzione dei permessi sono in `deploy/README.md` e
`docs/architettura.md` §12.

---

## 1. Integrare lo scheduling esterno e la documentazione operativa

### Azioni

1. Non usare un processo scheduler dentro il container.

2. Preparare un esempio di timer `systemd` sulla VM che esegua il job ETL con
   `docker compose --profile etl run --rm offerte-etl` o un wrapper equivalente.

3. Configurare il timer con:

   - una sola esecuzione alla volta;
   - retry controllati per errori transitori di rete;
   - log dell'exit code e dell'output JSON dell'ETL;
   - intervallo giornaliero per offerte e parametri;
   - intervallo mensile separato per l'aggiornamento PUN, se mantenuto come job
     distinto.

4. Documentare nel README:

   - build dell'immagine;
   - inizializzazione dei volumi e dei permessi;
   - avvio del servizio MCP locale;
   - esecuzione manuale dell'ETL;
   - installazione e test del timer;
   - verifica dello swap atomico;
   - ripristino da `offerte.db.prev`;
   - comportamento in assenza del database;
   - posizione dei raw e policy di conservazione.

5. Documentare chiaramente che questa fase non abilita ancora:

   - autenticazione API key;
   - Cloudflare Tunnel;
   - esposizione pubblica;
   - OAuth;
   - tool MCP aggiuntivi.

6. Aggiornare `deploy/README.md` con la topologia Docker e con la distinzione
   fra i permessi ETL e MCP.

7. Aggiungere test o script di smoke test per una VM/container pulito:

   ```text
   build immagine → crea volumi → esegue ETL → avvia MCP → chiama cerca_offerte
   ```

8. Prima di ogni commit che modifica comandi, struttura o comportamento,
   aggiornare `README.md` e verificare il risultato con:

   ```text
   just check
   ```

### Verifica

- Da un ambiente Docker pulito, seguendo il README, l'ETL completa il primo
  caricamento e MCP risponde a `cerca_offerte`.
- Il timer non avvia due ETL contemporaneamente.
- Il servizio MCP può essere riavviato senza perdita del database attivo.
- Il ripristino da `.prev` è documentato e verificabile.
- Nessuna porta pubblica viene aperta dalla configurazione di questa fase.
- `just check` passa e gli smoke test Docker sono ripetibili.

---

## Fuori scope di questo task

- API key, autenticazione e rate limiting applicativo;
- Cloudflare Tunnel e configurazione del proxy pubblico;
- OAuth, JWKS e identity provider;
- tool MCP diversi da `cerca_offerte`;
- calcolo dei costi;
- modifica dello schema SQLite, salvo necessità dimostrata dal deployment;
- orchestratori come Kubernetes o Docker Swarm.
