
from __future__ import annotations

import logging
import re
from typing import List

from .models import BVProjectFile
from .parser_manager import AbstractParser

logger = logging.getLogger(__name__)


class TextParser(AbstractParser):
    """Parser für textbasierte Dokumente im Format B."""

    name = "text"

    def parse(self, project_file: BVProjectFile) -> List[dict[str, object]]:
        """Parst den Textinhalt einer Projektdatei."""
        text = project_file.text_content or ""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        results: List[dict[str, object]] = []
        func_re = re.compile(r"^(.+?):\s*(.*)")
        i = 0
        while i < len(lines):
            m = func_re.match(lines[i])
            if not m:
                i += 1
                continue
            name = m.group(1).strip()
            sentence = m.group(2).strip()
            technisch = _map_technisch(sentence)
            verwenden = _map_verwendung(sentence, technisch)
            lv = _map_lv(sentence)
            i += 1
            details: List[dict[str, object]] = []
            while i < len(lines) and not func_re.match(lines[i]):
                detail_match = re.match(r"(.+?)[:?]\s*(.*)", lines[i])
                if detail_match:
                    frage = detail_match.group(1).strip()
                    antwort = detail_match.group(2).strip()
                    antwort_verw = "Ja" if re.search(r"\bja\b", antwort, re.I) else "Nein"
                    details.append(
                        {
                            "frage": frage,
                            "antwort_text": antwort,
                            "antwort_verwendung": antwort_verw,
                        }
                    )
                i += 1
            results.append(
                {
                    "funktion": name,
                    "technisch_verfuegbar": technisch,
                    "soll_verwendet_werden": verwenden,
                    "ueberwachung_leistung_verhalten": lv,
                    "details": details,
                }
            )
        return results


def _map_technisch(sentence: str) -> str:
    lower = sentence.lower()
    if "stehen technisch zur ver\u00fcgung" in lower:
        return "Ja"
    if "stehen technisch nicht zur ver\u00fcgung" in lower:
        return "Nein"
    if re.search(r"\bja\b", sentence, re.I):
        return "Ja"
    if re.search(r"\bnein\b", sentence, re.I):
        return "Nein"
    return "Unbekannt"


def _map_verwendung(sentence: str, technisch: str) -> str:
    lower = sentence.lower()
    if technisch == "Nein":
        return "Nein"
    if "und sollen verwendet werden" in lower:
        return "Ja"
    if "sollen nicht verwendet" in lower or "soll aber nicht verwendet" in lower:
        return "Nein"
    return "Unbekannt"


def _map_lv(sentence: str) -> str:
    lower = sentence.lower()
    if "\u00fcberwachung von leistung oder verhalten" in lower:
        if "nicht verwendet" in lower:
            return "Nein"
        if "verwendet" in lower:
            return "Ja"
    return "Unbekannt"


