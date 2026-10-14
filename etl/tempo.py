"""Fuso orario del mercato italiano e date di riferimento."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("Europe/Rome")


def oggi() -> str:
    """Data odierna in `Europe/Rome`, formato ISO (`AAAA-MM-GG`)."""
    return datetime.now(FUSO).date().isoformat()
