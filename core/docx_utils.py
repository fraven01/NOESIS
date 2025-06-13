from pathlib import Path
from docx import Document
import logging
import re

from .models import (
    Anlage2Config,
    Anlage2ColumnHeading,
    Anlage2Function,
    Anlage2SubQuestion,
)

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


def _parse_cell_value(text: str) -> dict[str, object]:
    """Parst eine Tabellenzelle mit optionaler Zusatzinfo.

    Gibt ein Dictionary mit ``value`` (bool oder ``None``) und ``note``
    (optionaler Zusatztext) zurück.
    """
    note: str | None = None
    clean = text
    m = re.search(r"\(([^)]*)\)", text)
    if m:
        note = m.group(1).strip() or None
        clean = text[: m.start()] + text[m.end() :]
    value = _parse_bool(clean)
    return {"value": value, "note": note}


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


def parse_anlage2_table(path: Path) -> list[dict[str, object]]:
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

    Die Rückgabe ist eine Liste von Dictionaries mit dem Schlüssel
    ``funktion`` sowie den in ``HEADER_FIELDS`` definierten Spalten. Jede
    Spalte enthält wiederum ein Dictionary mit den Schlüsseln ``value`` und
    ``note``.
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

    results: list[dict[str, object]] = []
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

        col_indices = {
            "technisch_verfuegbar": idx_tech,
            "einsatz_telefonica": idx_tel,
            "zur_lv_kontrolle": idx_lv,
        }
        if idx_ki is not None:
            col_indices["ki_beteiligung"] = idx_ki

        current_main_function_name = None

        for row_idx, row in enumerate(table.rows[1:], start=1):
            main_col_text = row.cells[idx_func].text.strip()
            sub_col_text = (
                row.cells[idx_func + 1].text.strip()
                if len(row.cells) > idx_func + 1
                else ""
            )

            logger.debug(
                "Tabelle %s, Zeile %s: main='%s', sub='%s'",
                table_idx,
                row_idx,
                main_col_text,
                sub_col_text,
            )

            row_data: dict[str, object] | None = None

            if main_col_text and "Wenn die Funktion technisch" not in main_col_text:
                current_main_function_name = main_col_text
                row_data = {"funktion": current_main_function_name}
            elif sub_col_text and current_main_function_name:
                full_name = f"{current_main_function_name}: {sub_col_text}"
                row_data = {"funktion": full_name}

            if row_data is None:
                logger.debug(
                    "Zeile %s: Keine verarbeitbare Funktion gefunden, übersprungen",
                    row_idx,
                )
                continue

            for col_name, idx in col_indices.items():
                if idx is not None:
                    row_data[col_name] = _parse_cell_value(row.cells[idx].text)

            logger.debug(
                "Zeile %s: Funktion '%s' Daten %s",
                row_idx,
                row_data["funktion"],
                {k: row_data[k] for k in col_indices},
            )

            results.append(row_data)

        if results:
            logger.debug(f"Tabelle {table_idx}: Ergebnisse gefunden, beende Suche.")
            break

    logger.debug(f"Endgültige Ergebnisse: {results}")
    return results


def parse_anlage2_text(text_content: str) -> list[dict[str, object]]:
    """Parst den Text einer Anlage 2 mittels Datenbankregeln.

    Die Funktion durchsucht den übergebenen Text zeilenweise nach
    Funktionsnamen und Unterfragen. Welche Phrasen dabei jeweils eine
    Übereinstimmung darstellen, wird über die ``detection_phrases`` der
    Funktionen bzw. Unterfragen bestimmt. Die Phrasen zur Ermittlung der
    Feldwerte liegen hingegen zentral im Modell ``Anlage2GlobalPhrase``.
    """

    logger = logging.getLogger(__name__)
    if not text_content:
        return []

    all_functions = list(Anlage2Function.objects.all())
    all_subs = list(Anlage2SubQuestion.objects.select_related("funktion"))

    def _get_list(data: dict, key: str) -> list[str]:
        val = data.get(key, [])
        if isinstance(val, str):
            return [val]
        return [str(v) for v in val]

    def _match(phrases: list[str], line: str) -> bool:
        return any(p.lower() in line for p in phrases if p)

    cfg = Anlage2Config.get_instance()
    gp_dict: dict[str, list[str]] = {}
    for gp in cfg.global_phrases.all():
        gp_dict.setdefault(gp.phrase_type, []).append(gp.phrase_text.lower())

    def _extract_values(line: str) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for field in [
            "technisch_verfuegbar",
            "einsatz_telefonica",
            "zur_lv_kontrolle",
            "ki_beteiligung",
        ]:
            val = None
            if _match(gp_dict.get(f"{field}_true", []), line):
                val = True
            elif _match(gp_dict.get(f"{field}_false", []), line):
                val = False
            if val is not None:
                result[field] = {"value": val, "note": None}
        return result

    lines = [l.strip() for l in text_content.replace("\u00b6", "\n").splitlines()]
    results: list[dict[str, object]] = []
    last_main: dict[str, object] | None = None

    for line in lines:
        lower = line.lower()
        if not lower:
            continue

        found = False
        for sub in all_subs:
            if last_main is None:
                break
            aliases = _get_list(sub.detection_phrases, "name_aliases")
            if _match(aliases, lower):
                full_name = f"{last_main['funktion']}: {sub.frage_text}"
                row = {"funktion": full_name}
                row.update(_extract_values(lower))
                results.append(row)
                found = True
                break
        if found:
            continue

        for func in all_functions:
            aliases = _get_list(func.detection_phrases, "name_aliases")
            if _match(aliases, lower):
                row = {"funktion": func.name}
                row.update(_extract_values(lower))
                results.append(row)
                last_main = row
                found = True
                break

    logger.debug("parse_anlage2_text Ergebnisse: %s", results)
    return results
