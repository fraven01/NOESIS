"""Hilfsfilter für Logging-Konfiguration."""

import logging


class Anlage2DBWriteFilter(logging.Filter):
    """Filtert SQL-Schreiboperationen für Anlage 2."""

    TARGET_TABLES = (
        "core_anlagenfunktionsmetadaten",
        "core_funktionsergebnis",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        """Gibt nur Schreiboperationen auf Anlage 2-Tabellen frei."""

        sql: str = getattr(record, "sql", "")
        if not sql:
            return record.name.startswith("core.llm_tasks")
        upper_sql = sql.upper()
        if not (
            upper_sql.startswith("INSERT")
            or upper_sql.startswith("UPDATE")
            or upper_sql.startswith("DELETE")
        ):
            return False
        return any(table in upper_sql for table in self.TARGET_TABLES)
