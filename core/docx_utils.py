from pathlib import Path
from docx import Document


def extract_text(path: Path) -> str:
    """Extrahiert den gesamten Text einer DOCX-Datei."""
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def parse_anlage2_table(path: Path) -> list[dict]:
    """Liest eine Anlage-2-Tabelle aus einer DOCX-Datei."""
    try:
        doc = Document(str(path))
    except Exception:  # pragma: no cover - ungültige Datei
        return []

    results: list[dict] = []
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

            def yes(index: int) -> bool:
                return row.cells[index].text.strip().lower().startswith("ja")

            results.append(
                {
                    "funktion": func,
                    "technisch_vorhanden": yes(idx_tech),
                    "einsatz_bei_telefonica": yes(idx_tel),
                    "zur_lv_kontrolle": yes(idx_lv),
                    "ki_beteiligung": yes(idx_ki),
                }
            )

        if results:
            break

    return results
