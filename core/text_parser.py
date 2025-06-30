
import re
from typing import List, Dict, Any


def parse_format_b(text: str) -> List[Dict[str, Any]]:
    """Parst ein einfaches Listenformat fuer Anlage 2.

    Jede Zeile enthaelt den Funktionsnamen gefolgt von optionalen
    Informationen zu technischen Flags. Zeilen koennen durch
    Semikolons oder Bindestriche getrennt sein.
    Beispiel::

        "Login; tv: ja; tel: nein; lv: nein; ki: ja"
    """

    mapping = {
        "tv": "technisch_verfuegbar",
        "tel": "einsatz_telefonica",
        "lv": "zur_lv_kontrolle",
        "ki": "ki_beteiligung",
    }
    results = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Entferne Nummerierung wie "1." oder "a)"
        line = re.sub(r"^[\d]+[.)]\s*", "", line)
        parts = re.split(r"[;|-]", line)
        if not parts:
            continue
        entry = {"funktion": parts[0].strip()}
        for part in parts[1:]:
            part = part.strip()
            m = re.match(r"(tv|tel|lv|ki)\s*[:=]\s*(ja|nein)", part, re.I)
            if not m:
                continue
            key, val = m.groups()
            entry[mapping[key.lower()]] = {"value": val.lower() == "ja", "note": None}
        results.append(entry)

    return results
