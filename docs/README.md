# Documentazione

Indice della cartella. Lo stato attuale e i comandi stanno in `README.md` (radice);
le regole di lavoro in `AGENTS.md`.

## Il sistema esistente

- `architettura.md` — design del sistema, modello dati, ETL, sicurezza: il
  riferimento stabile a cui allineare il codice.
- `contratto_cerca_offerte.md` — contratto della funzione e del tool
  `cerca_offerte` già implementati.
- `validazione_xml.md` — validazione aggregata dell'XML reale caricato dall'ETL.
- `questioni_aperte.md` — dubbi su codici, fonti, formule e termini d'uso.

## Cosa resta da fare

- `goals.md` — obiettivi non ancora implementati, in ordine.
- `task.md` — task operativi per completare un obiettivo (ora: il server MCP
  minimale di ricerca, completato).

## Dati di riferimento

- `PO_Parametri_Mercato_Libero_E_20261014.csv` — estratto del CSV dei parametri
  usato dai comandi `etl-*`.
