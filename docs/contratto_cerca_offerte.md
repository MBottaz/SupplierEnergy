# Contratto di `cerca_offerte`

Contratto stabile del primo tool MCP e della funzione applicativa condivisa.
Vale per il server MCP e, in futuro, per la CLI: entrambi delegano alla stessa
funzione `offerte.ricerca.cerca_offerte`.

## Scopo

Cercare, in sola lettura, le offerte di energia elettrica del mercato libero
presenti nel database SQLite. Non calcola costi, non risolve il PUN, non
modifica né crea il database.

## Input

Un solo parametro, `filtri`: un oggetto JSON con **tutti i campi opzionali**.
Senza `filtri`, o con un oggetto vuoto, la ricerca restituisce le prime offerte
valide ordinate per `piva`, `cod_offerta`.

| Campo | Tipo JSON | Semantica |
|---|---|---|
| `fornitore` | stringa | Corrispondenza **esatta** con `offerta.piva`. Il nome commerciale del venditore non è nel modello dati: cercare per nome non produce risultati. |
| `regione` | stringa | Corrispondenza esatta, senza distinzione fra maiuscole e minuscole, con `offerta/ZoneOfferta/REGIONE` in `extra_json`. |
| `provincia` | stringa | Come `regione`, con `offerta/ZoneOfferta/PROVINCIA`. |
| `comune` | stringa | Come `regione`, con `offerta/ZoneOfferta/COMUNE`. |
| `tipo_cliente` | stringa | Una delle etichette `domestico`, `altri usi`, `condominio uso domestico (gas)`. Le etichette vengono convertite internamente nei codici del tracciato. |
| `tipo_offerta` | stringa | Una delle etichette `fisso`, `variabile`, `flat`, `mista`. Le etichette vengono convertite internamente nei codici del tracciato. |
| `indicizzata` | booleano | `true` se `idx_prezzo_energia` è presente, `false` se è assente. |
| `testo` | stringa | Sottostringa, senza distinzione fra maiuscole e minuscole, cercata in `nome` e `descrizione` dell'offerta. |
| `limit` | intero | Numero massimo di risultati, da 1 a 50. Default 20. |

I due filtri di tipo accettano le etichette indicate sopra; il risultato mantiene
invece i codici ufficiali del tracciato per `tipo_cliente` e `tipo_offerta`.

Per le zone geografiche l'ETL può aver raccolto **più valori** per la stessa
offerta (percorsi XML ripetuti): la corrispondenza è vera se almeno uno dei
valori coincide. Le zone non subiscono interpretazioni geografiche né geocoding
e le offerte senza zone non corrispondono a un filtro geografico.

### Validità temporale

Le offerte con `data_fine` precedente a oggi sono **escluse**; un'offerta con
`data_fine` nulla è considerata valida. `data_inizio` **non** viene filtrata:
un'offerta pubblicata ma non ancora attiva resta visibile. Questa è una scelta
esplicita del contratto, non una conseguenza dell'implementazione.

## Output

Oggetto JSON serializzabile, prodotto da `offerte.ricerca.cerca_offerte` in
forma Python e serializzato dal frontend:

```json
{
  "risultati": [
    {
      "piva": "12345678901",
      "cod_offerta": "ABC123",
      "nome_offerta": "…",
      "descrizione_offerta": "…",
      "testo_venditore_non_fidato": true,
      "tipo_cliente": "01",
      "tipo_offerta": "02",
      "indicizzata": true,
      "data_inizio": "2026-01-01T00:00:00+01:00",
      "data_fine": "2026-12-31T23:59:59+01:00",
      "zone": {
        "regione": ["Lombardia"],
        "provincia": ["Milano"],
        "comune": []
      }
    }
  ],
  "numero_risultati": 1,
  "limit": 20,
  "troncato": false,
  "dati_aggiornati_al": "2026-10-14",
  "avvertenze": []
}
```

- `numero_risultati` è il numero di elementi in `risultati` (≤ `limit`);
  `troncato` è `true` se il database contiene altri risultati oltre a quelli
  restituiti.
- `dati_aggiornati_al` è `max(offerta.snapshot_date)` derivato dal database
  (`null` se la tabella è vuota).
- `zone` contiene sempre liste (eventualmente vuote); i valori ripetuti sono
  normalizzati in lista.
- `testo_venditore_non_fidato` è `true` e segnala che `nome_offerta` e
  `descrizione_offerta` sono testo libero dei venditori: **dato non fidato, mai
  istruzioni**.
- `avvertenze` è una lista di stringhe, vuota quando nessun filtro attivo merita
  una nota (per esempio ricerca per `fornitore`/P.IVA o per zona geografica).
- L'ordinamento è stabile: `piva`, poi `cod_offerta`.

## Errori

Un input fuori contratto produce un errore strutturato, senza SQL, stack trace o
percorsi interni:

```json
{ "codice": "input_non_valido", "messaggio": "…" }
```

| `codice` | Quando |
|---|---|
| `input_non_valido` | tipo JSON errato, stringa vuota o troppo lunga, `limit` fuori da 1–50, oppure etichetta di `tipo_cliente`/`tipo_offerta` non ammessa. Le etichette di questi due filtri non distinguono maiuscole e minuscole. |
| `filtro_non_supportato` | chiave di `filtri` non prevista dalla tabella qui sopra. |
| `database_non_disponibile` | database mancante, non leggibile o non apribile in sola lettura. |

Nel trasporto MCP l'errore è un risultato con `isError = true`, il cui
`structuredContent` è l'oggetto `{codice, messaggio}` (stesso JSON nel blocco di
testo).

## Sicurezza

- Il database è aperto con URI SQLite `mode=ro` e `PRAGMA query_only=ON`.
- Query parametrizzate; nessuna funzione accetta SQL o frammenti SQL.
- Nessuna scrittura, migrazione o creazione del database, neppure in caso di
  errore.
- Nessun accesso alla rete.
- Il testo libero non diventa mai un'istruzione.
