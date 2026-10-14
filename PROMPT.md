# PROMPT: cosa sviluppare e in che ordine

Sei un agente di sviluppo. Contesto stabile: `AGENTS.md` (regole) e `docs/architettura.md` (architettura, schema, sicurezza). Leggili prima di iniziare. Questo file dice **cosa fare adesso e come**.

## Come lavori

- Una fase alla volta, nell'ordine sotto. A fine fase scrivi un riepilogo di 5-10 righe (fatto, verificato, questioni aperte) e **fermati** in attesa dell'utente.
- Dentro ogni fase, task piccoli: test (o comando di verifica) prima, implementazione dopo, un commit per task.
- Una fase è chiusa solo quando il suo criterio di accettazione è verificato eseguendo i comandi, non per dichiarazione.
- Dubbi su codici del tracciato, formule, fonti, termini d'uso: scrivili in `docs/questioni_aperte.md`, procedi sul resto, non indovinare.
- Non leggere mai nel contesto l'XML completo o il CSV: usa script e query con output piccolo.

## Fase 1: scheletro e parser sulla fixture

Fai: struttura del repo (`etl/`, `offerte/` libreria, `cli/`, `mcp_server/`, `authctl/`, `deploy/`, `tests/`, `docs/`), `justfile` con `test` e `check`, schema SQLite come in `docs/architettura.md` §6, parser tollerante (§5) per l'XML, caricamento in SQLite.

Parti da: `tests/fixtures/offerta_estratto.xml` (una offerta). Cerca il tracciato ufficiale con le decodifiche e caricalo in `codifica`; se non lo trovi, questione aperta.

Accettazione: `just check` verde; la fixture produce 1 riga in `offerta`, 4 in `componente` (3 fasce di SPREAD + quota di commercializzazione), 1 in `condizione`; un elemento XML inventato e non previsto finisce in `extra_json` e incrementa il contatore dei percorsi sconosciuti senza far fallire il caricamento; un XML con entità esterne non viene risolto.

## Fase 2: ETL completo e validazione sui dati reali

Fai: download condizionale con allowlist e limiti, raw datati, caricamento del CSV dei parametri (`parametro`, riferimento dalla data nel nome file, controllo dei parametri obbligatori), validazioni e swap atomico, `etl_run`, comando per rilanciare da un raw locale.

Poi, con l'XML completo che l'utente ti mette a disposizione in locale: caricalo, interroga il DB con query **aggregate** e scrivi `docs/validazione_xml.md` (percorsi sconosciuti, valori distinti dei codici, elementi che si ripetono, campi vuoti, intervallo date, duplicati, come sono rappresentate le offerte a prezzo fisso). Estendi schema e parser dove serve e ricostruisci il DB.

Accettazione: ETL idempotente; un XML troncato non sostituisce il DB in uso; `docs/validazione_xml.md` esiste e non contiene dati grezzi, solo riassunti; zero percorsi sconosciuti non spiegati. **Fermati: l'utente rivede la validazione prima della Fase 3.**

## Fase 3: PUN

Fai: ingestione del PUN giornaliero dalla fonte indicata in §4 (servizio API del GME; l'utente fornirà le credenziali, non inventarle), tabella `pun` con la serie usata, storico che si accumula tra le ricostruzioni.

Accettazione: un range di date reale viene caricato e rileggibile; un secondo caricamento non duplica le righe; i termini d'uso del GME sono annotati in `docs/questioni_aperte.md`.

## Fase 4: libreria, calcolo (fase A) e CLI

Fai: libreria `offerte` con le funzioni di §10, modulo `calc` per la **stima della spesa per la materia energia** (§9, fase A), CLI con `--json` su tutte le funzioni, `stato_dati`.

Come: scrivi prima i test di `calc` con casi calcolati a mano (tre fasce uguali, fasce diverse, quota fissa, indicizzata con PUN di scenario, offerta non calcolabile). Output strutturato con unità esplicite, limiti rigidi, testo dei venditori in campi marcati.

Accettazione: `just check` verde; `offerte confronta --json ...` restituisce una classifica con ipotesi e `non_calcolabili`; la CLI non ha modo di scrivere sul DB.

## Fase 5: server MCP e autenticazione

Fai: server MCP come strato sottile sulla libreria (stesse funzioni e nomi della CLI), prima in stdio per i test locali, poi streamable HTTP su `127.0.0.1`; `TokenVerifier` con API key (hash, rate limit per chiave); `authctl`.

Accettazione: un client MCP di test elenca i tool, ne chiama almeno tre con successo, riceve rifiuto senza token o con token revocato, e riceve errore strutturato su input fuori limite; nessun log contiene token o consumi.

## Fase 6: deployment

Fai: unit e timer systemd con hardening, utenti separati, configurazione di `cloudflared` come da §12 (Tunnel come default; `Caddyfile` come alternativa documentata), README con setup, rotazione delle chiavi, ripristino.

Accettazione: da una VM pulita, seguendo il README, ETL e server partono; l'origine non è raggiungibile se non attraverso Cloudflare.

## Fuori scope finché l'utente non lo chiede

Spesa totale stimata con le componenti regolate (fase B, §9) e OAuth con IdP esterno (§11).
