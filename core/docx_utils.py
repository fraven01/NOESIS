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
    # Zuerst doppelt-escapte Newlines durch ein einfaches Leerzeichen ersetzen
    # Wichtig: Dies muss passieren, bevor "echte" Newlines ersetzt werden,
    # falls beides vorkommt, oder wenn die Quelle schon so escapet.
    text = text.replace("\\n", " ")  # <-- NEUE ZEILE / ÄNDERUNG HIER!
    # Ersetzt '\\n' durch ein Leerzeichen

    text = text.replace(
        "\n", " "
    )  # Behält die alte Zeile für den Fall von "echten" Newlines
    text = re.sub(r"ja\s*/\s*nein", "", text, flags=re.I)
    text = text.strip().lower()
    # Fragezeichen und Doppelpunkte am Ende entfernen
    text = re.sub(r"[?:]+$", "", text).strip()
    # Mehrere Leerzeichen und Tabulatoren vereinheitlichen
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _normalize_function_name(name: str) -> str:
    """Bereinigt Funktionsnamen für Vergleiche."""
    text = name.replace("\n", " ").strip().lower()
    return re.sub(r"[ \t]+", " ", text)


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
                logger.debug(f"Roh-Alias (repr): {repr(h.text)}")
                logger.debug(
                    f"Normalisierter Alias: '{_normalize_header_text(h.text)}'"
                )
                _add_mapping(_normalize_header_text(h.text), canonical)

    logger.debug(
        "Alias-Überschriften: %s",
        [str(h) for h in cfg.headers.all()] if cfg else [],
    )

    return mapping


def parse_anlage2_table(path: Path) -> list[dict[str, bool | None]]:
    """Liest und parst eine Anlage‑2‑Tabelle aus einer DOCX-Datei.

    Die Funktion versucht, sowohl einfache Tabellen als auch die in Anlage 2
    vorkommende hierarchische Struktur zu interpretieren. Dabei werden zwei
    Zeilentypen unterschieden:

    - **Hauptfunktions-Zeilen** enthalten einen Funktionsnamen in der ersten
      Spalte, die zweite Funktionsspalte ist leer.
    - **Unterfragen-Zeilen** besitzen einen Text in der zweiten
      Funktionsspalte. Der Text der ersten Spalte wird ignoriert, da er in der
      Regel einen generischen Hinweis enthält. Der vollständige Funktionsname
      ergibt sich aus dem zuletzt gefundenen Hauptfunktionsnamen gefolgt von
      einem Doppelpunkt und dem Unterfragentext.

    Die Rückgabe ist eine Liste von Dictionaries mit den Schlüsseln
    ``funktion`` sowie den in ``HEADER_FIELDS`` definierten Spalten.
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

    results: list[dict[str, bool | None]] = []
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
            func_indices = [i for i, h in enumerate(headers) if h == "funktion"]
            if not func_indices:
                raise ValueError("funktion")
            idx_func = func_indices[0]
            idx_tech = headers.index("technisch vorhanden")
            idx_tel = headers.index("einsatz bei telefónica")
            idx_lv = headers.index("zur lv-kontrolle")
        except ValueError as ve:
            logger.debug(f"Tabelle {table_idx}: Erwartete Spalten nicht gefunden: {ve}")
            continue
        idx_ki = (
            headers.index("ki-beteiligung") if "ki-beteiligung" in headers else None
        )

        second_idx = func_indices[1] if len(func_indices) > 1 else None
        current_main = None
        for row_idx, row in enumerate(table.rows[1:], start=1):
            first_text = row.cells[idx_func].text.strip()
            second_text = row.cells[second_idx].text.strip() if second_idx is not None else ""
            logger.debug(
                "Tabelle %s, Zeile %s: first='%s', second='%s'",
                table_idx,
                row_idx,
                first_text,
                second_text,
            )

            if second_text:
                if current_main:
                    func_name = f"{current_main}: {second_text}"
                else:
                    logger.debug(
                        "Zeile %s: Unterfrage ohne Kontext, übersprungen", row_idx
                    )
                    continue
            else:
                if not first_text:
                    logger.debug(
                        "Zeile %s: Leere Funktionsspalte, übersprungen", row_idx
                    )
                    continue
                current_main = first_text
                func_name = current_main

            data = {
                "technisch_verfuegbar": _parse_bool(row.cells[idx_tech].text),
                "einsatz_telefonica": _parse_bool(row.cells[idx_tel].text),
                "zur_lv_kontrolle": _parse_bool(row.cells[idx_lv].text),
            }
            if idx_ki is not None:
                data["ki_beteiligung"] = _parse_bool(row.cells[idx_ki].text)

            logger.debug(
                "Zeile %s: Funktion '%s' Daten %s",
                row_idx,
                func_name,
                data,
            )

            results.append({"funktion": func_name, **data})

        if results:
            logger.debug(f"Tabelle {table_idx}: Ergebnisse gefunden, beende Suche.")
            break

    logger.debug(f"Endgültige Ergebnisse: {results}")
    return results
