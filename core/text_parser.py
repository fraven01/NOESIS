
from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple

from thefuzz import process

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


def parse_anlage2_text(text: str, threshold: int = 80) -> List[dict[str, object]]:
    """Parst eine Freitext-Liste von Funktionen aus Anlage 2.

    Vor dem Doppelpunkt stehende Fragmente werden mittels Fuzzy-Matching mit den
    in der Datenbank hinterlegten Fragen abgeglichen. Der ``threshold`` gibt an,
    ab welcher Ähnlichkeit (0–100) ein Treffer akzeptiert wird.
    """

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

    alias_strings = [a for a, _, _ in phrase_map]
    alias_lookup = {a: (f, s) for a, f, s in phrase_map}
    rules = list(AntwortErkennungsRegel.objects.all())

    results: Dict[Tuple[int, int | None], Dict[str, object]] = {}
    unmatched: List[Dict[str, object]] = []
    last_key: Tuple[int, int | None] | None = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        parser_logger.debug("Verarbeite Zeile: '%s'", line)
        before, after = (line.split(":", 1) + [""])[0:2]
        parser_logger.debug("Vor dem Doppelpunkt: '%s', danach: '%s'", before, after)
        before_norm = _normalize(before)
        parser_logger.debug("Normalisiere '%s' zu '%s'", before, before_norm)
        match = process.extractOne(before_norm, alias_strings)
        matched: Tuple[Anlage2Function, Anlage2SubQuestion | None] | None = None
        if match:
            func, sub = alias_lookup.get(match[0], (None, None))
            q_name = (
                func.name
                if func and sub is None
                else f"{func.name}: {sub.frage_text}" if func else match[0]
            )
            parser_logger.debug(
                "Fuzzy-Match '%s' gegen '%s' (%s%%)", before_norm, q_name, match[1]
            )
            if match[1] >= threshold:
                matched = (func, sub)
        else:
            parser_logger.debug("Kein Fuzzy-Treffer für '%s'", before)

        def _apply_tokens(entry: Dict[str, object], text_part: str) -> None:
            lower = text_part.lower()
            parser_logger.debug("Prüfe Tokens in '%s'", text_part)
            for field, value, phrases in token_map:
                for phrase in phrases:
                    if phrase in lower:
                        parser_logger.debug(
                            "Token '%s' gefunden, setze %s=%s",
                            phrase,
                            field,
                            value,
                        )
                        entry[field] = {"value": value, "note": None}
                        break

        def _apply_rules(entry: Dict[str, object], text_part: str) -> None:
            remaining = text_part
            matched_fields: List[str] = []
            parser_logger.debug("Prüfe Regeln in '%s'", text_part)
            for rule in rules:
                if rule.erkennungs_phrase.lower() in remaining.lower():
                    entry[rule.ziel_feld] = {"value": rule.wert, "note": None}
                    parser_logger.debug(
                        "Regel '%s' (%s) setzt %s=%s",
                        rule.regel_name,
                        rule.erkennungs_phrase,
                        rule.ziel_feld,
                        rule.wert,
                    )
                    matched_fields.append(rule.ziel_feld)
                    remaining = re.sub(
                        re.escape(rule.erkennungs_phrase),
                        "",
                        remaining,
                        flags=re.I,
                    ).strip()
            if remaining and matched_fields:
                first = matched_fields[0]
                entry[first]["note"] = remaining

        if matched:
            func, sub = matched
            key = (func.id, sub.id if sub else None)
            entry = results.get(key)
            if not entry:
                name = func.name if sub is None else f"{func.name}: {sub.frage_text}"
                entry = {"funktion": name}
                results[key] = entry
                parser_logger.debug("Neuer Eintrag für '%s'", name)
            _apply_tokens(entry, after or line)
            if after:
                _apply_rules(entry, after)
            last_key = key
        elif last_key is not None:
            entry = results[last_key]
            parser_logger.debug(
                "Aktualisiere vorherige Funktion '%s' mit '%s'",
                entry.get("funktion"),
                line,
            )
            _apply_tokens(entry, after or line)
            if after:
                _apply_rules(entry, after)
        else:
            parser_logger.warning("Keine Funktion gefunden für Zeile: %s", line)
            entry = {"funktion": before}
            _apply_tokens(entry, after or line)
            if after:
                _apply_rules(entry, after)
            entry.setdefault("technisch_verfuegbar", {"value": False, "note": None})
            unmatched.append(entry)

    return list(results.values()) + unmatched


class FuzzyTextParser(AbstractParser):
    """Parser für Freitext mit Fuzzy-Logik."""

    name = "text"

    def parse(self, project_file: BVProjectFile) -> List[dict[str, object]]:
        return parse_anlage2_text(project_file.text_content or "")
