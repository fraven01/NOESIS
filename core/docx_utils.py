from pathlib import Path
from docx import Document


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


def parse_anlage2_table(path: Path) -> dict[str, dict[str, bool | None]]:
    """Liest eine Anlage-2-Tabelle aus einer DOCX-Datei.

    Die Spalte "KI-Beteiligung" ist optional und wird nur ausgewertet,
    wenn sie vorhanden ist.
    """
    try:
        doc = Document(str(path))
    except Exception:  # pragma: no cover - ungültige Datei
        return {}

    results: dict[str, dict[str, bool | None]] = {}

    aliases = {
        "steht technisch zur verfügung?": "technisch vorhanden",
        "steht technisch zur verfuegung?": "technisch vorhanden",
        "einsatz bei telefonica": "einsatz bei telefónica",
        "einsatz bei telefonica?": "einsatz bei telefónica",
        "zur lv kontrolle": "zur lv-kontrolle",
        "zur lv kontrolle?": "zur lv-kontrolle",
        "ki-beteiligung?": "ki-beteiligung",
    }

    for table in doc.tables:
        raw_headers = [cell.text.replace("\n", " ").replace("\r", " ") for cell in table.rows[0].cells]
        headers = [" ".join(h.split()).lower() for h in raw_headers]
        normalized = [aliases.get(h, h) for h in headers]
        try:
            idx_func = normalized.index("funktion")
            idx_tech = normalized.index("technisch vorhanden")
            idx_tel = normalized.index("einsatz bei telefónica")
            idx_lv = normalized.index("zur lv-kontrolle")
        except ValueError:
            continue
        idx_ki = normalized.index("ki-beteiligung") if "ki-beteiligung" in normalized else None

        for row in table.rows[1:]:
            func = row.cells[idx_func].text.strip()
            if not func:
                continue

            data = {
                "technisch_verfuegbar": _parse_bool(row.cells[idx_tech].text),
                "einsatz_telefonica": _parse_bool(row.cells[idx_tel].text),
                "zur_lv_kontrolle": _parse_bool(row.cells[idx_lv].text),
            }
            if idx_ki is not None:
                data["ki_beteiligung"] = _parse_bool(row.cells[idx_ki].text)
            results[func] = data

        if results:
            break

    return results
