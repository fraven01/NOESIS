
from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

from .models import BVProjectFile, FormatBParserRule
from .models import Anlage2Config, Anlage2Function, Anlage2SubQuestion

from .parsers import AbstractParser

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
                    antwort_verw = (
                        "Ja" if re.search(r"\bja\b", antwort, re.I) else "Nein"
                    )
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
    """Ermittelt, ob eine Funktion technisch verfügbar ist."""
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
    """Bewertet die geplante Verwendung einer Funktion."""
    lower = sentence.lower()
    if technisch == "Nein":
        return "Nein"
    if "und sollen verwendet werden" in lower:
        return "Ja"
    if (
        "sollen nicht verwendet" in lower
        or "soll aber nicht verwendet" in lower
    ):
        return "Nein"
    return "Unbekannt"


def _map_lv(sentence: str) -> str:
    """Gibt an, ob die Funktion der Leistungs- oder
    Verhaltenskontrolle dient."""
    lower = sentence.lower()
    if "\u00fcberwachung von leistung oder verhalten" in lower:
        if "nicht verwendet" in lower:
            return "Nein"
        if "verwendet" in lower:
            return "Ja"
    return "Unbekannt"



def parse_format_b(text: str) -> List[dict[str, object]]:
    """Parst ein einfaches Listenformat von Anlage 2.

    Mehrere Zeilen können verarbeitet werden.
    Jede Zeile enthält einen Funktionsnamen und optionale Tokens
    wie ``tv``, ``tel``, ``lv`` und ``ki``.
    Eine vorausgehende Nummerierung wie ``1.`` wird ignoriert.
    """

    rules = FormatBParserRule.objects.all()
    if rules:
        mapping = {r.key.lower(): r.target_field for r in rules}
    else:
        mapping = {
            "tv": "technisch_verfuegbar",
            "tel": "einsatz_telefonica",
            "lv": "zur_lv_kontrolle",
            "ki": "ki_beteiligung",
        }

    results: List[dict[str, object]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[\d]+[.)]\s*", "", line)
        parts = re.split(r"[;\-]", line)
        if not parts:
            continue
        entry: dict[str, object] = {"funktion": parts[0].strip()}
        key_re = "|".join(map(re.escape, mapping.keys()))
        for part in parts[1:]:
            part = part.strip()
            m = re.match(rf"({key_re})\s*[:=]\s*(ja|nein)", part, re.I)
            if not m:
                continue
            key, val = m.groups()
            entry[mapping[key.lower()]] = {
                "value": val.lower() == "ja",
                "note": None,
            }
        results.append(entry)

    return results


def parse_anlage2_text(text: str) -> List[dict[str, object]]:
    """Parst eine Freitext-Liste von Funktionen aus Anlage 2."""

    cfg = Anlage2Config.get_instance()

    def _normalize(s: str) -> str:
        return re.sub(r"[\s\-_/]+", "", s).lower()

    phrase_map: List[Tuple[str, Anlage2Function, Anlage2SubQuestion | None]] = []
    for func in Anlage2Function.objects.prefetch_related("anlage2subquestion_set"):
        aliases = [func.name]
        if hasattr(func, "detection_phrases") and func.detection_phrases:
            aliases.extend(func.detection_phrases.get("name_aliases", []))
        for alias in aliases:
            phrase_map.append((_normalize(alias), func, None))
        for sub in func.anlage2subquestion_set.all():
            sub_aliases = [sub.frage_text]
            if hasattr(sub, "detection_phrases") and sub.detection_phrases:
                sub_aliases.extend(sub.detection_phrases.get("name_aliases", []))
            for alias in sub_aliases:
                phrase_map.append((_normalize(alias), func, sub))

    token_map: List[Tuple[str, bool, List[str]]] = []
    for attr in dir(cfg):
        if not attr.startswith("text_"):
            continue
        phrases = getattr(cfg, attr, [])
        if not isinstance(phrases, list):
            continue
        if attr.endswith("_true"):
            field = attr[5:-5]
            token_map.append((field, True, [p.lower() for p in phrases]))
        elif attr.endswith("_false"):
            field = attr[5:-6]
            token_map.append((field, False, [p.lower() for p in phrases]))

    results: Dict[Tuple[int, int | None], Dict[str, object]] = {}
    last_key: Tuple[int, int | None] | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        norm = _normalize(line)
        matched: Tuple[Anlage2Function, Anlage2SubQuestion | None] | None = None
        for alias_norm, func, sub in phrase_map:
            if norm.startswith(alias_norm):
                matched = (func, sub)
                break

        def _apply_tokens(entry: Dict[str, object]) -> None:
            lower = line.lower()
            for field, value, phrases in token_map:
                if any(p in lower for p in phrases):
                    entry[field] = {"value": value, "note": None}

        if matched:
            func, sub = matched
            key = (func.id, sub.id if sub else None)
            entry = results.get(key)
            if not entry:
                name = func.name if sub is None else f"{func.name}: {sub.frage_text}"
                entry = {"funktion": name}
                results[key] = entry
            _apply_tokens(entry)
            last_key = key
        elif last_key is not None:
            entry = results[last_key]
            _apply_tokens(entry)

    return list(results.values())
