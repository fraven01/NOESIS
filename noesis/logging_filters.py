"""Hilfsfilter für anlagenspezifisches Logging."""

from __future__ import annotations

import logging


class AnlageFilter(logging.Filter):
    """Filtert Logeinträge anhand der Anlagenummer."""

    def __init__(self, anlage: str) -> None:
        super().__init__()
        self.anlage = str(anlage)

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401 - Django-Style
        """Lässt nur Einträge für die konfigurierte Anlage passieren."""
        return getattr(record, "anlage", "") == self.anlage
