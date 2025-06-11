from pathlib import Path
from docx import Document

from .models import Anlage2Config


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

    cfg = Anlage2Config.objects.first()

    col_tech = cfg.col_technisch_vorhanden if cfg else "Technisch vorhanden"
    col_tel = cfg.col_einsatz_bei_telefonica if cfg else "Einsatz bei Telefónica"
    col_lv = cfg.col_zur_lv_kontrolle if cfg else "Zur LV-Kontrolle"
    col_ki = cfg.col_ki_beteiligung if cfg else "KI-Beteiligung"

    def norm(text: str) -> str:
        return " ".join(text.split()).lower()

    results: dict[str, dict[str, bool | None]] = {}

    tech_name = norm(col_tech)
    tel_name = norm(col_tel)
    lv_name = norm(col_lv)
    ki_name = norm(col_ki)

    aliases: dict[str, str] = {}
    tech_aliases = [
        col_tech,
        "Technisch vorhanden",
        "Steht technisch zur Verfügung?",
        "Steht technisch zur Verfuegung?",
    ]
    tel_aliases = [
        col_tel,
        "Einsatz bei Telefónica",
        "Einsatz bei Telefonica",
        "Einsatz bei Telefonica?",
    ]
    lv_aliases = [
        col_lv,
        "Zur LV-Kontrolle",
        "Zur LV Kontrolle",
        "Zur LV Kontrolle?",
    ]
    ki_aliases = [
        col_ki,
        "KI-Beteiligung",
        "KI-Beteiligung?",
    ]

    for a in tech_aliases:
        aliases[norm(a)] = tech_name
    for a in tel_aliases:
        aliases[norm(a)] = tel_name
    for a in lv_aliases:
        aliases[norm(a)] = lv_name
    for a in ki_aliases:
        aliases[norm(a)] = ki_name

    for table in doc.tables:
        raw_headers = [cell.text.replace("\n", " ").replace("\r", " ") for cell in table.rows[0].cells]
        headers = [norm(h) for h in raw_headers]
        normalized = [aliases.get(h, h) for h in headers]
        try:
            idx_func = normalized.index("funktion")
            idx_tech = normalized.index(tech_name)
            idx_tel = normalized.index(tel_name)
            idx_lv = normalized.index(lv_name)
        except ValueError:
            continue
        idx_ki = normalized.index(ki_name) if ki_name in normalized else None

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
