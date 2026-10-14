# Validazione dell'XML reale

Riassunto (solo aggregati, nessun dato grezzo) del primo caricamento dell'XML
open data completo, come richiesto da `PROMPT.md` fase 2.

## Come è stato prodotto

| Voce | Valore |
|---|---|
| File | `raw/2026-10-14/PO_Offerte_E_MLIBERO_20261014.xml` (20,7 MB) |
| SHA-256 | `7de4c0df3fc0dcc22589a4d28e43ac09dd75ed088bdad3da2af1e3f27f627dee` |
| Parametri | `docs/PO_Parametri_Mercato_Libero_E_20261014.csv` — SHA-256 `801bb798d551656be3e7e9db45431d81fc0bb5df147dfb4f94b722e577e639d0` |
| Tracciato di riferimento | SII, "Trasmissione Offerte Mercato Retail" v5.0, 15/12/2025, §7 (in `etl/codifiche.py`) |
| Comando | `just etl-reale` (≈5 s) |

Il DB è ricostruibile da zero dallo stesso raw; l'esecuzione registrata in
`etl_run` ha `esito = ok` e `percorsi_sconosciuti = 0`.

## 1. Copertura

- 3.540 offerte, 15.269 componenti, 5.186 condizioni, 338 venditori distinti
  (il maggiore con 203 offerte), 100 parametri, 82 decodifiche.
- Ogni offerta ha `piva`, `cod_offerta`, date di validità e almeno una
  componente; 2 offerte su 3.540 non hanno `ComponenteImpresa` (si caricano
  senza righe in `componente`).
- 39 mesi di validità coperti: `data_inizio` dal 2022-11 al 2026-10, quasi
  tutte nel 2026 (3.183); 2 offerte non ancora attive alla data di riferimento,
  0 scadute (il file pubblica le offerte attive).

## 2. Percorsi sconosciuti: zero

Nessun percorso fuori dal tracciato e dal parser (`percorsi_sconosciuti = 0`).
L'XML pubblicato usa un namespace di default
(`http://www.acquirenteunico.it/schemas/SII_AU/OffertaRetail/01`): il parser
confronta i percorsi senza namespace, e regge entrambe le forme.

Due campi del tracciato non compaiono in questo snapshot e sono comunque già
previsti come noti: `RiferimentiPrezzoEnergia/FASCIA_PREZZO` (se assente, il
prezzo vale per tutti i consumi) e `TipoPrezzo/FasceOrarieSettimanali/*` (per
`TIPOLOGIA_FASCE` = 03/07 il tracciato dice che si ereditano le fasce standard).

Nomi reali diversi da come erano stati trascritti dal tracciato PDF:
`TIPO_FASCE` è nel file `TipoPrezzo/TIPOLOGIA_FASCE` (plurale) e
`Dispacciamento/VALORE_DISP` (non `VALORE_DISPACCIAMENTO`). Il parser usa i
nomi reali.

## 3. Campi noti senza colonna (`extra_json`)

Restano in `extra_json` (e non contano come sconosciuti) i percorsi del tracciato
che il modello dati di §6 non modella. Numerosità (in ordine decrescente):

- ripetuti su tutti i tracciati caricati: `TIPOLOGIA_FASCE`,
  `MetodoPagamento/MODALITA_PAGAMENTO`, `Dispacciamento/TIPO_DISPACCIAMENTO`,
  `Dispacciamento/NOME`, `DettaglioOfferta/TIPOLOGIA_ATT_CONTR`,
  `ModalitaAttivazione/MODALITA`;
- 1.000-2.000 offerte: `MetodoPagamento/DESCRIZIONE` (1.751),
  `Dispacciamento/DESCRIZIONE` (1.488), `DettaglioOfferta/DOMESTICO_RESIDENTE` (1.430);
- 500-1.000: `Sconto/*` (968 offerte con sconto; nome, descrizione, validità,
  IVA, condizioni, periodi, `PrezziSconto/*`), `CondizioniContrattuali/ALTRO`
  (868, il testo libero quando `TIPOLOGIA_CONDIZIONE = 99`),
  `ModalitaAttivazione/DESCRIZIONE` (585);
- 100-500: `Dispacciamento/VALORE_DISP` (449, solo con `TIPO_DISPACCIAMENTO = 99`),
  `CaratteristicheOfferta/*` (641: POTENZA_MIN/MAX, CONSUMO_MIN/MAX),
  `ZoneOfferta/*` (322: REGIONE/PROVINCIA/COMUNE), `ProdottiServiziAggiuntivi/*`
  (258), `ComponentiRegolate/CODICE` (75);
- meno di 100: `RiferimentiPrezzoEnergia/COEFFICIENTE` (40) e `ALTRO` (25),
  `Sconto/CODICE_COMPONENTE_FASCIA` (27), `OffertaDual/OFFERTE_CONGIUNTE_GAS` (3).

Dentro le componenti finiscono in `componente.extra_json` (136 righe):
`CONSUMO_DA` (103), `CONSUMO_A` (65), `PeriodoValidita/VALIDO_FINO` (25),
`PeriodoValidita/DURATA` (12), `TIPO_PREZZO` (4).

## 4. Valori dei codici

Tutti i campi codificati usano i codici del tracciato, tranne un caso (§11).

| Campo | Valori osservati (offerta) |
|---|---|
| `tipo_mercato` | 01 = 3.540 |
| `tipo_cliente` | 01 domestico 1.906, 02 altri usi 1.634 |
| `tipo_offerta` | 02 variabile 2.893, 01 fisso 646, 04 mista 1 |
| `offerta_singola` | SI 3.503, NO 37 |
| `tipologia_att_contr` | 99 sempre 2.474, 01 cambio fornitore 1.017, 02 prima attivazione 26, 04 voltura 18, 03 riattivazione 5 |
| `idx_prezzo_energia` | 12 PUN mensile 2.793, 01 PUN trimestrale 107, 08 PUN bimestrale 9, 05 PE trimestrale 1, assente 630 |
| `modalita_pagamento` | 01 2.349, 04 638, 99 445, 03 57, 02 51 |
| `tipo_dispacciamento` | 14 CdispD 1.870, 01 1.113, 11 301, 09 105, 02 66, 13 37, 99 18, 10 13, 12 5, **03 12 (fuori tracciato)** |
| `macroarea` | 04 prezzo quota energia 8.235, 01 commercializzazione fissa 3.932, 06 FER/verde 1.621, 02 quota energia 1.470, 05 una tantum 11 |
| `tipologia` componente | 01 standard 13.958, 02 opzionale 1.311 |
| `unita_misura` | 03 €/kWh 11.241, 01 €/anno 3.947, 02 €/kW 44, 05 € 37 |
| `fascia` | assente 4.028, 01 4.658, 02 3.216, 03 3.216, 91 biorario 113, 07 Peak 19, 08 OffPeak 19 |
| `tipologia_condizione` | 01 attivazione 2.691, 99 altro 1.446, 03 recesso 401, 04 pluriennale 279, 02 disattivazione 228, 05 oneri di recesso 141 |
| `limitante` | 02 no 4.192, 01 sì 994 |

`durata`: 12 mesi 1.759 offerte, `-1` (indeterminata) 1.066, poi 24/36/60/72/…;
`garanzie` è testo libero (spesso "NO").

## 5. Elementi che si ripetono

Dentro la stessa offerta, e quindi salvati come lista in `extra_json` mentre la
colonna tiene il primo valore:

| Percorso | Offerte | Massimo in una offerta |
|---|---|---|
| `MetodoPagamento/MODALITA_PAGAMENTO` | 3.540 | 5 |
| `DettaglioOfferta/TIPOLOGIA_ATT_CONTR` | 3.540 | 5 |
| `Dispacciamento/TIPO_DISPACCIAMENTO` | 3.540 | 9 |
| `DettaglioOfferta/ModalitaAttivazione/MODALITA` | 1.212 | 6 |
| `Sconto/NOME` | 474 | 6 |
| `ZoneOfferta/COMUNE` | 91 | 659 |

Componenti per offerta: da 1 a 16 (la moda è 4). Condizioni per offerta: da 1 a
16 (moda 2).

Nella stessa offerta la coppia (macroarea, fascia) compare su più componenti
(1.527 casi), di solito perché sono componenti diverse con lo stesso nome di
macroarea (per esempio più voci di prezzo energia). Lo stesso identico nome di
componente ripete invece solo in 86 casi, tutti con `CONSUMO_DA`/`CONSUMO_A`
(scaglioni di consumo) o `PeriodoValidita` valorizzati: il formato "long" li
tiene come righe distinte.

## 6. Campi vuoti

`idx_prezzo_energia` 630 (tutte offerte a prezzo fisso, vedi §9),
`url_offerta` 388, `url_sito` 12, `telefono` 0, `descrizione` 0.
Nessun `componente.prezzo` nullo. `fascia` assente in 4.028 componenti su 15.269
(quote fisse e componenti non legate alle fasce). `extra_json` non nullo per
tutte le offerte (per via dei percorsi noti ripetuti).

## 7. Duplicati

Nessuna chiave `(piva, cod_offerta)` duplicata e nessuna offerta senza chiave nel
file: alle 3.540 righe corrispondono 3.540 chiavi distinte.

## 8. Date

`data_inizio` 2022-11-08 → 2026-10-15; `data_fine` fino a sentinelle usate come
"senza scadenza" (2099-12-31 293 volte, poi 2044/2050/2055…). Le date sono
convertite in ISO 8601 con fuso `Europe/Rome`; l'ora è spesso 00:00:00 o
23:59:59. Le query di default dovranno filtrare `data_fine >= oggi`.

## 9. Offerte a prezzo fisso (come sono rappresentate)

646 offerte `tipo_offerta = 01`. Rispetto alle variabili:

- 630 su 646 non hanno `RiferimentiPrezzoEnergia` (nessun indice): il prezzo è
  nelle componenti, `macroarea 04` (prezzo quota energia) con `unita_misura 03`
  (€/kWh) — 667 righe — e `macroarea 02` (quota energia) 192 righe;
- 16 offerte fisse hanno comunque un indice (12/01/08): rappresentazione mista,
  da trattare in fase 4 come indicizzate (l'indice c'è);
- come le variabili, le fisse hanno quote fisse (`macroarea 01`, `unita_misura 01`)
  e componenti FER/verde (`macroarea 06`);
- `fascia` assente in 718 righe di componenti di offerte fisse (prezzo unico) e
  valorizzata in 1.280 (fisse con prezzo per fascia, incluse biorarie 91 e
  Peak/OffPeak 07/08);
- l'unica offerta `04` (mista) ha due righe con `TIPO_PREZZO` (01/02) negli
  intervalli, come previsto dal tracciato solo per `TIPO_OFFERTA = 04`.

## 10. Conseguenze

- Lo schema di §6 regge senza modifiche: nessun campo nuovo è obbligatorio per
  il calcolo della fase A, che può leggere `componente` per macroarea/fascia e
  `extra_json` per la struttura delle fasce (`TIPOLOGIA_FASCE`) e la durata.
- Restano fuori dal modello dati (e quindi fuori dal calcolo finché l'utente non
  lo chiede): sconti, zone, prodotti/servizi aggiuntivi, caratteristiche di
  potenza/consumo, componenti regolate scelte dal venditore.
- La fase 4 deve saper gestire: offerte senza indice, offerte con più indici,
  componenti senza fascia (prezzo unico), fasce 91/07/08 e `durata = -1`.

## 11. Questioni aperte emerse

- `TIPO_DISPACCIAMENTO = 03` (12 offerte variabili, tutte con `data_fine` nel
  2026 o sentinella) non è definito nel tracciato v5.0: codice legacy o refuso
  del venditore. Non è un percorso sconosciuto (il campo è noto) ma il valore
  non ha decodifica ufficiale: annotato in `docs/questioni_aperte.md`.
- Le 16 offerte fisse con indice e l'unica mista vanno chiarite con l'utente
  prima di calcolarne il costo.
