# Validation of the real XML

Summary (aggregates only, no raw data) of the first load of the full open-data XML (ETL objective, completed).

## How it was produced

| Item | Value |
|---|---|
| File | `raw/2026-10-14/PO_Offerte_E_MLIBERO_20261014.xml` (20.7 MB) |
| SHA-256 | `7de4c0df3fc0dcc22589a4d28e43ac09dd75ed088bdad3da2af1e3f27f627dee` |
| Parameters | `docs/PO_Parametri_Mercato_Libero_E_20261014.csv` — SHA-256 `801bb798d551656be3e7e9db45431d81fc0bb5df147dfb4f94b722e577e639d0` |
| Reference track | SII, "Trasmissione Offerte Mercato Retail" v5.0, 15/12/2025, §7 (in `etl/codifiche.py`) |
| Command | `just etl-reale` (≈5 s) |

The DB is rebuildable from scratch from the same raw file; the run recorded in `etl_run` has `esito = ok` and `percorsi_sconosciuti = 0`.

## 1. Coverage

- 3,540 offers, 15,269 components, 5,186 conditions, 338 distinct sellers (the largest with 203 offers), 100 parameters, 82 decodings.
- Every offer has `piva`, `cod_offerta`, validity dates and at least one component; 2 offers out of 3,540 have no `ComponenteImpresa` (they load with no rows in `componente`).
- 39 months of validity covered: `data_inizio` from 2022-11 to 2026-10, almost all in 2026 (3,183); 2 offers not yet active at the reference date, 0 expired (the file publishes active offers).

## 2. Unknown paths: zero

No path outside the track and the parser (`percorsi_sconosciuti = 0`). The published XML uses a default namespace (`http://www.acquirenteunico.it/schemas/SII_AU/OffertaRetail/01`): the parser compares paths without the namespace and handles both forms.

Two track fields do not appear in this snapshot and are nevertheless already known: `RiferimentiPrezzoEnergia/FASCIA_PREZZO` (if absent, the price applies to all consumption) and `TipoPrezzo/FasceOrarieSettimanali/*` (for `TIPOLOGIA_FASCE` = 03/07 the track says the standard bands are inherited).

Real names different from how they had been transcribed from the PDF track: `TIPO_FASCE` is in the file `TipoPrezzo/TIPOLOGIA_FASCE` (plural) and `Dispacciamento/VALORE_DISP` (not `VALORE_DISPACCIAMENTO`). The parser uses the real names.

## 3. Known fields without a column (`extra_json`)

Track paths that the data model of §6 does not model remain in `extra_json` (and do not count as unknown). Counts (descending):

- repeated on all loaded tracks: `TIPOLOGIA_FASCE`, `MetodoPagamento/MODALITA_PAGAMENTO`, `Dispacciamento/TIPO_DISPACCIAMENTO`, `Dispacciamento/NOME`, `DettaglioOfferta/TIPOLOGIA_ATT_CONTR`, `ModalitaAttivazione/MODALITA`;
- 1,000–2,000 offers: `MetodoPagamento/DESCRIZIONE` (1,751), `Dispacciamento/DESCRIZIONE` (1,488), `DettaglioOfferta/DOMESTICO_RESIDENTE` (1,430);
- 500–1,000: `Sconto/*` (968 offers with a discount; name, description, validity, VAT, conditions, periods, `PrezziSconto/*`), `CondizioniContrattuali/ALTRO` (868, the free text when `TIPOLOGIA_CONDIZIONE = 99`), `ModalitaAttivazione/DESCRIZIONE` (585);
- 100–500: `Dispacciamento/VALORE_DISP` (449, only with `TIPO_DISPACCIAMENTO = 99`), `CaratteristicheOfferta/*` (641: POTENZA_MIN/MAX, CONSUMO_MIN/MAX), `ZoneOfferta/*` (322: REGIONE/PROVINCIA/COMUNE), `ProdottiServiziAggiuntivi/*` (258), `ComponentiRegolate/CODICE` (75);
- fewer than 100: `RiferimentiPrezzoEnergia/COEFFICIENTE` (40) and `ALTRO` (25), `Sconto/CODICE_COMPONENTE_FASCIA` (27), `OffertaDual/OFFERTE_CONGIUNTE_GAS` (3).

Inside components they go into `componente.extra_json` (136 rows): `CONSUMO_DA` (103), `CONSUMO_A` (65), `PeriodoValidita/VALIDO_FINO` (25), `PeriodoValidita/DURATA` (12), `TIPO_PREZZO` (4).

## 4. Code values

All encoded fields use the track codes, except one case (§11).

| Field | Observed values (offer) |
|---|---|
| `tipo_mercato` | 01 = 3,540 |
| `tipo_cliente` | 01 domestic 1,906, 02 other uses 1,634 |
| `tipo_offerta` | 02 variable 2,893, 01 fixed 646, 04 mixed 1 |
| `offerta_singola` | SI 3,503, NO 37 |
| `tipologia_att_contr` | 99 always 2,474, 01 supplier switch 1,017, 02 first activation 26, 04 transfer 18, 03 reactivation 5 |
| `idx_prezzo_energia` | 12 monthly PUN 2,793, 01 quarterly PUN 107, 08 bi-monthly PUN 9, 05 quarterly PE 1, absent 630 |
| `modalita_pagamento` | 01 2,349, 04 638, 99 445, 03 57, 02 51 |
| `tipo_dispacciamento` | 14 CdispD 1,870, 01 1,113, 11 301, 09 105, 02 66, 13 37, 99 18, 10 13, 12 5, **03 12 (outside the track)** |
| `macroarea` | 04 energy price 8,235, 01 fixed commercialization 3,932, 06 FER/green 1,621, 02 energy charge 1,470, 05 one-off 11 |
| component `tipologia` | 01 standard 13,958, 02 optional 1,311 |
| `unita_misura` | 03 €/kWh 11,241, 01 €/year 3,947, 02 €/kW 44, 05 € 37 |
| `fascia` | absent 4,028, 01 4,658, 02 3,216, 03 3,216, 91 two-rate 113, 07 Peak 19, 08 OffPeak 19 |
| `tipologia_condizione` | 01 activation 2,691, 99 other 1,446, 03 withdrawal 401, 04 multi-year 279, 02 deactivation 228, 05 withdrawal charges 141 |
| `limitante` | 02 no 4,192, 01 yes 994 |

`durata`: 12 months for 1,759 offers, `-1` (indefinite) 1,066, then 24/36/60/72/…; `garanzie` is free text (often "NO").

## 5. Repeated elements

Within the same offer, and therefore stored as a list in `extra_json` while the column holds the first value:

| Path | Offers | Maximum in one offer |
|---|---|---|
| `MetodoPagamento/MODALITA_PAGAMENTO` | 3,540 | 5 |
| `DettaglioOfferta/TIPOLOGIA_ATT_CONTR` | 3,540 | 5 |
| `Dispacciamento/TIPO_DISPACCIAMENTO` | 3,540 | 9 |
| `DettaglioOfferta/ModalitaAttivazione/MODALITA` | 1,212 | 6 |
| `Sconto/NOME` | 474 | 6 |
| `ZoneOfferta/COMUNE` | 91 | 659 |

Components per offer: 1 to 16 (mode 4). Conditions per offer: 1 to 16 (mode 2).

In the same offer the pair (macroarea, fascia) appears on several components (1,527 cases), usually because they are different components with the same macroarea name (for example several energy-price entries). The exact same component name repeats instead in only 86 cases, all with `CONSUMO_DA`/`CONSUMO_A` (consumption tiers) or `PeriodoValidita` set: the long format keeps them as separate rows.

## 6. Empty fields

`idx_prezzo_energia` 630 (all fixed-price offers, see §9), `url_offerta` 388, `url_sito` 12, `telefono` 0, `descrizione` 0. No null `componente.prezzo`. `fascia` absent in 4,028 components out of 15,269 (fixed charges and components not tied to bands). `extra_json` non-null for all offers (because of the repeated known paths).

## 7. Duplicates

No duplicated `(piva, cod_offerta)` key and no offer without a key in the file: the 3,540 rows correspond to 3,540 distinct keys.

## 8. Dates

`data_inizio` 2022-11-08 → 2026-10-15; `data_fine` up to sentinels used as "no expiry" (2099-12-31 293 times, then 2044/2050/2055…). Dates are converted to ISO 8601 with the `Europe/Rome` time zone; the time is often 00:00:00 or 23:59:59. Default queries will have to filter `data_fine >= today`.

## 9. Fixed-price offers (how they are represented)

646 offers with `tipo_offerta = 01`. Compared with variable ones:

- 630 out of 646 have no `RiferimentiPrezzoEnergia` (no index): the price is in the components, `macroarea 04` (energy price) with `unita_misura 03` (€/kWh) — 667 rows — and `macroarea 02` (energy charge) 192 rows;
- 16 fixed offers still have an index (12/01/08): a mixed representation, to be handled in phase 4 as indexed (the index is there);
- like variable ones, fixed offers have fixed charges (`macroarea 01`, `unita_misura 01`) and FER/green components (`macroarea 06`);
- `fascia` absent in 718 component rows of fixed offers (single price) and set in 1,280 (fixed offers with a per-band price, including two-rate 91 and Peak/OffPeak 07/08);
- the only `04` (mixed) offer has two rows with `TIPO_PREZZO` (01/02) in the intervals, as the track provides only for `TIPO_OFFERTA = 04`.

## 10. Consequences

- The schema of §6 holds without changes: no new field is mandatory for the phase-A calculation, which can read `componente` by macroarea/fascia and `extra_json` for the band structure (`TIPOLOGIA_FASCE`) and the duration.
- Out of the data model (and therefore out of the calculation until the user asks): discounts, zones, additional products/services, power/consumption characteristics, regulated components chosen by the seller.
- Phase 4 must handle: offers without an index, offers with several indexes, components without a band (single price), bands 91/07/08 and `durata = -1`.

## 11. Open questions that emerged

- `TIPO_DISPACCIAMENTO = 03` (12 variable offers, all with `data_fine` in 2026 or a sentinel) is not defined in track v5.0: a legacy code or a seller typo. It is not an unknown path (the field is known) but the value has no official decoding: noted in `docs/open_questions.md`.
- The 16 fixed offers with an index and the single mixed one must be clarified with the user before calculating their cost.
