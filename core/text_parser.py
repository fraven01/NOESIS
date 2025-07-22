
from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple


from thefuzz import fuzz

from .models import (
    BVProjectFile,
    FormatBParserRule,
    Anlage2Config,
    Anlage2Function,
    Anlage2SubQuestion,
    AntwortErkennungsRegel,
)
from .parsers import AbstractParser

logger = logging.getLogger(__name__)
parser_logger = logging.getLogger("parser_debug")

# Standard-Schwelle für Fuzzy-Vergleiche
FUZZY_THRESHOLD = 80


def _normalize(text: str) -> str:
    """Normalisiert einen Begriff für Vergleiche."""

    return re.sub(r"[\s\-_/]+", "", text).lower()


def _load_alias_lists() -> tuple[
    list[tuple[str, Anlage2Function]],
    dict[int, list[tuple[str, Anlage2SubQuestion]]],
    dict[int, Anlage2Function],
]:
    """Lädt alle Funktions- und Unterfragen-Aliase."""

    func_aliases: list[tuple[str, Anlage2Function]] = []
    sub_aliases: dict[int, list[tuple[str, Anlage2SubQuestion]]] = {}
    func_map: dict[int, Anlage2Function] = {}

    for func in Anlage2Function.objects.prefetch_related("anlage2subquestion_set"):
        func_map[func.id] = func
        aliases = [func.name]
        if func.detection_phrases:
            aliases.extend(func.detection_phrases.get("name_aliases", []))
        for alias in aliases:
            func_aliases.append((_normalize(alias), func))

        sub_list: list[tuple[str, Anlage2SubQuestion]] = []
        for sub in func.anlage2subquestion_set.all():
            sub_aliases_list = [sub.frage_text]
            if sub.detection_phrases:
                sub_aliases_list.extend(sub.detection_phrases.get("name_aliases", []))
            for alias in sub_aliases_list:
                sub_list.append((_normalize(alias), sub))
        if sub_list:
            sub_aliases[func.id] = sub_list

    func_aliases.sort(key=lambda t: len(t[0]), reverse=True)
    for sub_list in sub_aliases.values():
        sub_list.sort(key=lambda t: len(t[0]), reverse=True)

    return func_aliases, sub_aliases, func_map


def fuzzy_match(phrase: str, text: str, threshold: int = FUZZY_THRESHOLD) -> bool:
    """Prüft präzise, ob eine Phrase als exakte Wortfolge im Text vorkommt.

    Verwendet reguläre Ausdrücke mit Wortgrenzen (\b), um Fehler
    durch Teil-Übereinstimmungen zu vermeiden. Die Suche ignoriert
    Groß- und Kleinschreibung. Der ``threshold``-Parameter wird aus
    Kompatibilitätsgründen beibehalten, aber nicht verwendet.
    """

    # re.escape behandelt mögliche Sonderzeichen in der Suchphrase.
    # \b sorgt für die Übereinstimmung ganzer Wörter.
    pattern = r"\b" + re.escape(phrase) + r"\b"

    # re.search findet das Muster an beliebiger Stelle im Text.
    # re.IGNORECASE ignoriert Groß-/Kleinschreibung.
    return bool(re.search(pattern, text, re.IGNORECASE))

# Globale Phrasenarten, die beim Parsen von Freitext erkannt werden.
PHRASE_TYPE_CHOICES: list[tuple[str, str]] = [
    ("einsatz_telefonica_false", "einsatz_telefonica_false"),
    ("einsatz_telefonica_true", "einsatz_telefonica_true"),
    ("ki_beteiligung_false", "ki_beteiligung_false"),
    ("ki_beteiligung_true", "ki_beteiligung_true"),
    ("technisch_verfuegbar_false", "technisch_verfuegbar_false"),
    ("technisch_verfuegbar_true", "technisch_verfuegbar_true"),
    ("zur_lv_kontrolle_false", "zur_lv_kontrolle_false"),
    ("zur_lv_kontrolle_true", "zur_lv_kontrolle_true"),
]



def parse_format_b(text: str) -> List[dict[str, object]]:
    """Parst ein einfaches Listenformat von Anlage 2.

    Mehrere Zeilen können verarbeitet werden.
    Jede Zeile enthält einen Funktionsnamen und optionale Tokens
    wie ``tv``, ``tel``, ``lv`` und ``ki``.
    Eine vorausgehende Nummerierung wie ``1.`` wird ignoriert.
    """

    parser_logger.info("parse_format_b gestartet")
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

    parser_logger.info("parse_format_b beendet: %s Einträge", len(results))

    return results


def build_token_map(cfg: Anlage2Config) -> Dict[str, List[Tuple[str, bool]]]:
    """Erstellt die Token-Zuordnung für Anlage 2."""
    token_map: Dict[str, List[Tuple[str, bool]]] = {}
    for attr in dir(cfg):
        if not attr.startswith("text_"):
            continue
        phrases = getattr(cfg, attr, [])
        if not isinstance(phrases, list):
            continue
        if attr.endswith("_true"):
            field = attr[5:-5]
            token_map.setdefault(field, []).extend((p.lower(), True) for p in phrases)
        elif attr.endswith("_false"):
            field = attr[5:-6]
            token_map.setdefault(field, []).extend((p.lower(), False) for p in phrases)
    return token_map


def apply_tokens(
    entry: Dict[str, object],
    text_part: str,
    token_map: Dict[str, List[Tuple[str, bool]]],
    threshold: int = FUZZY_THRESHOLD,
) -> None:
    """Wendet Token-Regeln auf einen Textabschnitt an."""
    parser_logger.debug("Prüfe Tokens in '%s'", text_part)
    for field, items in token_map.items():
        if field in entry:
            continue
        for phrase, value in sorted(items, key=lambda t: len(t[0]), reverse=True):
            if fuzzy_match(phrase, text_part, threshold):
                parser_logger.debug(
                    "Token '%s' gefunden, setze %s=%s",
                    phrase,
                    field,
                    value,
                )
                entry[field] = {"value": value, "note": None}
                break


def apply_rules(
    entry: Dict[str, object],
    text_part: str,
    rules: List[AntwortErkennungsRegel],
    threshold: int = FUZZY_THRESHOLD,
) -> None:
    """Wendet Antwortregeln auf einen Textabschnitt an."""
    parser_logger.debug("Prüfe Regeln in '%s'", text_part)
    found_rules: Dict[str, tuple[bool, int, str]] = {}
    for rule in rules:
        if fuzzy_match(rule.erkennungs_phrase, text_part, threshold):
            actions = rule.actions_json or []
            if isinstance(actions, dict):
                actions = [
                    {"field": k, "value": v} for k, v in actions.items()
                ]
            for act in actions:
                field = act.get("field")
                if not field:
                    continue
                val = act.get("value")
                current = found_rules.get(field)
                if current is None or rule.prioritaet < current[1]:
                    found_rules[field] = (
                        bool(val),
                        rule.prioritaet,
                        rule.erkennungs_phrase,
                    )
                    parser_logger.debug(
                        "Regel '%s' (%s) setzt %s=%s",
                        rule.regel_name,
                        rule.erkennungs_phrase,
                        field,
                        val,
                    )

    if not found_rules:
        return

    for field, (val, _prio, _phrase) in found_rules.items():
        entry[field] = {"value": val, "note": None}

    remaining = text_part
    for _val, _prio, phrase in found_rules.values():
        remaining = re.sub(re.escape(phrase), "", remaining, flags=re.I)
    remaining = remaining.strip()

    if remaining:
        best_field = min(found_rules.items(), key=lambda i: i[1][1])[0]
        entry[best_field]["note"] = remaining


def parse_anlage2_text(text: str) -> List[dict[str, object]]:
    """Platzhalter für die Textparser-Logik."""

    parser_logger.info("parse_anlage2_text gestartet")
    return []


