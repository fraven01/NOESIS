
from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple



from .models import (
    BVProjectFile,
    Anlage2Config,
    Anlage2Function,
    Anlage2SubQuestion,
    AntwortErkennungsRegel,
)

logger = logging.getLogger(__name__)
detail_logger = logging.getLogger("anlage2_detail")
result_logger = logging.getLogger("anlage2_result")

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
    """Prüft präzise, ob eine Phrase als zusammenhängende Wortfolge im Text vorkommt.

    Interne Leerzeichen werden flexibel als ``\s+`` behandelt, sodass auch
    variierende Abstände oder Zeilenumbrüche erkannt werden. Groß- und
    Kleinschreibung werden ignoriert. Der ``threshold``-Parameter existiert
    nur aus Kompatibilitätsgründen und hat keine Funktion mehr.
    """

    words = phrase.split()
    pattern = r"\b" + r"\s+".join(map(re.escape, words)) + r"\b"
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
    detail_logger.debug("Prüfe Tokens in '%s'", text_part)
    for field, items in token_map.items():
        if field in entry:
            continue
        for phrase, value in sorted(items, key=lambda t: len(t[0]), reverse=True):
            if fuzzy_match(phrase, text_part, threshold):
                detail_logger.debug(
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
    *,
    func_name: str | None = None,
) -> None:
    """Wendet Antwortregeln auf einen Textabschnitt an.

    Der optionale Parameter ``func_name`` dient ausschließlich der Protokoll-
    lierung und legt fest, zu welcher Funktion die Prüfung gehört.
    """
    detail_logger.debug("Prüfe Regeln in '%s'", text_part)
    found_rules: Dict[str, tuple[bool, int, str, str]] = {}
    for rule in rules:
        if fuzzy_match(rule.erkennungs_phrase, text_part, threshold):
            actions = rule.actions_json or []
            if isinstance(actions, dict):
                actions = [{"field": k, "value": v} for k, v in actions.items()]
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
                        rule.regel_name,
                    )

    if not found_rules:
        return

    for field, (val, _prio, _phrase, rule_name) in found_rules.items():
        detail_logger.debug(
            "-> Regel '%s' gefunden. Setzt '%s' auf '%s'.",
            rule_name,
            field,
            val,
        )
        entry[field] = {"value": val, "note": None}

    remaining = text_part
    for _val, _prio, phrase, _rule_name in found_rules.values():
        remaining = re.sub(re.escape(phrase), "", remaining, flags=re.I)
    remaining = remaining.strip()

    if remaining:
        best_field = min(found_rules.items(), key=lambda i: i[1][1])[0]
        entry[best_field]["note"] = remaining


def _clean_text(text: str) -> str:
    """Entfernt Sonderzeichen vor der Zeilenaufteilung."""

    text = text.replace("\n", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = text.replace("\u00b6", " ")
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _split_lines(text: str) -> list[str]:
    """Zerteilt einen Text in bereinigte Zeilen."""

    text = text.replace("\u00b6", "\n").replace("\r", "\n")
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        line = re.sub(r"\s{2,}", " ", line.replace("\t", " ")).strip()
        if line:
            cleaned.append(line)
    return cleaned


def _alias_regex(alias: str) -> str:
    """Erzeugt ein flexibles Regex für einen Funktionsalias."""

    parts = re.split(r"[\s\-_/]+", alias.strip())
    pattern = r"[\s\-_/]*".join(map(re.escape, parts))
    return rf"^{pattern}[\s\-_:]*"


def extract_function_segments(text: str) -> list[tuple[str, str]]:
    """Zerlegt einen Dokumententext in Funktionssegmente.

    Jeder erkannte Funktions- oder Unterfragen-Block wird als Tupel aus
    Funktionsbezeichnung und zugehörigem Textabschnitt zurückgegeben.
    Nachfolgende Zeilen ohne erneute Funktionsangabe werden dem zuletzt
    gefundenen Segment zugeordnet.
    """

    lines = _split_lines(text)
    func_aliases, sub_aliases, func_map = _load_alias_lists()

    segments: list[tuple[str, str]] = []
    current_key: str | None = None

    for raw in lines:
        line = re.sub(r"^[\d]+[.)]\s*", "", raw).strip()
        if not line:
            continue

        found_key = None
        found_alias = None
        line_norm = _normalize(line.split(":", 1)[0])

        for func_id, aliases in sub_aliases.items():
            for alias_norm, sub in aliases:
                if line_norm.startswith(alias_norm):
                    func = func_map[func_id]
                    found_key = f"{func.name}: {sub.frage_text}"
                    found_alias = sub.frage_text
                    break
            if found_key:
                break

        if not found_key:
            for alias_norm, func in func_aliases:
                if line_norm.startswith(alias_norm):
                    found_key = func.name
                    found_alias = func.name
                    break

        text_part = line
        if found_key:
            current_key = found_key
            if ":" in line:
                text_part = line.split(":", 1)[1].strip()
            else:
                text_part = re.sub(_alias_regex(found_alias), "", line, flags=re.I).strip()
            segments.append((found_key, text_part))
        elif current_key:
            segments.append((current_key, line))

    return segments


def parse_anlage2_text(text: str) -> List[dict[str, object]]:
    """Parst die Freitextvariante der Anlage 2."""

    detail_logger.info("parse_anlage2_text gestartet")

    cfg = Anlage2Config.get_instance()
    token_map = build_token_map(cfg)
    rules = list(AntwortErkennungsRegel.objects.all())

    segments = extract_function_segments(text)

    results: dict[str, dict[str, object]] = {}
    order: list[str] = []

    for func_name, text_part in segments:
        if ":" in func_name:
            main_name = func_name.split(":", 1)[0]
            main_entry = results.get(main_name)
            if not main_entry or main_entry.get("technisch_verfuegbar", {}).get("value") is not True:
                continue

        entry = results.setdefault(func_name, {"funktion": func_name})
        if func_name not in order:
            order.append(func_name)
            detail_logger.info("[Analyse Funktion: '%s']", func_name)

        line_entry: dict[str, object] = {}
        apply_tokens(line_entry, text_part, token_map)
        apply_rules(line_entry, text_part, rules, func_name=func_name)
        for key, value in line_entry.items():
            entry[key] = value

    ordered_results = [results[k] for k in order]
    for res in ordered_results:
        detail_logger.info(
            "--> Endergebnis für '%s': %s",
            res.get("funktion"),
            res,
        )
        result_logger.info(
            "Ergebnis Funktion '%s': %s",
            res.get("funktion"),
            res,
        )
    return ordered_results


