
from __future__ import annotations

import logging
import re
import string
from typing import List

from .models import (
    BVProjectFile,
    Anlage2Config,
    Anlage2Function,
    Anlage2SubQuestion,
)
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


def _normalize_snippet(text: str) -> str:
    """Normalisiert einen Textschnipsel für Alias-Vergleiche."""
    text = (
        text.replace("\n", " ")
        .replace("\t", " ")
        .replace("\u00b6", " ")
        .replace("\xa0", " ")
    )
    text = text.lower()
    text = re.sub(r"[\-_/]+", " ", text)
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_anlage2_text(text_content: str) -> list[dict[str, object]]:
    """Parst den Text einer Anlage 2 anhand der Konfiguration."""

    logger = logging.getLogger(__name__)
    parser_logger = logging.getLogger("parser_debug")
    parser_logger.info("parse_anlage2_text gestartet")

    if not text_content:
        return []

    def _get_list(data: dict | None, key: str) -> list[str]:
        val = data.get(key, []) if isinstance(data, dict) else []
        if isinstance(val, str):
            return [val]
        return [str(v) for v in val]

    functions: list[tuple[Anlage2Function, list[str]]] = []
    for func in Anlage2Function.objects.all():
        alias_list = [func.name]
        alias_list += _get_list(getattr(func, "detection_phrases", {}), "name_aliases")
        aliases = list(dict.fromkeys(_normalize_snippet(a) for a in alias_list))
        parser_logger.debug("Funktion '%s' Aliase: %s", func.name, aliases)
        functions.append((func, aliases))

    sub_map: dict[int, list[tuple[Anlage2SubQuestion, list[str]]]] = {}
    for sub in Anlage2SubQuestion.objects.select_related("funktion"):
        alias_list = [sub.frage_text]
        alias_list += _get_list(getattr(sub, "detection_phrases", {}), "name_aliases")
        aliases = list(dict.fromkeys(_normalize_snippet(a) for a in alias_list))
        parser_logger.debug(
            "Unterfrage '%s' (%s) Aliase: %s",
            sub.frage_text,
            sub.funktion.name,
            aliases,
        )
        sub_map.setdefault(sub.funktion_id, []).append((sub, aliases))

    cfg = Anlage2Config.get_instance()
    phrase_fields = [
        "technisch_verfuegbar_true",
        "technisch_verfuegbar_false",
        "einsatz_telefonica_true",
        "einsatz_telefonica_false",
        "zur_lv_kontrolle_true",
        "zur_lv_kontrolle_false",
        "ki_beteiligung_true",
        "ki_beteiligung_false",
    ]
    gp_dict: dict[str, list[str]] = {}
    for field in phrase_fields:
        phrases = getattr(cfg, f"text_{field}", []) or []
        for ph in phrases:
            parser_logger.debug("Globale Phrase '%s': %s", field, ph)
            norm = _normalize_snippet(ph)
            gp_dict.setdefault(field, []).append(norm)
    parser_logger.debug("Gesammelte globale Phrasen: %s", gp_dict)

    def _match(
        phrases: list[str],
        line: str,
        origin: str | None = None,
        raw_line: str | None = None,
    ) -> bool:
        valid_phrases = [p for p in phrases if p]
        if not valid_phrases:
            parser_logger.debug(
                "Keine gültigen Aliase zum Prüfen für '%s' vorhanden. Überspringe.",
                origin or "Unbekannt",
            )
            return False
        for ph in valid_phrases:
            if origin:
                if raw_line is not None:
                    parser_logger.debug(
                        "Prüfe Alias '%s' aus '%s' gegen Zeile '%s' (Rohtext: '%s')",
                        ph,
                        origin,
                        line,
                        raw_line,
                    )
                else:
                    parser_logger.debug(
                        "Prüfe Alias '%s' aus '%s' gegen Zeile '%s'",
                        ph,
                        origin,
                        line,
                    )
            else:
                parser_logger.debug("Prüfe Alias '%s' gegen Zeile '%s'", ph, line)
            if ph in line:
                parser_logger.debug("-> Treffer")
                return True
        return False

    def _extract_values(line: str, raw_line: str) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for field in [
            "technisch_verfuegbar",
            "einsatz_telefonica",
            "zur_lv_kontrolle",
            "ki_beteiligung",
        ]:
            val = None
            if _match(gp_dict.get(f"{field}_true", []), line, origin=f"{field}_true", raw_line=raw_line):
                val = True
            elif _match(gp_dict.get(f"{field}_false", []), line, origin=f"{field}_false", raw_line=raw_line):
                val = False
            if val is not None:
                result[field] = {"value": val, "note": None}
                parser_logger.debug("Extrahierter Wert für %s: %s", field, val)
        return result

    lines = [l.strip() for l in text_content.replace("\u00b6", "\n").splitlines()]
    results: list[dict[str, object]] = []
    results_by_func: dict[str, dict[str, object]] = {}
    last_main: dict[str, object] | None = None
    last_func: Anlage2Function | None = None

    for line in lines:
        parser_logger.debug("Prüfe Zeile: %s", line)
        norm_line = _normalize_snippet(line)
        parser_logger.debug("Zeile | ROH: %r | NORMALISIERT: %r", line, norm_line)
        if not norm_line:
            continue

        found = False

        if last_func:
            for sub, aliases in sub_map.get(last_func.id, []):
                if _match(aliases, norm_line, origin=f"Unterfrage {sub.frage_text}", raw_line=line):
                    full_name = f"{last_main['funktion']}: {sub.frage_text}"
                    parser_logger.debug("Unterfrage erkannt: %s", full_name)
                    row = {"funktion": full_name}
                    row.update(_extract_values(norm_line, line))
                    results.append(row)
                    found = True
                    break
        if found:
            continue

        for func, aliases in functions:
            if _match(aliases, norm_line, origin=f"Funktion {func.name}", raw_line=line):
                parser_logger.debug("Hauptfunktion erkannt: %s", func.name)
                new_data = {"funktion": func.name}
                new_data.update(_extract_values(norm_line, line))
                if func.name in results_by_func:
                    row = results_by_func[func.name]
                    row.update(new_data)
                else:
                    row = new_data
                    results_by_func[func.name] = row
                    results.append(row)
                last_main = row
                last_func = func
                found = True
                break

        if not found:
            extra_values = _extract_values(norm_line, line)
            if extra_values and last_main is not None:
                parser_logger.debug(
                    "Ergänze letzte Funktion %s um Werte %s",
                    last_main.get("funktion"),
                    extra_values,
                )
                last_main.update(extra_values)
            else:
                parser_logger.debug("Keine Funktion erkannt für Zeile: %s", line)

    logger.debug("parse_anlage2_text Ergebnisse: %s", results)
    parser_logger.info("parse_anlage2_text beendet")
    return results


