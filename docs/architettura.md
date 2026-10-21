# Architettura: database offerte luce e interfacce per agenti

Documento di contesto, stabile nel tempo. Va in `docs/architettura.md`. Cosa sviluppare e in che ordine è in `PROMPT.md`.

## 1. Obiettivo

Un sistema minimale che:

1. scarica periodicamente le offerte di energia elettrica del mercato libero (XML open data, ~22 MB), il file dei parametri regolati (CSV) e il PUN giornaliero;
2. li normalizza e li carica in un database SQLite (un solo file);
3. li espone in sola lettura ad **agenti AI** tramite una libreria con due interfacce sottili: una CLI (agenti locali) e un server MCP remoto (agenti remoti), con funzioni come `confronta_offerte`.

Gli utilizzatori sono agenti, non persone: nomi, descrizioni e formati di output vanno pensati per un LLM che li legge.

## 2. Principi

- **Minimalismo**: poche dipendenze, nessun framework pesante, nessun servizio che richieda manutenzione continua.
- **Portabilità**: Linux (Debian stabile come target), FreeBSD per quanto possibile. Nessuna dipendenza da un cloud specifico: Cloudflare sta davanti, non dentro.
- **Separazione dei privilegi**: ETL (scrive il DB) e interfacce (lo leggono) sono processi distinti con utenti distinti.
- **Il DB è ricostruibile** da zero a partire dai file raw datati. Correggere lo schema costa poco.
- **Non indovinare**: codici del tracciato e formule di calcolo vengono dalla documentazione ufficiale.
- **Il calcolo del costo sta in Python**, con `Decimal`, testato.

## 3. Architettura

```
[systemd timer] → etl: fetch → parse → normalizza → offerte.db.new → validazione → rename atomico
                                                              │
                                                    offerte.db (aperto in sola lettura)
                                                              │
                              pacchetto `offerte` (nessun I/O di rete nella libreria)
                               ├── CLI `offerte ... --json`      → agenti locali (via shell)
                               ├── server MCP su 127.0.0.1       → agenti remoti
                               └── `authctl` (gestione chiavi)   → non gira come servizio
                                                              │
        cloudflared (Tunnel: solo connessione in uscita) ←→ Cloudflare (proxy: DDoS, WAF, rate limit) ←→ agenti
```

| Componente | Cosa fa | Cosa NON fa |
|---|---|---|
| `etl` | scarica, valida, parsa, scrive il DB nuovo, swap atomico, registra `etl_run` | non serve richieste, non apre porte |
| libreria `offerte` | query tipizzate e calcolo dei costi (`calc`, funzioni pure) | non accede alla rete |
| CLI | espone le funzioni della libreria, output JSON | non scrive il DB |
| server MCP | espone le stesse funzioni come tool, verifica token, rate limit | non scrive il DB, non emette token |
| `authctl` | crea, elenca, revoca API key | non gira come servizio |
| Cloudflare + Tunnel | DDoS, WAF, rate limit grossolano, TLS pubblico | non sostituisce l'autenticazione applicativa |

Un solo pacchetto Python non-ETL, `offerte`: la libreria (query e calcolo) più
i frontend `offerte.cli`, `offerte.mcp` e `offerte.auth`. Sono processi
separati (e utenti di sistema separati, §12), ma un unico package: la
separazione dei privilegi è a livello di processo, non di namespace.

## 4. Fonti dati (gli URL vanno verificati, non inventati)

1. **Offerte XML**: Portale Offerte di ARERA (open data), elettricità, mercato libero. Trova l'URL ufficiale e il **tracciato ufficiale** con le tabelle di decodifica. Download condizionale (ETag / If-Modified-Since); se lo SHA-256 coincide con quello dell'ultima esecuzione, non fare nulla. Verifica la licenza d'uso.
2. **Parametri CSV**: `PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv`, colonne `nome_parametro,valore,descrizione`, ~100 righe. La data nel nome è la data di riferimento: salvala con i valori.
3. **PUN**: due fonti, entrambe da verificare nei termini d'uso. *Serie mensile* (serve alla maggior parte delle offerte indicizzate): CSV "Prezzi storici - indici a pubblica diffusione" della pagina Open Data del Portale Offerte, colonna `PUN (€/kWh)`, un valore per mese; `python -m etl pun` lo scarica e aggiorna `pun` (serie `PUN_MENSILE`), l'URL non è datato e sta in `etl/pun.py`. *Serie giornaliera*: servizio API del GME (guida tecnica ufficiale di ottobre 2025, con autenticazione: serve una registrazione dell'utente). Alternativa: file della sezione "MGP – Download". Dal 2025 l'indice è il PUN Index GME: verifica la definizione e salva in `pun` quale serie usi. **Verifica i termini d'uso di entrambe le fonti** (uso commerciale, ridistribuzione) e annotali in `docs/questioni_aperte.md`: vincolano il modo in cui il servizio può essere offerto a terzi.

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

Il DB si ricostruisce da zero a ogni esecuzione dall'ultimo raw, copiando dal precedente solo `parametro`, `pun` ed `etl_run`.

## 7. File dei parametri

Dal file `PO_Parametri_Mercato_Libero_E_20260928.csv` (100 righe):

- I nomi seguono uno schema: prefisso della componente (`acc`, `arim`, `asos`, `dis`, `iva`, `pcv`…), categoria cliente (`_d`/`_nd`/`_a`, `_dr`/`_dnr`, `_b1`…`_b6`) e tipo (`_c` energia, `_f` quota fissa, `_p` potenza).
- **Le unità non sono nel file**: convivono €/kWh, €/anno o €/POD/anno, €/kW/anno, importi anomali (`acc_a_h_h` = 4820.0, `gamma` = -73.5737) e adimensionali (`lambda` = 0.1). I metadati (unità, categoria cliente, BTA) si ricaveranno dalla documentazione ufficiale in fase B, non per induzione dai nomi.
- Si caricano sempre tutte le righe così come sono; i metadati arrivano in un secondo passaggio (fase B), così un cambio di schema dei nomi non rompe il caricamento.
- La classificazione BTA (`_b1`…`_b6`) va mappata a potenza/uso del cliente dal documento ufficiale; se non è reperibile, chiedi all'utente. Questa mappatura serve alla fase B, non al caricamento dei parametri.
- Parametri obbligatori controllati dall'ETL (almeno `pcv_a`, `pcv_c`, `iva_a`, `iva_c`, `lambda`): se mancano, lo swap è bloccato.

## 8. ETL

1. Download in cartella temporanea con timeout, limite di dimensione (es. 100 MB), solo host in allowlist, solo HTTPS.
2. Raw salvati in `raw/AAAA-MM-GG/` (ultimi 90 giorni).
3. Parser XML hardened (entità esterne e rete disabilitate: `defusedxml` oppure `lxml` con `resolve_entities=False, no_network=True`), in streaming con `iterparse`, memoria liberata a ogni `<offerta>`.
4. DB nuovo → `PRAGMA integrity_check` → controlli: offerte ≥ 50% dell'esecuzione precedente, nessuna chiave nulla o duplicata, parametri obbligatori presenti, ultimo PUN recente (solo warning).
5. Se tutto passa: rename atomico, versione precedente in `offerte.db.prev`. Se no: DB in uso intatto, errore in `etl_run`, exit code ≠ 0.
6. Idempotente.

Pianificazione (systemd timer, Europe/Rome): offerte e parametri una volta al giorno; PUN dopo la pubblicazione dei risultati del mercato (verifica l'orario GME).

## 9. Calcolo del costo

Fase A: **stima della spesa per la materia energia**: componenti dell'offerta (energia/spread per fascia × consumi per fascia, quote fisse e di commercializzazione); per le indicizzate, l'indice risolto con un PUN di scenario. Restituisce sempre le ipotesi usate.

Fase B (dopo conferma dell'utente): **spesa totale stimata** con le componenti regolate del file parametri (trasporto, oneri, accise, IVA), seguendo la metodologia ufficiale del Portale Offerte, che va trovata e citata nel codice.

Regole: funzioni pure, `Decimal`; un'offerta non calcolabile (struttura non supportata, componente sconosciuta) va in `non_calcolabili` con il motivo, mai con un costo inventato; test su casi calcolati a mano e, se possibile, confrontati con il simulatore del Portale.

## 10. Interfacce per agenti

Un'unica libreria, due frontend sottili (CLI e MCP) che espongono le stesse funzioni. Linee guida di design, valide per qualunque harness (anche piccoli, come Pi):

- **Output strutturato, non prosa**: JSON con campi dai nomi autoesplicativi e unità esplicite (`_eur`, `_eur_mwh`, `_kwh`). Nel server MCP, dichiara lo schema di output dove l'SDK lo supporta.
- **Pochi tool, ben documentati**: la descrizione di ogni tool e di ogni parametro deve bastare a un agente per usarlo senza leggere altro (enum ammessi, unità, esempi, limiti). I tool si scoprono dalla documentazione.
- **Componibili**: identificatori stabili (`piva`, `cod_offerta`) restituiti da una funzione e accettati dalle altre; `confronta_offerte` accetta una lista opzionale `cod_offerte` per restringere il confronto.
- **Output piccolo**: limiti rigidi (`n` ≤ 25, `limit` ≤ 50, tetto sui caratteri con segnalazione del troncamento), paginazione dove serve.
- **Testo dei venditori = dato non fidato**: in campi marcati (es. `descrizione_venditore`), mai concatenato in istruzioni o messaggi generati dal server.
- **Errori strutturati** (`codice`, `messaggio`), senza stack trace né percorsi.

Funzioni (CLI: `offerte <comando> --json`; MCP: stesso nome, annotazione di sola lettura):

- `confronta_offerte(tipo_cliente, consumo_annuo_kwh, ripartizione_fasce?, potenza_kw?, tipo_prezzo?, pun_scenario_eur_mwh?, cod_offerte?, n=10)` → classifica con `costo_annuo_eur`, `dettaglio_componenti`, `ipotesi`, `non_calcolabili`, `dati_aggiornati_al`, `avvertenze`
- `cerca_offerte(venditore?, tipo_cliente?, tipo_prezzo?, indicizzata?, testo?, limit=20)`
- `dettaglio_offerta(piva, cod_offerta)`
- `pun(da, a, aggregazione=giornaliero|mensile)`
- `decodifica(dominio, codice?)`
- `stato_dati()` → date di ultimo aggiornamento di offerte, parametri e PUN, numero di offerte

Il DB si apre con `file:...?mode=ro` e `PRAGMA query_only=ON`. Nessuna funzione accetta SQL libero.

Stack: Python, SDK ufficiale `mcp` (FastMCP) con transport streamable HTTP, `uv`, versioni pinnate; verifica la documentazione attuale dell'SDK e della specifica MCP prima di implementare.

## 11. Autenticazione (pluggabile)

Interfaccia `TokenVerifier`, due implementazioni:

1. **Subito: API key per agente.** Token casuali ≥ 256 bit in `Authorization: Bearer`; si conserva solo l'hash SHA-256, con etichetta, data, stato. Gestione con `authctl create|list|revoke`. File auth separato dal DB dati. Rate limit per chiave in memoria (token bucket, default 60 richieste/minuto, configurabile). Mai log del valore dei token né dei parametri di consumo.
2. **Solo se servono client che accettano solo OAuth**: validazione di JWT di un identity provider esterno (JWKS, `iss`, `aud` = URL canonico del server, scadenza) ed esposizione di `/.well-known/oauth-protected-resource` (RFC 9728). Il server non emette token. L'IdP lo sceglie l'utente (candidati open source/UE: Zitadel, Keycloak).

## 12. Rete e deployment

- Una VM Linux (Debian stabile) in un provider UE scelto dall'utente. Aggiornamenti di sicurezza automatici, SSH con chiave.
- **Cloudflare davanti come proxy**: DDoS, WAF, rate limit grossolano. L'origine non deve essere raggiungibile direttamente (altrimenti la protezione si aggira):
  - **Default: Cloudflare Tunnel** (`cloudflared`): la VM apre solo connessioni in uscita, nessuna porta pubblica, il server MCP ascolta su `127.0.0.1` in HTTP semplice. In questo caso **Caddy non serve**.
  - **Alternativa senza Tunnel**: Caddy sulla 443 (TLS automatico, reverse proxy, limite al body) con firewall che accetta la 443 solo dagli intervalli IP di Cloudflare. Caddy è anche il piano B se un giorno si lascia Cloudflare.
  - Nota: nelle chiamate MCP (POST JSON-RPC dinamiche) la cache non serve; il valore di Cloudflare è nella mitigazione di DDoS e abusi.
- Utenti di sistema separati: `offerte-etl` (scrive in `/var/lib/offerte`) e `offerte-mcp` (legge, e legge il file auth). Unit systemd con hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, `ReadWritePaths` minimi, `MemoryMax`.
- Backup: il DB è ricostruibile; solo file auth, configurazione e storico PUN.
- `/healthz` senza dati per il monitoraggio.

## 13. Checklist di sicurezza

- Download solo da allowlist, HTTPS, limiti di dimensione e timeout; parser XML hardened.
- Swap del DB solo dopo validazione; DB in uso mai toccato in caso di errore.
- Interfacce in sola lettura; nessun SQL libero; input con limiti rigidi.
- Token hashati, rate limit per chiave, nessun dato di consumo nei log.
- Testo dei venditori sanificato e marcato come non fidato.
- Origine non raggiungibile se non attraverso Cloudflare.
- Errori senza dettagli interni.

## 14. Verifica

- Parser testato sulla fixture; funzioni di calcolo su casi calcolati a mano (tre fasce uguali, fasce diverse, quota fissa, indicizzata con PUN di scenario, non calcolabile).
- Test di sicurezza: scrittura sul DB impossibile dalle interfacce; richiesta senza token o con token revocato rifiutata; input fuori limite rifiutato; entità XML esterne non risolte; XML corrotto o troncato non sostituisce il DB in uso.
- ETL idempotente.
- `just check` (lint, tipi, test) è il comando unico di verifica; `just` ricrea tutto da zero.
