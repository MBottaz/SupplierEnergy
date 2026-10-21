# Questioni aperte

Dubbi su codici, formule, fonti e termini d'uso. Si procede sul resto e non si
indovina: qui sta cosa manca, cosa blocca e in quale fase si risolve.

## Aperte

1. **Licenza d'uso dei dati aperti del Portale Offerte**. Prima di
   ridistribuire i dati va verificata la licenza indicata nella pagina Open Data
   di `ilportaleofferte.it`: la pagina non la dichiara (verificato il 21/10/2026)
   e riguarda sia l'XML delle offerte sia il CSV "Prezzi storici" degli indici
   usato per il PUN. Blocca la fase 6 (servizio a terzi), non l'ETL. Una fonte
   terza dichiara CC BY 4.0, ma non è una fonte ufficiale: da confermare con
   ARERA / Acquirente Unico.
2. **URL e orari del CSV dei parametri**. L'XML ha un URL ufficiale (dato
   dall'utente, usato come default dalla CLI), il CSV no: per ora si carica il
   file locale. Servono anche la periodicità di pubblicazione e la data di
   riferimento esatta. Senza, `just etl-scarica` carica le offerte ma non i
   parametri. (La pagina Open Data pubblica anche un URL datato per i parametri:
   vedi "Risolte".)
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
8. **Termini d'uso del GME per il PUN**. Il sito `mercatoelettrico.org` è
   protetto da condizioni di utilizzo da accettare espressamente, con un
   disclaimer che vieta usi non consentiti di dati e informazioni: per la fase 3
   non si usa il GME, ma il CSV "Prezzi storici" del Portale Offerte. L'API del
   GME serve solo se servirà il PUN **giornaliero** (richiede credenziali che
   fornisce l'utente): prima di usarla vanno letti integralmente Condizioni di
   utilizzo e Disclaimer e annotato qui cosa consentono a un servizio verso
   terzi.
9. **Che serie è il "PUN (€/kWh)" mensile del file Prezzi storici** (fase 4).
   Il file pubblica un valore per mese senza dire come è pesato: media
   aritmetica dei PUN giornalieri o PUN Index GME, che il TIDE definisce come
   media dei prezzi zonali del MGP **ponderata per le quantità acquistate**?
   I valori coincidono con quelli di fonti terze che citano il Portale Offerte,
   ma il modo in cui risolvere `IDX_PREZZO_ENERGIA` per un'offerta indicizzata
   va confermato sul tracciato e con l'utente prima di calcolare un costo.
10. **Stabilità dell'URL del file Prezzi storici**. Il CSV sta in una cartella
    `resources/cms/documents/` con nome opaco (`0c916785….csv`) e `Last-Modified`
    mensile (07/10/2026 con dati fino a settembre 2026). Non è un URL datato: se
    il Portale lo sostituisce, il download fallisce. La pagina Open Data resta
    il riferimento; per ora l'URL è una costante (`etl/pun.py`) e si può
    override con `--url`.
11. **Metodologia ufficiale del Portale Offerte per la spesa totale** (fase B,
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
- **URL datato del CSV dei parametri**: la pagina Open Data linka anche
  `.../opendata/csv/parametriML/AAAA_MM/PO_Parametri_Mercato_Libero_E_AAAAMMGG.csv`
  (visto il 21/10/2026, aggiornato lo stesso giorno delle offerte). La data nel
  nome resta il riferimento. Cablare il download in `etl scarica` è un task a
  parte: per ora il CSV si passa con `--parametri`.
- **File "Prezzi storici" del Portale Offerte come fonte del PUN mensile**:
  CSV `;` in cp1252, colonna `AnnoMese` (`AAAAMM`) e `PUN (€/kWh)`, un valore per
  mese dal 2020; unità dichiarata nell'intestazione e convertita in €/MWh.
  Serie salvata: `PUN_MENSILE` (`etl/pun.py`). Verificato sui dati reali: 81
  mesi, 2020-01 → 2026-09, agosto 2022 = 543,15 €/MWh (picco).
