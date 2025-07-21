
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
            actions = rule.actions_json or {}
            for field, val in actions.items():
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


def parse_anlage2_text(
    text: str, threshold: int = FUZZY_THRESHOLD
) -> List[dict[str, object]]:
    """Parst eine Freitext-Liste von Funktionen aus Anlage 2.

    Die neue Logik arbeitet zweistufig: Zuerst werden nur die
    Hauptfunktionen erkannt und bewertet. Anschließend erfolgt –
    ausschließlich bei technisch vorhandenen Hauptfunktionen – eine
    gezielte Suche nach zugehörigen Unterfragen.
    """

    parser_logger.info("parse_anlage2_text gestartet")
    cfg = Anlage2Config.get_instance()

    func_aliases, sub_aliases, func_map = _load_alias_lists()

    token_map: Dict[str, List[Tuple[str, bool]]] = {}
    for attr in dir(cfg):
        if not attr.startswith("text_"):
            continue
        phrases = getattr(cfg, attr, [])
        if not isinstance(phrases, list):
            continue
        if attr.endswith("_true"):
            field = attr[5:-5]
            token_map.setdefault(field, []).extend(
                (p.lower(), True) for p in phrases
            )
        elif attr.endswith("_false"):
            field = attr[5:-6]
            token_map.setdefault(field, []).extend(
                (p.lower(), False) for p in phrases
            )

    rules_main = list(
        AntwortErkennungsRegel.objects.filter(
            regel_anwendungsbereich="Hauptfunktion"
        ).order_by("prioritaet")
    )
    rules_sub = list(
        AntwortErkennungsRegel.objects.filter(
            regel_anwendungsbereich="Unterfrage"
        ).order_by("prioritaet")
    )

    def _format_result(entry: Dict[str, object]) -> str:
        parts = []
        for key, val in entry.items():
            if key == "funktion":
                continue
            if isinstance(val, dict):
                val_str = str(val.get("value"))
                if val.get("note"):
                    val_str += f" ({val['note']})"
            else:
                val_str = str(val)
            parts.append(f"{key}={val_str}")
        return f"{entry['funktion']}: " + ", ".join(parts)

    # Stufe 1: Hauptfunktionen erkennen
    main_results: Dict[int, Dict[str, object]] = {}
    sub_lines: Dict[int, List[Tuple[Anlage2SubQuestion, str]]] = {}
    sub_results: Dict[Tuple[int, int], Dict[str, object]] = {}
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
            # Prüfen, ob im selben Text eine Unterfrage angesprochen wird
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
                entry = main_results.get(current_func_id)
                if not entry:
                    entry = {"funktion": matched_func.name, "_skip_output": True}
                    main_results[current_func_id] = entry
                    found_main.append(matched_func.name)
                apply_tokens(entry, after or line, token_map, threshold)
                apply_rules(entry, after or line, rules_main, threshold)

                key = (current_func_id, matched_sub.id)
                sub_entry = sub_results.get(key)
                if not sub_entry:
                    sub_entry = {
                        "funktion": f"{matched_func.name} - {matched_sub.frage_text}"
                    }
                sub_results[key] = sub_entry
                apply_tokens(sub_entry, after or line, token_map, threshold)
                apply_rules(sub_entry, after or line, rules_sub, threshold)
                sub_entry.pop("technisch_verfuegbar", None)
                continue

            entry = main_results.get(current_func_id)
            if not entry:
                entry = {"funktion": matched_func.name}
                main_results[current_func_id] = entry
                found_main.append(matched_func.name)
            apply_tokens(entry, after or line, token_map, threshold)
            apply_rules(entry, after or line, rules_main, threshold)
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
        apply_tokens(entry, after or line, token_map, threshold)
        apply_rules(entry, after or line, rules_main, threshold)

    # Stufe 2: Unterfragen nur für vorhandene Funktionen prüfen
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
            apply_tokens(entry, after or line, token_map, threshold)
            apply_rules(entry, after or line, rules_sub, threshold)
            entry.pop("technisch_verfuegbar", None)

    all_results = [
        entry for entry in main_results.values() if not entry.pop("_skip_output", False)
    ] + list(sub_results.values())
    if found_main:
        parser_logger.info("Gefundene Funktionen: %s", ", ".join(found_main))
    if all_results:
        summary = "; ".join(_format_result(e) for e in all_results)
        parser_logger.info("Ergebnisse: %s", summary)
    parser_logger.info(
        "parse_anlage2_text beendet: %s Einträge", len(all_results)
    )
    return all_results


class FuzzyTextParser(AbstractParser):
    """Parser für Freitext mit Fuzzy-Logik."""

    name = "text"

    def parse(self, project_file: BVProjectFile) -> List[dict[str, object]]:
        return parse_anlage2_text(project_file.text_content or "")
