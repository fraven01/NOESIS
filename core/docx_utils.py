from pathlib import Path
from docx import Document
import logging
import re

from .models import Anlage2Config, Anlage2ColumnHeading

# Zuordnung der Standardspalten zu ihren Feldnamen
HEADER_FIELDS = {
    "technisch vorhanden": "technisch_vorhanden",  # <-- Der kanonische TEXT-Schlüssel, der gesucht wird
    "einsatz bei telefónica": "einsatz_bei_telefonica",
    "zur lv-kontrolle": "zur_lv_kontrolle",
    "ki-beteiligung": "ki_beteiligung",
}

# Aliasüberschriften werden ausschließlich über das Modell
# ``Anlage2ColumnHeading`` gepflegt


def extract_text(path: Path) -> str:
    """Extrahiert den gesamten Text einer DOCX-Datei."""
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def _parse_bool(text: str) -> bool | None:
    """Interpretiert 'Ja' oder 'Nein'."""
    text = text.strip().lower()
    if text.startswith("ja"):
        return True
    if text.startswith("nein"):
        return False
    return None


def _normalize_header_text(text: str) -> str:
    """Bereinigt eine Tabellenüberschrift für den Vergleich."""
    text = text.replace("\n", " ")
    text = re.sub(r"ja\s*/\s*nein", "", text, flags=re.I)
    text = text.strip().lower()
    # Fragezeichen und Doppelpunkte am Ende entfernen
    text = re.sub(r"[?:]+$", "", text).strip()
    # Mehrere Leerzeichen und Tabulatoren vereinheitlichen
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _build_header_map(cfg: Anlage2Config | None) -> dict[str, str]:
    """Erzeugt ein Mapping aller bekannten Header auf ihre kanonische Form.

    Aliasüberschriften werden ausschließlich aus ``Anlage2ColumnHeading``
    geladen.
    """

    logger = logging.getLogger(__name__)

    mapping: dict[str, str] = {"funktion": "funktion"}

    def _add_mapping(key: str, canonical: str) -> None:
        """Fügt einen Mapping-Eintrag hinzu und prüft auf Konflikte."""
        if key in mapping and mapping[key] != canonical:
            msg = (
                f"Mehrdeutige Überschrift '{key}' "
                f"für '{mapping[key]}' und '{canonical}'"
            )
            logger.warning(msg)
            raise ValueError(msg)
        mapping[key] = canonical

    if cfg:
        logger.debug(
            "Konfiguriere Alias-Überschriften: %s",
            [str(h) for h in cfg.headers.all()],
        )
    else:
        logger.debug("Keine Anlage2Config gefunden")

    for canonical, field in HEADER_FIELDS.items():
        _add_mapping(_normalize_header_text(canonical), canonical)
        if cfg:
            for h in cfg.headers.filter(field_name=field):
                _add_mapping(_normalize_header_text(h.text), canonical)

    logger.debug(
        "Alias-Überschriften: %s",
        [str(h) for h in cfg.headers.all()] if cfg else [],
    )

    return mapping


def parse_anlage2_table(path: Path) -> dict[str, dict[str, bool | None]]:
    """Liest und parst eine Anlage-2-Tabelle aus einer DOCX-Datei und gibt die extrahierten Daten als verschachteltes Dictionary zurück.
    Die Funktion sucht in der angegebenen DOCX-Datei nach einer Tabelle mit den erwarteten Spaltenüberschriften:
    - "Funktion"
    - "Technisch vorhanden"
    - "Einsatz bei Telefónica"
    - "Zur LV-Kontrolle"
    Die Spalte "KI-Beteiligung" ist optional und wird nur ausgewertet, wenn sie vorhanden ist. Eigene Überschriften können über Aliasdefinitionen in der Datenbank hinterlegt werden.
    Jede Zeile der Tabelle wird als Eintrag im Ergebnis-Dictionary gespeichert, wobei der Wert der Spalte "Funktion" als Schlüssel dient.
    Die zugehörigen Werte sind Dictionaries mit den folgenden Schlüsseln:
    - "technisch_verfuegbar": bool oder None – Gibt an, ob die Funktion technisch verfügbar ist.
    - "einsatz_telefonica": bool oder None – Gibt an, ob die Funktion bei Telefónica im Einsatz ist.
    - "zur_lv_kontrolle": bool oder None – Gibt an, ob die Funktion zur LV-Kontrolle verwendet wird.
    - "ki_beteiligung": bool oder None – Gibt an, ob KI-Beteiligung vorliegt (nur, wenn die Spalte vorhanden ist).
    Die Werte werden aus den jeweiligen Zellen der Tabelle extrahiert und mit einer Hilfsfunktion in boolesche Werte oder None umgewandelt.
    Parameter:
        path (Path): Pfad zur DOCX-Datei, die die Anlage-2-Tabelle enthält.
    Rückgabewert:
        dict[str, dict[str, bool | None]]:
            Ein Dictionary, das für jede Funktion ein weiteres Dictionary mit den ausgelesenen Werten enthält.
            Ist die Datei ungültig oder enthält keine passende Tabelle, wird ein leeres Dictionary zurückgegeben.
    Hinweise:
        - Die Funktion verarbeitet nur die erste gefundene Tabelle mit den erwarteten Spaltenüberschriften.
        - Leere Funktionsnamen werden übersprungen.
        - Fehler beim Laden der Datei werden protokolliert und führen zur Rückgabe eines leeren Dictionaries.
    Liest eine Anlage-2-Tabelle aus einer DOCX-Datei.

    Die Spalte "KI-Beteiligung" ist optional und wird nur ausgewertet,
    wenn sie vorhanden ist.
    """
    logger = logging.getLogger(__name__)

    logger.debug(f"Starte parse_anlage2_table mit Pfad: {path}")

    try:
        doc = Document(str(path))
        logger.debug(f"Dokument erfolgreich geladen: {path}")
    except Exception as e:  # pragma: no cover - ungültige Datei
        logger.error(f"Fehler beim Laden der Datei {path}: {e}")
        return {}

    cfg = Anlage2Config.get_instance()
    logger.debug("Aktive Anlage2Config: %s", cfg)
    header_map = _build_header_map(cfg)
    logger.debug("Erzeugtes Header-Mapping: %s", header_map)

    results: dict[str, dict[str, bool | None]] = {}
    for table_idx, table in enumerate(doc.tables):
        headers_raw = [cell.text for cell in table.rows[0].cells]
        headers = [
            header_map.get(_normalize_header_text(h), _normalize_header_text(h))
            for h in headers_raw
        ]
        logger.debug(
            f"Tabelle {table_idx}: Roh-Header = {headers_raw}, Normiert = {headers}"
        )
        try:
            idx_func = headers.index("funktion")
            idx_tech = headers.index("technisch vorhanden")
            idx_tel = headers.index("einsatz bei telefónica")
            idx_lv = headers.index("zur lv-kontrolle")
        except ValueError as ve:
            logger.debug(f"Tabelle {table_idx}: Erwartete Spalten nicht gefunden: {ve}")
            continue
        idx_ki = (
            headers.index("ki-beteiligung") if "ki-beteiligung" in headers else None
        )

        for row_idx, row in enumerate(table.rows[1:], start=1):
            func = row.cells[idx_func].text.strip()
            logger.debug(f"Tabelle {table_idx}, Zeile {row_idx}: Funktion = '{func}'")
            if not func:
                logger.debug(
                    f"Tabelle {table_idx}, Zeile {row_idx}: Leere Funktion, überspringe Zeile."
                )
                continue

            data = {
                "technisch_verfuegbar": _parse_bool(row.cells[idx_tech].text),
                "einsatz_telefonica": _parse_bool(row.cells[idx_tel].text),
                "zur_lv_kontrolle": _parse_bool(row.cells[idx_lv].text),
            }
            if idx_ki is not None:
                data["ki_beteiligung"] = _parse_bool(row.cells[idx_ki].text)
            logger.debug(
                f"Tabelle {table_idx}, Zeile {row_idx}: Funktion = {func}, Daten = {data}"
            )
            results[func] = data

        if results:
            logger.debug(f"Tabelle {table_idx}: Ergebnisse gefunden, beende Suche.")
            break

    logger.debug(f"Endgültige Ergebnisse: {results}")
    return results
