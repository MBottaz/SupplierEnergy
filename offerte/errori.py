"""Errori strutturati della libreria `offerte`.

Ogni errore ha un `codice` stabile e un `messaggio` leggibile. Il messaggio non
contiene mai SQL, stack trace o percorsi interni: è ciò che viene restituito
all'agente, anche attraverso il server MCP.
"""

from __future__ import annotations


class ErroreOfferte(Exception):
    """Errore applicativo con codice stabile."""

    codice = "errore"

    def __init__(self, messaggio: str) -> None:
        super().__init__(messaggio)
        self.messaggio = messaggio

    def come_dizionario(self) -> dict[str, str]:
        """La forma strutturata restituita all'agente."""
        return {"codice": self.codice, "messaggio": self.messaggio}


class InputNonValido(ErroreOfferte):
    """Un filtro fuori contratto (tipo, lunghezza, intervallo, formato)."""

    codice = "input_non_valido"


class FiltroNonSupportato(ErroreOfferte):
    """Una chiave di filtro non prevista dal contratto."""

    codice = "filtro_non_supportato"


class DatabaseNonDisponibile(ErroreOfferte):
    """Il database manca, non è leggibile o non è un database valido."""

    codice = "database_non_disponibile"
