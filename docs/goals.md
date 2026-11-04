# Obiettivi da implementare

Elenco, in ordine di dipendenza, degli obiettivi **non ancora implementati**.
Contesto stabile (design, schema, sicurezza) in `docs/architettura.md`; regole di
lavoro in `AGENTS.md`; task operativi di un obiettivo in `docs/task.md`; lo stato
attuale in `README.md`.

## Stato di partenza (già implementato)

ETL completo (offerte XML, parametri CSV, PUN mensile) con validazione e swap
atomico; accesso read-only al DB; funzione applicativa `cerca_offerte`; server
MCP che la espone (stdio e HTTP su loopback), senza autenticazione. Dettagli e
comandi in `README.md`, `docs/contratto_cerca_offerte.md`,
`docs/validazione_xml.md`; il percorso che ha portato qui è in `docs/task.md`.

## Obiettivo 1 — Libreria, calcolo (fase A) e CLI

**Cosa fare.** Le restanti funzioni di libreria di `docs/architettura.md` §10
(`dettaglio_offerta`, `pun`, `decodifica`, `stato_dati`; `cerca_offerte` esiste
già), il modulo `calc` per la **stima della spesa per la materia energia**
(§9, fase A) e la CLI `offerte <comando> --json` su tutte le funzioni.

**Come.** Prima i test di `calc` con casi calcolati a mano (tre fasce uguali,
fasce diverse, quota fissa, indicizzata con PUN di scenario, offerta non
calcolabile), poi l'implementazione. Output strutturato con unità esplicite,
limiti rigidi, testo dei venditori in campi marcati. Una sola implementazione
per operazione, condivisa con il server MCP.

**Vincoli aperti.** Le questioni su fasce/indici, offerte miste e sconti
(`docs/questioni_aperte.md` #5, #6, #7, #9) vanno risolte o gestite come
`non_calcolabile` con motivo, mai con un costo inventato.

**Fatto quando.** `just check` verde; `offerte confronta --json ...` restituisce
una classifica con ipotesi e `non_calcolabili`; la CLI non ha modo di scrivere
sul DB.

## Obiettivo 2 — Completamento del server MCP e autenticazione

**Cosa fare.** Esporre come tool MCP anche `confronta_offerte`,
`dettaglio_offerta`, `pun`, `decodifica` e `stato_dati`, come strato sottile
sulla libreria (stesse funzioni e nomi della CLI). API key dirette nel server
(hash SHA-256, rate limit per chiave, niente interfaccia `TokenVerifier` finché
serve un solo meccanismo); `authctl` (`python -m offerte.auth`).

**Dipende da.** Obiettivo 1 (le funzioni che i tool espongono).

**Fatto quando.** Un client MCP di test elenca i tool, ne chiama almeno tre con
successo, riceve rifiuto senza token o con token revocato e un errore strutturato
su input fuori limite; nessun log contiene token o consumi.

## Obiettivo 3 — Deployment

**Cosa fare.** Unit e timer systemd con hardening, utenti di sistema separati,
configurazione di `cloudflared` come da `docs/architettura.md` §12 (solo Tunnel,
nessun reverse proxy locale), README con setup, gestione delle chiavi,
ripristino.

**Dipende da.** Obiettivi 1–2; verifica della licenza d'uso dei dati per il
servizio verso terzi (`docs/questioni_aperte.md` #1).

**Fatto quando.** Da una VM pulita, seguendo il README, ETL e server partono;
l'origine non è raggiungibile se non attraverso Cloudflare.

## Obiettivo 4 — ETL: download del CSV dei parametri

**Cosa fare.** Collegare in `etl scarica` il download del CSV dei parametri
dall'URL datato (`.../parametriML/AAAA_MM/PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv`,
vedi `docs/questioni_aperte.md` → "Risolte"), con la stessa allowlist, gli stessi
limiti di dimensione e il riferimento dalla data nel nome file usati per l'XML.

**Dipende da.** Niente.

**Fatto quando.** `just etl-scarica` carica offerte e parametri senza passare il
CSV a mano; `just check` verde.

## Fuori scope finché l'utente non lo chiede

- spesa totale stimata con le componenti regolate (fase B, §9);
- PUN giornaliero dal GME (§4);
- OAuth con identity provider esterno (§11).

## Come si procede

- Un obiettivo alla volta, nell'ordine. A fine obiettivo: riepilogo di 5–10 righe
  (fatto, verificato, questioni aperte) e ci si ferma.
- Un task per volta, piccolo e verificabile: prima il test (o il comando di
  verifica), poi l'implementazione, un commit per task.
- Un obiettivo è chiuso solo quando il suo criterio è verificato eseguendo i
  comandi (`just check`), non per dichiarazione.
- Dubbi su codici del tracciato, formule, fonti o termini d'uso:
  `docs/questioni_aperte.md`; si procede sul resto, senza indovinare.
- Mai leggere l'XML o il CSV completo nel contesto: script e query con output
  piccolo (`LIMIT`).
