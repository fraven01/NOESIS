
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


def parse_anlage2_text(text: str, threshold: int = 80) -> List[dict[str, object]]:
    """Parst eine Freitext-Liste von Funktionen aus Anlage 2.

    Die neue Logik arbeitet zweistufig: Zuerst werden nur die
    Hauptfunktionen erkannt und bewertet. Anschließend erfolgt –
    ausschließlich bei technisch vorhandenen Hauptfunktionen – eine
    gezielte Suche nach zugehörigen Unterfragen.
    """

    parser_logger.info("parse_anlage2_text gestartet")
    cfg = Anlage2Config.get_instance()

    def _normalize(s: str) -> str:
        return re.sub(r"[\s\-_/]+", "", s).lower()

    # Aliase für Hauptfunktionen und Unterfragen aufbauen
    func_aliases: List[Tuple[str, Anlage2Function]] = []
    sub_aliases: Dict[int, List[Tuple[str, Anlage2SubQuestion]]] = {}
    func_map: Dict[int, Anlage2Function] = {}
    for func in Anlage2Function.objects.prefetch_related("anlage2subquestion_set"):
        func_map[func.id] = func
        aliases = [func.name]
        if getattr(func, "detection_phrases", None):
            aliases.extend(func.detection_phrases.get("name_aliases", []))
        for alias in aliases:
            func_aliases.append((_normalize(alias), func))

        sub_list: List[Tuple[str, Anlage2SubQuestion]] = []
        for sub in func.anlage2subquestion_set.all():
            sub_aliases_list = [sub.frage_text]
            if getattr(sub, "detection_phrases", None):
                sub_aliases_list.extend(sub.detection_phrases.get("name_aliases", []))
            for alias in sub_aliases_list:
                sub_list.append((_normalize(alias), sub))
        if sub_list:
            sub_aliases[func.id] = sub_list

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

    # Spezifischere Namen zuerst prüfen
    func_aliases.sort(key=lambda t: len(t[0]), reverse=True)
    for sub_list in sub_aliases.values():
        sub_list.sort(key=lambda t: len(t[0]), reverse=True)

    rules = list(AntwortErkennungsRegel.objects.all())

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
        parser_logger.debug("Prüfe Regeln in '%s'", text_part)
        found_rules: Dict[str, tuple[bool, int, str]] = {}
        for rule in rules:
            if rule.erkennungs_phrase.lower() in text_part.lower():
                current = found_rules.get(rule.ziel_feld)
                if current is None or rule.prioritaet < current[1]:
                    found_rules[rule.ziel_feld] = (rule.wert, rule.prioritaet, rule.erkennungs_phrase)
                    parser_logger.debug(
                        "Regel '%s' (%s) setzt %s=%s",
                        rule.regel_name,
                        rule.erkennungs_phrase,
                        rule.ziel_feld,
                        rule.wert,
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

    # Stufe 1: Hauptfunktionen erkennen
    main_results: Dict[int, Dict[str, object]] = {}
    sub_lines: Dict[int, List[Tuple[Anlage2SubQuestion, str]]] = {}
    current_func_id: int | None = None
    found_main: List[str] = []

    lines = text.splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        before, after = (line.split(":", 1) + [""])[0:2]
        before_norm = _normalize(before)

        matched_func: Anlage2Function | None = None
        for alias_norm, func in func_aliases:
            score = fuzz.partial_ratio(alias_norm, before_norm)
            if score >= threshold:
                matched_func = func
                parser_logger.debug("Hauptfunktion '%s' erkannt", func.name)
                break

        if matched_func:
            current_func_id = matched_func.id
            entry = main_results.get(current_func_id)
            if not entry:
                entry = {"funktion": matched_func.name}
                main_results[current_func_id] = entry
                found_main.append(matched_func.name)
            _apply_tokens(entry, after or line)
            _apply_rules(entry, after or line)
            continue

        if current_func_id is None:
            continue

        # Prüfen, ob die Zeile eine Unterfrage der aktuellen Funktion enthält
        matched_sub: Anlage2SubQuestion | None = None
        for alias_norm, sub in sub_aliases.get(current_func_id, []):
            score = fuzz.partial_ratio(alias_norm, before_norm)
            if score >= threshold:
                matched_sub = sub
                parser_logger.debug(
                    "Unterfrage '%s' erkannt", sub.frage_text
                )
                break

        if matched_sub:
            sub_lines.setdefault(current_func_id, []).append((matched_sub, line))
            continue

        # Keine Unterfrage -> zusätzliche Informationen zur aktuellen Funktion
        entry = main_results[current_func_id]
        _apply_tokens(entry, after or line)
        _apply_rules(entry, after or line)

    # Stufe 2: Unterfragen nur für vorhandene Funktionen prüfen
    sub_results: Dict[Tuple[int, int], Dict[str, object]] = {}
    for func_id, lines_list in sub_lines.items():
        main_entry = main_results.get(func_id)
        if not main_entry:
            continue
        tech = main_entry.get("technisch_verfuegbar")
        if not tech or tech.get("value") is not True:
            parser_logger.debug(
                "Überspringe Unterfragen zu '%s', da technisch nicht vorhanden",
                func_map[func_id].name,
            )
            continue

        for sub, line in lines_list:
            before, after = (line.split(":", 1) + [""])[0:2]
            key = (func_id, sub.id)
            entry = sub_results.get(key)
            if not entry:
                entry = {"funktion": f"{func_map[func_id].name}: {sub.frage_text}"}
                sub_results[key] = entry
            _apply_tokens(entry, after or line)
            _apply_rules(entry, after or line)

    all_results = list(main_results.values()) + list(sub_results.values())
    if found_main:
        parser_logger.info("Gefundene Funktionen: %s", ", ".join(found_main))
    parser_logger.info(
        "parse_anlage2_text beendet: %s Einträge", len(all_results)
    )
    return all_results


class FuzzyTextParser(AbstractParser):
    """Parser für Freitext mit Fuzzy-Logik."""

    name = "text"

    def parse(self, project_file: BVProjectFile) -> List[dict[str, object]]:
        return parse_anlage2_text(project_file.text_content or "")
