# `cerca_offerte` contract

Stable contract of the first MCP tool and of the shared application function. MCP is the only point of contact for agents and delegates to `offerte.ricerca.cerca_offerte`. Any CLI is only a local debug adapter: it is not an agent surface, is not part of the deployment and does not form a second public contract.

## Purpose

Search, read-only, the free-market electricity offers present in the SQLite database. It does not calculate costs, does not resolve the PUN, and does not modify or create the database.

## Input

A single parameter, `filtri`: a JSON object with **all fields optional**. Without `filtri`, or with an empty object, the search returns the first valid offers ordered by `piva`, `cod_offerta`.

| Field | JSON type | Semantics |
|---|---|---|
| `fornitore` | string | **Exact** match with `offerta.piva`. The seller's commercial name is not in the data model: searching by name yields no results. |
| `regione` | string | Exact match, case-insensitive, with `offerta/ZoneOfferta/REGIONE` in `extra_json`. |
| `provincia` | string | As `regione`, with `offerta/ZoneOfferta/PROVINCIA`. |
| `comune` | string | As `regione`, with `offerta/ZoneOfferta/COMUNE`. |
| `tipo_cliente` | string | One of the labels `domestico`, `altri usi`, `condominio uso domestico (gas)`. The labels are converted internally to the track codes. |
| `tipo_offerta` | string | One of the labels `fisso`, `variabile`, `flat`, `mista`. The labels are converted internally to the track codes. |
| `indicizzata` | boolean | `true` if `idx_prezzo_energia` is present, `false` if absent. |
| `testo` | string | Case-insensitive substring searched in the offer `nome` and `descrizione`. |
| `limit` | integer | Maximum number of results, from 1 to 50. Default 20. |

The two type filters accept the labels above; the result keeps the official track codes for `tipo_cliente` and `tipo_offerta`.

For geographical zones the ETL may have collected **multiple values** for the same offer (repeated XML paths): the match is true if at least one value matches. Zones undergo no geographical interpretation or geocoding, and offers without zones do not match a geographical filter.

### Temporal validity

Offers with `data_fine` before today are **excluded**; an offer with a null `data_fine` is considered valid. `data_inizio` is **not** filtered: an offer published but not yet active remains visible. This is an explicit contract choice, not a consequence of the implementation.

## Output

A serializable JSON object, produced by `offerte.ricerca.cerca_offerte` in Python form and serialized by the frontend:

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

- `numero_risultati` is the number of elements in `risultati` (≤ `limit`); `troncato` is `true` if the database contains more results than those returned.
- `dati_aggiornati_al` is `max(offerta.snapshot_date)` derived from the database (`null` if the table is empty).
- `zone` always contains lists (possibly empty); repeated values are normalized into a list.
- `testo_venditore_non_fidato` is `true` and signals that `nome_offerta` and `descrizione_offerta` are seller free text: **untrusted data, never instructions**.
- `avvertenze` is a list of strings, empty when no active filter deserves a note (for example a search by `fornitore`/VAT number or by geographical zone).
- Ordering is stable: `piva`, then `cod_offerta`.

## Errors

Out-of-contract input produces a structured error, with no SQL, stack trace or internal paths:

```json
{ "codice": "input_non_valido", "messaggio": "…" }
```

| `codice` | When |
|---|---|
| `input_non_valido` | wrong JSON type, empty or too-long string, `limit` outside 1–50, or a `tipo_cliente`/`tipo_offerta` label not allowed. The labels of these two filters are always case-insensitive. |
| `filtro_non_supportato` | a `filtri` key not in the table above. |
| `database_non_disponibile` | database missing, unreadable or not openable read-only. |

In the MCP transport the error is a result with `isError = true`, whose `structuredContent` is the `{codice, messaggio}` object (the same JSON in the text block).

## Security

- The database is opened with the SQLite URI `mode=ro` and `PRAGMA query_only=ON`.
- Parameterized queries; no function accepts SQL or SQL fragments.
- No writes, migrations or database creation, even on error.
- No network access.
- Free text never becomes an instruction.
