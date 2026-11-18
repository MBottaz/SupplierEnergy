"""Decodifica geografica delle zone delle offerte.

I codici `REGIONE`, `PROVINCIA` e `COMUNE` di `offerta/ZoneOfferta/*` sono
**codici ISTAT** (regione 2 cifre, provincia 3 cifre, comune 6 cifre), come dice
il tracciato ufficiale delle offerte. Questo modulo tiene le tabelle ufficiali
per tradurre i nomi in codici (filtri) e i codici in nomi (risultato) per i due
livelli con un elenco breve e non ambiguo: regioni (20) e province (107). I
comuni (circa 7.900) non sono tradotti qui: restano codici ISTAT a 6 cifre.

Fonte delle tabelle: ISTAT, "Elenco dei comuni italiani" (denominazioni ufficiali
di regioni e province), pubblicato su
`https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv`,
consultato il 2026-11-18. Le tabelle sono statiche: si aggiornano solo quando
ISTAT cambia denominazioni o province.
"""

from __future__ import annotations

import unicodedata

from offerte.errori import InputNonValido

#: Codice ISTAT (2 cifre) -> denominazione ufficiale della regione.
REGIONI: dict[str, str] = {
    "01": "Piemonte",
    "02": "Valle d'Aosta/Vallée d'Aoste",
    "03": "Lombardia",
    "04": "Trentino-Alto Adige/Südtirol",
    "05": "Veneto",
    "06": "Friuli-Venezia Giulia",
    "07": "Liguria",
    "08": "Emilia-Romagna",
    "09": "Toscana",
    "10": "Umbria",
    "11": "Marche",
    "12": "Lazio",
    "13": "Abruzzo",
    "14": "Molise",
    "15": "Campania",
    "16": "Puglia",
    "17": "Basilicata",
    "18": "Calabria",
    "19": "Sicilia",
    "20": "Sardegna",
}

#: Codice ISTAT (3 cifre) -> denominazione ufficiale della provincia.
PROVINCE: dict[str, str] = {
    "001": "Torino",
    "002": "Vercelli",
    "003": "Novara",
    "004": "Cuneo",
    "005": "Asti",
    "006": "Alessandria",
    "007": "Valle d'Aosta/Vallée d'Aoste",
    "008": "Imperia",
    "009": "Savona",
    "010": "Genova",
    "011": "La Spezia",
    "012": "Varese",
    "013": "Como",
    "014": "Sondrio",
    "015": "Milano",
    "016": "Bergamo",
    "017": "Brescia",
    "018": "Pavia",
    "019": "Cremona",
    "020": "Mantova",
    "021": "Bolzano/Bozen",
    "022": "Trento",
    "023": "Verona",
    "024": "Vicenza",
    "025": "Belluno",
    "026": "Treviso",
    "027": "Venezia",
    "028": "Padova",
    "029": "Rovigo",
    "030": "Udine",
    "031": "Gorizia",
    "032": "Trieste",
    "033": "Piacenza",
    "034": "Parma",
    "035": "Reggio nell'Emilia",
    "036": "Modena",
    "037": "Bologna",
    "038": "Ferrara",
    "039": "Ravenna",
    "040": "Forlì-Cesena",
    "041": "Pesaro e Urbino",
    "042": "Ancona",
    "043": "Macerata",
    "044": "Ascoli Piceno",
    "045": "Massa-Carrara",
    "046": "Lucca",
    "047": "Pistoia",
    "048": "Firenze",
    "049": "Livorno",
    "050": "Pisa",
    "051": "Arezzo",
    "052": "Siena",
    "053": "Grosseto",
    "054": "Perugia",
    "055": "Terni",
    "056": "Viterbo",
    "057": "Rieti",
    "058": "Roma",
    "059": "Latina",
    "060": "Frosinone",
    "061": "Caserta",
    "062": "Benevento",
    "063": "Napoli",
    "064": "Avellino",
    "065": "Salerno",
    "066": "L'Aquila",
    "067": "Teramo",
    "068": "Pescara",
    "069": "Chieti",
    "070": "Campobasso",
    "071": "Foggia",
    "072": "Bari",
    "073": "Taranto",
    "074": "Brindisi",
    "075": "Lecce",
    "076": "Potenza",
    "077": "Matera",
    "078": "Cosenza",
    "079": "Catanzaro",
    "080": "Reggio Calabria",
    "081": "Trapani",
    "082": "Palermo",
    "083": "Messina",
    "084": "Agrigento",
    "085": "Caltanissetta",
    "086": "Enna",
    "087": "Catania",
    "088": "Ragusa",
    "089": "Siracusa",
    "090": "Sassari",
    "091": "Nuoro",
    "092": "Cagliari",
    "093": "Pordenone",
    "094": "Isernia",
    "095": "Oristano",
    "096": "Biella",
    "097": "Lecco",
    "098": "Lodi",
    "099": "Rimini",
    "100": "Prato",
    "101": "Crotone",
    "102": "Vibo Valentia",
    "103": "Verbano-Cusio-Ossola",
    "108": "Monza e della Brianza",
    "109": "Fermo",
    "110": "Barletta-Andria-Trani",
    "111": "Sud Sardegna",
}

#: Codice ISTAT della provincia (3 cifre) -> codice ISTAT della regione (2 cifre).
REGIONE_DI_PROVINCIA: dict[str, str] = {
    "001": "01",
    "002": "01",
    "003": "01",
    "004": "01",
    "005": "01",
    "006": "01",
    "007": "02",
    "008": "07",
    "009": "07",
    "010": "07",
    "011": "07",
    "012": "03",
    "013": "03",
    "014": "03",
    "015": "03",
    "016": "03",
    "017": "03",
    "018": "03",
    "019": "03",
    "020": "03",
    "021": "04",
    "022": "04",
    "023": "05",
    "024": "05",
    "025": "05",
    "026": "05",
    "027": "05",
    "028": "05",
    "029": "05",
    "030": "06",
    "031": "06",
    "032": "06",
    "033": "08",
    "034": "08",
    "035": "08",
    "036": "08",
    "037": "08",
    "038": "08",
    "039": "08",
    "040": "08",
    "041": "11",
    "042": "11",
    "043": "11",
    "044": "11",
    "045": "09",
    "046": "09",
    "047": "09",
    "048": "09",
    "049": "09",
    "050": "09",
    "051": "09",
    "052": "09",
    "053": "09",
    "054": "10",
    "055": "10",
    "056": "12",
    "057": "12",
    "058": "12",
    "059": "12",
    "060": "12",
    "061": "15",
    "062": "15",
    "063": "15",
    "064": "15",
    "065": "15",
    "066": "13",
    "067": "13",
    "068": "13",
    "069": "13",
    "070": "14",
    "071": "16",
    "072": "16",
    "073": "16",
    "074": "16",
    "075": "16",
    "076": "17",
    "077": "17",
    "078": "18",
    "079": "18",
    "080": "18",
    "081": "19",
    "082": "19",
    "083": "19",
    "084": "19",
    "085": "19",
    "086": "19",
    "087": "19",
    "088": "19",
    "089": "19",
    "090": "20",
    "091": "20",
    "092": "20",
    "093": "06",
    "094": "14",
    "095": "20",
    "096": "01",
    "097": "03",
    "098": "03",
    "099": "08",
    "100": "09",
    "101": "18",
    "102": "18",
    "103": "01",
    "108": "03",
    "109": "11",
    "110": "16",
    "111": "20",
}


def _normalizza(testo: str) -> str:
    """Chiave di confronto: minuscole, senza accenti, apostrofi uniformati."""
    testo = testo.replace("\u2019", "'").replace("\u2018", "'")
    scomposto = unicodedata.normalize("NFKD", testo)
    senza_accenti = "".join(c for c in scomposto if not unicodedata.combining(c))
    return " ".join(senza_accenti.casefold().split())


_REGIONI_PER_NOME = {_normalizza(nome): codice for codice, nome in REGIONI.items()}
_PROVINCE_PER_NOME = {_normalizza(nome): codice for codice, nome in PROVINCE.items()}


def _risolvi(
    valore: str,
    per_nome: dict[str, str],
    per_codice: dict[str, str],
    larghezza: int,
    etichetta: str,
) -> str:
    nome = _normalizza(valore)
    if nome in per_nome:
        return per_nome[nome]
    if valore.isdigit():
        codice = valore.zfill(larghezza)
        if codice in per_codice:
            return codice
    raise InputNonValido(
        f"{etichetta} deve essere una denominazione ufficiale "
        f"({', '.join(per_codice.values())}) oppure il codice ISTAT "
        f"a {larghezza} cifre"
    )


def codice_regione(valore: str) -> str:
    """Codice ISTAT a 2 cifre da una denominazione ufficiale o da un codice."""
    return _risolvi(valore, _REGIONI_PER_NOME, REGIONI, 2, "regione")


def codice_provincia(valore: str) -> str:
    """Codice ISTAT a 3 cifre da una denominazione ufficiale o da un codice."""
    return _risolvi(valore, _PROVINCE_PER_NOME, PROVINCE, 3, "provincia")


def nome_regione(codice: str) -> str | None:
    """Denominazione ufficiale di una regione, `None` se il codice è ignoto."""
    return REGIONI.get(codice)


def nome_provincia(codice: str) -> str | None:
    """Denominazione ufficiale di una provincia, `None` se il codice è ignoto."""
    return PROVINCE.get(codice)


def regione_di_provincia(codice: str) -> str | None:
    """Codice ISTAT della regione che contiene la provincia, `None` se ignota."""
    return REGIONE_DI_PROVINCIA.get(codice)


def elenco_regioni() -> str:
    """Nomi ufficiali delle regioni, per descrizioni ed errori."""
    return ", ".join(REGIONI.values())


def elenco_province() -> str:
    """Nomi ufficiali delle province, per descrizioni ed errori."""
    return ", ".join(PROVINCE.values())
