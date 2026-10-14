"""Esecuzione ETL: validazioni, swap atomico, etl_run, storico copiato."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from etl.esegui import EsitoEsecuzione, esegui, ultimo_run

FIXTURE_XML = Path(__file__).parent / "fixtures" / "offerta_estratto.xml"
FIXTURE_CSV = Path(__file__).parent / "fixtures" / "PO_Parametri_Mercato_Libero_E_20261014.csv"
SNAPSHOT = "2026-10-14"

_OFFERTA = """<offerta>
  <IdentificativiOfferta>
    <PIVA_UTENTE>{piva}</PIVA_UTENTE>
    <COD_OFFERTA>{cod}</COD_OFFERTA>
  </IdentificativiOfferta>
  <DettaglioOfferta>
    <NOME_OFFERTA>OFFERTA {i}</NOME_OFFERTA>
    <TIPO_MERCATO>01</TIPO_MERCATO>
    <OFFERTA_SINGOLA>SI</OFFERTA_SINGOLA>
    <TIPO_CLIENTE>02</TIPO_CLIENTE>
    <TIPO_OFFERTA>02</TIPO_OFFERTA>
    <DURATA>-1</DURATA>
    <GARANZIE>NO</GARANZIE>
  </DettaglioOfferta>
  <RiferimentiPrezzoEnergia><IDX_PREZZO_ENERGIA>12</IDX_PREZZO_ENERGIA></RiferimentiPrezzoEnergia>
  <ValiditaOfferta>
    <DATA_INIZIO>21/07/2026_12:25:58</DATA_INIZIO>
    <DATA_FINE>10/10/2026_23:59:59</DATA_FINE>
  </ValiditaOfferta>
  <ComponenteImpresa>
    <NOME>SPREAD</NOME><MACROAREA>04</MACROAREA><TIPOLOGIA>01</TIPOLOGIA>
    <IntervalloPrezzi>
      <FASCIA_COMPONENTE>01</FASCIA_COMPONENTE>
      <PREZZO>0.0132</PREZZO>
      <UNITA_MISURA>03</UNITA_MISURA>
    </IntervalloPrezzi>
  </ComponenteImpresa>
</offerta>"""


def xml_con(n: int) -> Path:
    """XML con `n` offerte distinte, scritto in una cartella temporanea."""
    offerte = "\n".join(
        _OFFERTA.format(piva=f"0000000000{i:02d}", cod=f"COD{i:02d}", i=i) for i in range(1, n + 1)
    )
    percorso = Path(f"/tmp/offerte_finte_{n}.xml")
    percorso.write_text(f"<ListaOfferteMercatoLibero>{offerte}</ListaOfferteMercatoLibero>")
    return percorso


def _conta(db: Path, tabella: str) -> int:
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        return int(conn.execute(f"SELECT count(*) FROM {tabella}").fetchone()[0])


def test_primo_run_ok(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    esito = esegui(
        FIXTURE_XML,
        db=db,
        snapshot_date=SNAPSHOT,
        parametri=FIXTURE_CSV,
        sorgente="fixture",
        sha256="a" * 64,
    )

    assert esito.esito == "ok"
    assert esito.codice is None
    assert esito.n_offerte == 1
    assert esito.percorsi_sconosciuti == ()
    assert esito.note == ()
    assert db.is_file()
    assert not (tmp_path / "offerte.db.prev").exists()
    assert not (tmp_path / "offerte.db.new").exists()
    assert _conta(db, "offerta") == 1
    assert _conta(db, "componente") == 4
    assert _conta(db, "condizione") == 1
    assert _conta(db, "parametro") == 6

    registro = ultimo_run(db)
    assert registro is not None
    assert registro["esito"] == "ok"
    assert registro["sorgente"] == "fixture"
    assert registro["sha256"] == "a" * 64
    assert registro["n_offerte"] == 1
    assert registro["percorsi_sconosciuti"] == 0


def test_secondo_run_crea_prev_e_non_duplica(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    esegui(FIXTURE_XML, db=db, snapshot_date=SNAPSHOT, parametri=FIXTURE_CSV)
    esegui(FIXTURE_XML, db=db, snapshot_date="2026-10-15", parametri=FIXTURE_CSV)

    assert (tmp_path / "offerte.db.prev").is_file()
    assert _conta(db, "offerta") == 1
    assert _conta(db, "componente") == 4
    assert _conta(db, "etl_run") == 2
    assert _conta(db, "parametro") == 6


def test_storico_dei_parametri_si_accumula(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    esegui(FIXTURE_XML, db=db, snapshot_date=SNAPSHOT, parametri=FIXTURE_CSV)

    nuovo = tmp_path / "PO_Parametri_Mercato_Libero_E_20261015.csv"
    nuovo.write_text(FIXTURE_CSV.read_text(encoding="utf-8").replace("23.04", "24.00"))
    esegui(FIXTURE_XML, db=db, snapshot_date="2026-10-15", parametri=nuovo)

    assert _conta(db, "parametro") == 12
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        valore = conn.execute(
            "SELECT valore FROM parametro WHERE nome = 'pcv_a' AND riferimento = '2026-10-15'"
        ).fetchone()[0]
    assert valore == "24.00"


def test_xml_troncato_non_sostituisce_il_db(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    esegui(FIXTURE_XML, db=db, snapshot_date=SNAPSHOT, parametri=FIXTURE_CSV)

    rotto = tmp_path / "troncato.xml"
    rotto.write_text(FIXTURE_XML.read_text(encoding="utf-8")[:200], encoding="utf-8")
    esito = esegui(rotto, db=db, snapshot_date="2026-10-15", parametri=FIXTURE_CSV)

    assert esito.esito == "errore"
    assert esito.codice == "xml_non_valido"
    assert _conta(db, "offerta") == 1
    assert _conta(db, "componente") == 4
    assert not (tmp_path / "offerte.db.new").exists()
    assert not (tmp_path / "offerte.db.prev").exists()
    registro = ultimo_run(db)
    assert registro is not None
    assert registro["esito"] == "errore"


def test_parametri_obbligatori_mancanti_bloccano_lo_swap(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    parziale = tmp_path / "PO_Parametri_Mercato_Libero_E_20261014.csv"
    parziale.write_text("nome_parametro,valore,descrizione\npcv_a,23.04,Quota fissa\n")

    esito = esegui(FIXTURE_XML, db=db, snapshot_date=SNAPSHOT, parametri=parziale)

    assert esito.esito == "errore"
    assert esito.codice == "parametri_mancanti"
    assert "lambda" in " ".join(esito.note)
    assert not db.exists()
    assert not (tmp_path / "offerte.db.new").exists()


def test_calo_delle_offerte_blocca_lo_swap(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    esegui(xml_con(10), db=db, snapshot_date=SNAPSHOT, parametri=FIXTURE_CSV)

    esito = esegui(xml_con(4), db=db, snapshot_date="2026-10-15", parametri=FIXTURE_CSV)

    assert esito.esito == "errore"
    assert esito.codice == "troppe_poche_offerte"
    assert _conta(db, "offerta") == 10
    registro = ultimo_run(db)
    assert registro is not None
    assert registro["esito"] == "errore"


def test_run_senza_parametri_e_un_avviso(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    esito = esegui(FIXTURE_XML, db=db, snapshot_date=SNAPSHOT)

    assert esito.esito == "ok"
    assert any("parametri" in nota for nota in esito.note)
    assert _conta(db, "offerta") == 1


def test_offerte_scartate_finiscono_nelle_note(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    esegui(xml_con(3), db=db, snapshot_date=SNAPSHOT, parametri=FIXTURE_CSV)

    misto = Path("/tmp/offerte_miste.xml")
    valide = xml_con(2).read_text(encoding="utf-8").removesuffix("</ListaOfferteMercatoLibero>")
    misto.write_text(
        valide + "<offerta><DettaglioOfferta><NOME_OFFERTA>SENZA CHIAVE</NOME_OFFERTA>"
        "</DettaglioOfferta></offerta></ListaOfferteMercatoLibero>"
    )
    esito = esegui(misto, db=db, snapshot_date="2026-10-15", parametri=FIXTURE_CSV)

    assert esito.esito == "ok"
    assert any("scartate" in nota for nota in esito.note)
    assert _conta(db, "offerta") == 2


def test_nessuna_offerta_blocca_lo_swap(tmp_path: Path) -> None:
    db = tmp_path / "offerte.db"
    senza_chiave = Path("/tmp/offerte_senza_chiave.xml")
    senza_chiave.write_text(
        "<ListaOfferteMercatoLibero><offerta><DettaglioOfferta>"
        "<NOME_OFFERTA>SENZA CHIAVE</NOME_OFFERTA></DettaglioOfferta></offerta>"
        "</ListaOfferteMercatoLibero>"
    )
    esito = esegui(senza_chiave, db=db, snapshot_date=SNAPSHOT, parametri=FIXTURE_CSV)

    assert esito.esito == "errore"
    assert esito.codice == "nessuna_offerta"
    assert ultimo_run(db) is None


def test_esito_immutabile() -> None:
    esito = EsitoEsecuzione(esito="ok", db=Path("/tmp/x.db"))
    assert esito.n_offerte == 0
    assert esito.note == ()
    assert esito.non_modificato is False


def test_ultimo_run_su_db_inesistente(tmp_path: Path) -> None:
    assert ultimo_run(tmp_path / "manca.db") is None


@pytest.mark.parametrize("tabella", ["offerta", "componente", "condizione", "etl_run"])
def test_schema_nel_db_nuovo(tmp_path: Path, tabella: str) -> None:
    db = tmp_path / "offerte.db"
    esegui(FIXTURE_XML, db=db, snapshot_date=SNAPSHOT, parametri=FIXTURE_CSV)
    assert _conta(db, tabella) >= 0
