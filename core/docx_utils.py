from pathlib import Path
from docx import Document
import logging
import re
import string
import zipfile

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
    text = "\n".join(p.text for p in doc.paragraphs)
    parser_logger = logging.getLogger("parser_debug")
    parser_logger.debug("Rohtext aus %s: %r", path, text)
    return text


def get_docx_page_count(path: Path) -> int:
    """Ermittelt die Seitenzahl eines DOCX-Dokuments.

    Es werden sowohl manuelle Seitenumbrüche (``<w:br w:type="page"/>``)
    als auch Abschnittswechsel gezählt, sofern sie einen neuen
    Seitenumbruch bewirken. Ein einfaches Dokument besitzt somit immer
    mindestens eine Seite.
    """

    doc = Document(str(path))
    root = doc.part.element

    # Zähle explizite Seitenumbrüche
    page_breaks = len(root.xpath('.//w:br[@w:type="page"]'))

    # Abschnittswechsel können ebenfalls neue Seiten erzeugen. Das
    # abschließende ``sectPr`` beschreibt lediglich das letzte
    # Abschnittslayout und zählt daher nicht als Umbruch.
    section_breaks = 0
    sect_prs = root.xpath('.//w:sectPr')
    for sp in sect_prs[1:]:
        type_el = sp.xpath('./w:type')
        val = (
            type_el[0].get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val')
            if type_el
            else None
        )
        if val != 'continuous':
            section_breaks += 1

    return 1 + page_breaks + section_breaks


def extract_docx_images(path: Path) -> list[bytes]:
    """Extrahiert Bilder aus einer DOCX-Datei."""

    logger = logging.getLogger(__name__)
    images: list[bytes] = []
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.startswith("word/media/"):
                    with zf.open(name) as fh:
                        images.append(fh.read())
    except Exception as exc:  # pragma: no cover - ungültige Datei
        logger.error("Fehler beim Extrahieren der Bilder aus %s: %s", path, exc)
    return images


def extract_pdf_images(path: Path) -> list[bytes]:
    """Extrahiert Bilder aus einer PDF-Datei."""

    logger = logging.getLogger(__name__)
    images: list[bytes] = []
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                data = doc.extract_image(xref)
                if data and "image" in data:
                    images.append(data["image"])
    except Exception as exc:  # pragma: no cover - ungültige Datei
        logger.error("Fehler beim Extrahieren der Bilder aus %s: %s", path, exc)
    return images


def extract_images(path: Path) -> list[bytes]:
    """Extrahiert Bilder aus DOCX- oder PDF-Dateien."""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_images(path)
    return extract_docx_images(path)


def _parse_cell_value(text: str) -> dict[str, object]:
    """Parst eine Tabellenzelle mit optionaler Zusatzinfo.

    Gibt ein Dictionary mit ``value`` (bool oder ``None``) und ``note``
    (optionaler Zusatztext) zurück.
    """
    text = text.strip()
    match = re.match(r"^(ja|nein)\b(.*)$", text, flags=re.IGNORECASE)
    if match:
        value = match.group(1).lower() == "ja"
        rest = match.group(2).strip()
        rest = re.sub(r"^[,:;\-\s]+", "", rest)
        if rest.startswith("(") and rest.endswith(")"):
            rest = rest[1:-1].strip()
        note = rest or None
        return {"value": value, "note": note}

    note: str | None = None
    m = re.search(r"\(([^)]*)\)", text)
    if m:
        note = m.group(1).strip() or None
        text = (text[: m.start()] + text[m.end() :]).strip()

    lower = text.lower()
    if lower.startswith("ja"):
        value = True
    elif lower.startswith("nein"):
        value = False
    else:
        value = None
    return {"value": value, "note": note}


def _normalize_header_text(text: str) -> str:
    """Bereinigt eine Tabellenüberschrift für den Vergleich."""
    # Zuerst doppelt-escapte Newlines durch ein einfaches Leerzeichen ersetzen
    # Wichtig: Dies muss passieren, bevor "echte" Newlines ersetzt werden,
    # falls beides vorkommt, oder wenn die Quelle schon so escapet.
    text = text.replace("\\n", " ")
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


def _normalize_snippet(text: str) -> str:
    """Normalisiert Textschnipsel für Alias-Vergleiche."""
    text = (
        text.replace("\n", " ")
        .replace("\t", " ")
        .replace("\u00b6", " ")
        .replace("\xa0", " ")
    )
    text = text.lower()
    text = re.sub(r"[\-_/]+", " ", text)
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


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
    parser_logger = logging.getLogger("parser_debug")
    logger.debug(f"Starte parse_anlage2_table mit Pfad: {path}")
    parser_logger.info("parse_anlage2_table gestartet: %s", path)

    try:
        doc = Document(str(path))
        logger.debug(f"Dokument erfolgreich geladen: {path}")
    except Exception as e:  # pragma: no cover - ungültige Datei
        logger.error(f"Fehler beim Laden der Datei {path}: {e}")
        return []

    cfg = Anlage2Config.get_instance()
    logger.debug("Aktive Anlage2Config: %s", cfg)
    header_map = _build_header_map(cfg)
    logger.debug("Erzeugtes Header-Mapping: %s", header_map)

    results: list[dict[str, object]] = []
    if not doc.tables:
        logger.debug("Keine Tabellen im Dokument gefunden")
        parser_logger.debug("Keine Tabellen im Dokument gefunden")
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
                parser_logger.debug("Hauptfunktion erkannt: %s", current_main_function_name)
                row_data = {"funktion": current_main_function_name}
            elif sub_col_text and current_main_function_name:
                full_name = f"{current_main_function_name}: {sub_col_text}"
                parser_logger.debug("Unterfrage erkannt: %s", full_name)
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

            parser_logger.debug("Verarbeite Zeile %s: %s", row_idx, row_data)
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
    parser_logger.info("parse_anlage2_table beendet: %s", path)
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
    parser_logger = logging.getLogger("parser_debug")
    parser_logger.info("parse_anlage2_text gestartet")
    if not text_content:
        return []

    def _get_list(data: dict, key: str) -> list[str]:
        val = data.get(key, [])
        if isinstance(val, str):
            return [val]
        return [str(v) for v in val]

    # Alle Funktionen mit ihren Aliases vorbereiten
    functions: list[tuple[Anlage2Function, list[str]]] = []
    for func in Anlage2Function.objects.all():
        alias_list = [func.name]
        alias_list += _get_list(func.detection_phrases, "name_aliases")
        aliases = list(dict.fromkeys(_normalize_snippet(a) for a in alias_list))
        parser_logger.debug("Funktion '%s' Aliase: %s", func.name, aliases)
        functions.append((func, aliases))

    # Unterfragen pro Funktion sammeln
    sub_map: dict[int, list[tuple[Anlage2SubQuestion, list[str]]]] = {}
    for sub in Anlage2SubQuestion.objects.select_related("funktion"):
        alias_list = [sub.frage_text]
        alias_list += _get_list(sub.detection_phrases, "name_aliases")
        aliases = list(dict.fromkeys(_normalize_snippet(a) for a in alias_list))
        parser_logger.debug(
            "Unterfrage '%s' (%s) Aliase: %s",
            sub.frage_text,
            sub.funktion.name,
            aliases,
        )
        sub_map.setdefault(sub.funktion_id, []).append((sub, aliases))

    def _match(
        phrases: list[str],
        line: str,
        origin: str | None = None,
        raw_line: str | None = None,
    ) -> bool:
        valid_phrases = [p for p in phrases if p]
        if not valid_phrases:
            parser_logger.debug(
                "Keine gültigen Aliase zum Prüfen für '%s' vorhanden. Überspringe.",
                origin or "Unbekannt",
            )
            return False

        for ph in valid_phrases:
            if origin:
                if raw_line is not None:
                    parser_logger.debug(
                        "Prüfe Alias '%s' aus '%s' gegen Zeile '%s' (Rohtext: '%s')",
                        ph,
                        origin,
                        line,
                        raw_line,
                    )
                else:
                    parser_logger.debug(
                        "Prüfe Alias '%s' aus '%s' gegen Zeile '%s'",
                        ph,
                        origin,
                        line,
                    )
            else:
                if raw_line is not None:
                    parser_logger.debug(
                        "Prüfe Alias '%s' gegen Zeile '%s' (Rohtext: '%s')",
                        ph,
                        line,
                        raw_line,
                    )
                else:
                    parser_logger.debug(
                        "Prüfe Alias '%s' gegen Zeile '%s'",
                        ph,
                        line,
                    )
            parser_logger.debug(
                "Finaler Vergleich: %r (%s) in %r (%s)",
                ph,
                type(ph).__name__,
                line,
                type(line).__name__,
            )
            if ph in line:
                parser_logger.debug("-> Treffer")
                return True
        return False

    cfg = Anlage2Config.get_instance()
    gp_dict: dict[str, list[str]] = {}
    for gp in cfg.global_phrases.all():
        parser_logger.debug(
            "Globale Phrase '%s': %s",
            gp.phrase_type,
            gp.phrase_text,
        )
        norm = _normalize_snippet(gp.phrase_text)
        gp_dict.setdefault(gp.phrase_type, []).append(norm)
    parser_logger.debug("Gesammelte globale Phrasen: %s", gp_dict)

    def _extract_values(line: str, raw_line: str) -> dict[str, dict[str, object]]:
        """Extrahiert Werte aus einer bereits normalisierten Zeile."""
        result: dict[str, dict[str, object]] = {}
        for field in [
            "technisch_verfuegbar",
            "einsatz_telefonica",
            "zur_lv_kontrolle",
            "ki_beteiligung",
        ]:
            val = None
            if _match(
                gp_dict.get(f"{field}_true", []),
                line,
                origin=f"{field}_true",
                raw_line=raw_line,
            ):
                val = True
            elif _match(
                gp_dict.get(f"{field}_false", []),
                line,
                origin=f"{field}_false",
                raw_line=raw_line,
            ):
                val = False
            if val is not None:
                result[field] = {"value": val, "note": None}
                parser_logger.debug(
                    "Extrahierter Wert für %s: %s", field, val
                )
        return result

    lines = [l.strip() for l in text_content.replace("\u00b6", "\n").splitlines()]
    results: list[dict[str, object]] = []
    last_main: dict[str, object] | None = None
    last_func: Anlage2Function | None = None

    for line in lines:
        parser_logger.debug("Prüfe Zeile: %s", line)
        norm_line = _normalize_snippet(line)
        if not norm_line:
            continue

        found = False

        # Prüfe zuerst auf Unterfragen der zuletzt gefundenen Funktion
        if last_func:
            for sub, aliases in sub_map.get(last_func.id, []):
                if _match(
                    aliases,
                    norm_line,
                    origin=f"Unterfrage {sub.frage_text}",
                    raw_line=line,
                ):
                    full_name = f"{last_main['funktion']}: {sub.frage_text}"
                    parser_logger.debug("Unterfrage erkannt: %s", full_name)
                    row = {"funktion": full_name}
                    row.update(_extract_values(norm_line, line))
                    results.append(row)
                    found = True
                    break
        if found:
            continue

        # Suche nach einer neuen Hauptfunktion
        for func, aliases in functions:
            if _match(
                aliases,
                norm_line,
                origin=f"Funktion {func.name}",
                raw_line=line,
            ):
                parser_logger.debug("Hauptfunktion erkannt: %s", func.name)
                row = {"funktion": func.name}
                row.update(_extract_values(norm_line, line))
                results.append(row)
                last_main = row
                last_func = func
                found = True
                break

        if not found:
            parser_logger.debug("Keine Funktion erkannt für Zeile: %s", line)

    logger.debug("parse_anlage2_text Ergebnisse: %s", results)
    parser_logger.info("parse_anlage2_text beendet")
    return results
