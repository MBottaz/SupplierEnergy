# Questioni aperte

Dubbi su codici, formule, fonti e termini d'uso. Si procede sul resto e non si
indovina: qui sta cosa manca, cosa blocca e in quale fase si risolve.

## Aperte

1. **Licenza d'uso dell'XML open data del Portale Offerte**. Prima di
   ridistribuire i dati va verificata la licenza indicata nella pagina Open Data
   di `ilportaleofferte.it`. Blocca la fase 6 (servizio a terzi), non l'ETL.
2. **URL e orari del CSV dei parametri**. L'XML ha un URL ufficiale (dato
   dall'utente, usato come default dalla CLI), il CSV no: per ora si carica il
   file locale. Servono anche la periodicità di pubblicazione e la data di
   riferimento esatta. Senza, `just etl-scarica` carica le offerte ma non i
   parametri.
3. **`TIPO_DISPACCIAMENTO = 03`** (12 offerte variabili, `data_fine` 2026 o
   sentinella). Il tracciato v5.0 non definisce il codice: o è legacy, o è un
   refuso del venditore. Va deciso se ignorarlo o mapparlo a "altro" nel calcolo.
4. **Mappatura BTA** `_b1`…`_b6` → potenza/uso del cliente e **unità di misura
   dei parametri** del CSV (assenti dal file): servono i documenti ufficiali
   della raccolta parametri. Se non reperibili, chiedere all'utente prima di
   compilare `parametro_meta`.
5. **Codici "Altro"** (`IDX_PREZZO_ENERGIA=99`, `TIPO_DISPACCIAMENTO=99`,
   `MODALITA_PAGAMENTO=99`…): il tracciato li ammette ma il valore vero sta in
   un campo di testo libero. Come trattarli nel calcolo (fase 4) va deciso:
   probabile `non_calcolabile` con motivo, mai un costo inventato.
6. **Offerte fisse con indice e offerta mista** (fase 4): 16 offerte
   `tipo_offerta=01` hanno comunque un `IDX_PREZZO_ENERGIA` e l'unica offerta
   `04` ha `TIPO_PREZZO` sugli intervalli. Vanno trattate come indicizzate? Da
   chiarire prima di calcolarne il costo.
7. **Sconti e promozioni** (fase 4): 968 offerte hanno `Sconto/*` in
   `extra_json`. La fase A non li include; se l'utente li vuole nel confronto
   serve una regola ufficiale (il Portale Offerte li applica alla spesa annua).
8. **Termini d'uso del GME per il PUN** (fase 3): uso commerciale e
   ridistribuzione vincolano il modo in cui il servizio può essere offerto a
   terzi. Da verificare insieme alle credenziali dell'API.
9. **Metodologia ufficiale del Portale Offerte per la spesa totale** (fase B,
   fuori scope finché l'utente non lo chiede): va trovata e citata nel codice.

## Risolte

- **Decodifiche del tracciato**: dal documento ufficiale "Funzionamento e
  Specifiche del Processo di Trasmissione Offerte Mercato Retail" v5.0
  (Acquirente Unico, 15/12/2025), sezione "7 Formato e tracciato delle Offerte".
  82 voci caricate in `codifica` da `etl/codifiche.py` (fonte e URL nel modulo).
  Include la periodicità nella descrizione di `IDX_PREZZO_ENERGIA`, perché lo
  stesso indice ha codici diversi per trimestrale/bimestrale/mensile.
- **Formato delle date** `gg/mm/aaaa_hh:mm:ss`: normalizzato in ISO 8601 con
  fuso `Europe/Rome` (tracciato, sezione `ValiditaOfferta`).
- **`DURATA = -1`**: dal tracciato significa durata indeterminata; salvata come
  stringa, senza interpretazioni.
- **Corrispondenza fra XML pubblicato e tracciato v5.0**: verificata sui dati
  reali (`docs/validazione_xml.md`): zero percorsi sconosciuti. Unici scarti di
  nome rispetto alla tabella del PDF: `TipoPrezzo/TIPOLOGIA_FASCE` (plurale) e
  `Dispacciamento/VALORE_DISP`; il parser usa i nomi reali.
- **Rappresentazione delle offerte a prezzo fisso**: documentata in
  `docs/validazione_xml.md` §9 (componenti `macroarea 04`/`02` in €/kWh, fascia
  solo se il prezzo dipende dalle fasce, indice assente in 630 su 646).
- **URL di download dell'XML open data**: fornito dall'utente
  (`.../offerteML/AAAA_MM/PO_Offerte_E_MLIBERO_AAAAMMGG.xml`), usato come default
  da `python -m etl scarica`.
