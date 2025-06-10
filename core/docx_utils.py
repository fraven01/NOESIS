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
    """Liest eine Anlage-2-Tabelle aus einer DOCX-Datei."""
    try:
        doc = Document(str(path))
    except Exception:  # pragma: no cover - ungültige Datei
        return {}

    results: dict[str, dict[str, bool | None]] = {}
    for table in doc.tables:
        headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
        try:
            idx_func = headers.index("funktion")
            idx_tech = headers.index("technisch vorhanden")
            idx_tel = headers.index("einsatz bei telefónica")
            idx_lv = headers.index("zur lv-kontrolle")
            idx_ki = headers.index("ki-beteiligung")
        except ValueError:
            continue

        for row in table.rows[1:]:
            func = row.cells[idx_func].text.strip()
            if not func:
                continue

            results[func] = {
                "technisch_verfuegbar": _parse_bool(row.cells[idx_tech].text),
                "einsatz_telefonica": _parse_bool(row.cells[idx_tel].text),
                "zur_lv_kontrolle": _parse_bool(row.cells[idx_lv].text),
                "ki_beteiligung": _parse_bool(row.cells[idx_ki].text),
            }

        if results:
            break

    return results
