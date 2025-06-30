"""Einfache Parser-Funktionen fuer Freitextdokumente.

Dieses Modul enthaelt eine Funktion zum Parsen von Zeilen im Format
"[Funktionsname]: [Statussatz]". Der Statussatz kann Angaben zu drei
Bewertungsfeldern enthalten:

* technisch_verfuegbar
* soll_verwendet_werden
* ueberwachung_leistung_verhalten

Hinter einer Funktionszeile koennen optionale Detailfragen folgen, die mit
"-" beginnen. Sie muessen das Muster "- Frage? Antwort" einhalten.

Die Rueckgabe erfolgt als Liste von Dictionaries und spiegelt damit die
Struktur der Review-Ansicht wider.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


_TRUE_WORDS = {"ja", "yes", "true", "wahr", "1"}
_FALSE_WORDS = {"nein", "no", "false", "0", "nicht", "kein"}


def _to_bool(token: str) -> bool | None:
    """Wandelt ein Wort in einen Bool-Wert um."""
    t = token.strip().lower()
    if t in _TRUE_WORDS:
        return True
    if t in _FALSE_WORDS:
        return False
    return None


def _extract_value(sentence: str, keywords: List[str]) -> bool | None:
    """Sucht nach einem Ja/Nein-Wert in ``sentence`` nach einem Stichwort."""
    s = sentence.lower()
    for kw in keywords:
        idx = s.find(kw)
        if idx != -1:
            after = s[idx:]
            m = re.search(r"\b(ja|nein|yes|no|true|false|nicht|kein)\b", after)
            if m:
                return _to_bool(m.group(1))
    return None


def _parse_status_sentence(sentence: str) -> Dict[str, bool | None]:
    """Extrahiert die drei Bewertungsfelder aus dem Satz."""

    return {
        "technisch_verfuegbar": _extract_value(
            sentence, ["technisch", "verfuegbar", "verf\u00fcgbar"]
        ),
        "soll_verwendet_werden": _extract_value(
            sentence, ["soll", "verwendet", "verwenden"]
        ),
        "ueberwachung_leistung_verhalten": _extract_value(
            sentence, ["\u00fcberwachung", "ueberwachung", "leistung", "verhalten"]
        ),
    }


def parse_function_statuses(text: str) -> List[Dict[str, Any]]:
    """Parst ein komplettes Dokument.

    Jede Zeile mit dem Muster ``"Name: Status"`` erzeugt einen neuen
    Eintrag. Darauffolgende Zeilen, die mit ``"-"`` beginnen, werden als
    Detailfrage gewertet und dem letzten Eintrag hinzugefuegt.
    """

    results: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = re.match(r"^(?P<func>[^:]+):\s*(?P<status>.+)$", line)
        if match:
            if current:
                results.append(current)
            current = {"funktion": match.group("func").strip()}
            status = match.group("status")
            current.update(_parse_status_sentence(status))
            continue

        if current and line.startswith("-"):
            q_match = re.match(r"^-\s*(?P<frage>[^?]+\?)\s*(?P<antwort>.+)$", line)
            if q_match:
                details = current.setdefault("details", [])
                details.append({
                    "frage": q_match.group("frage").strip(),
                    "antwort": q_match.group("antwort").strip(),
                })

    if current:
        results.append(current)

    return results
