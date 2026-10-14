# Questioni aperte

Dubbi su codici, formule, fonti e termini d'uso. Si procede sul resto e non si
indovina: qui sta cosa manca, cosa blocca e in quale fase si risolve.

## Aperte

1. **Licenza d'uso dell'XML open data del Portale Offerte** (fase 2). Prima di
   ridistribuire i dati va verificata la licenza indicata nella pagina Open Data
   di `ilportaleofferte.it`. Blocca la fase 6 (servizio a terzi), non l'ETL.
2. **URL di download dell'XML open data** (fase 2). Da leggere dalla pagina
   Open Data ufficiale: non è stato inventato un endpoint.
3. **Corrispondenza fra XML pubblicato e tracciato v5.0** (fase 2). Il parser
   segue il tracciato ufficiale, ma l'XML pubblicato potrebbe contenere campi
   che il tracciato non descrive: la prima validazione sui dati reali
   (`docs/validazione_xml.md`, contatore `percorsi_sconosciuti`) dirà se esistono
   scostamenti da assorbire in `etl/parser.py`.
4. **Offerte a prezzo fisso** (fase 2). La fixture è una variabile con SPREAD in
   fascia: come sono rappresentate le fisse nell'XML va verificato sui dati
   reali (sezione `TipoPrezzo`/`ComponenteImpresa`), non dedotto.
5. **Mappatura BTA** `_b1`…`_b6` → potenza/uso del cliente (fase 2, §7) e
   **unità di misura dei parametri** del CSV (assenti dal file): servono i
   documenti ufficiali della raccolta parametri. Se non reperibili, chiedere
   all'utente prima di compilare `parametro_meta`.
6. **Codici "Altro"** (`IDX_PREZZO_ENERGIA=99`, `TIPO_DISPACCIAMENTO=99`,
   `MODALITA_PAGAMENTO=99`…): il tracciato li ammette ma il valore vero sta in
   un campo di testo libero. Come trattarli nel calcolo (fase 4) va deciso:
   probabile `non_calcolabile` con motivo, mai un costo inventato.
7. **Termini d'uso del GME per il PUN** (fase 3): uso commerciale e
   ridistribuzione vincolano il modo in cui il servizio può essere offerto a
   terzi. Da verificare insieme alle credenziali dell'API.
8. **Metodologia ufficiale del Portale Offerte per la spesa totale** (fase B,
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
