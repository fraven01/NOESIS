"""LLM-gest\xFCtzte Aufgaben f\xFCr BV-Projekte."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from django.conf import settings

from .models import BVProject, BVProjectFile, Prompt
from .llm_utils import query_llm
from docx import Document

logger = logging.getLogger(__name__)


def _add_editable_flags(data: dict) -> dict:
    """Ergänzt jedes Feld eines Dictionaries um ein ``editable``-Flag."""
    if isinstance(data, dict):
        return {k: {"value": v, "editable": True} for k, v in data.items()}
    return data


def get_prompt(name: str, default: str) -> str:
    """Lade einen Prompt-Text aus der Datenbank."""
    try:
        return Prompt.objects.get(name=name).text
    except Prompt.DoesNotExist:
        return default


def _collect_text(projekt: BVProject) -> str:
    """Fasst die Textinhalte aller Anlagen zusammen."""
    parts: list[str] = []
    for anlage in projekt.anlagen.all():
        if anlage.text_content:
            parts.append(f"Anlage {anlage.anlage_nr}\n{anlage.text_content}")
    return "\n\n".join(parts)


def parse_structured_anlage(text_content: str) -> dict | None:
    """Parst eine strukturiert aufgebaute Anlage."""
    if not text_content:
        return None
    lines = [line.strip() for line in text_content.split("\u00b6") if line.strip()]
    question_pattern = re.compile(r"^(\d+)\.->.*\?$")
    if not any(question_pattern.match(line) for line in lines):
        return None
    parsed: dict[str, str] = {}
    for idx, line in enumerate(lines):
        m = question_pattern.match(line)
        if m:
            qnum = m.group(1)
            if idx + 1 < len(lines):
                ans = lines[idx + 1]
                if not question_pattern.match(ans):
                    parsed[qnum] = ans
    return parsed if parsed else None


def classify_system(projekt_id: int, model_name: str | None = None) -> dict:
    """Klassifiziert das System eines Projekts und speichert das Ergebnis."""
    projekt = BVProject.objects.get(pk=projekt_id)
    prefix = get_prompt(
        "classify_system",
        "Bitte klassifiziere das folgende Softwaresystem. Gib ein JSON mit den Schl\xFCsseln 'kategorie' und 'begruendung' zur\xFCck.\n\n",
    )
    prompt = prefix + _collect_text(projekt)
    reply = query_llm(prompt, model_name=model_name, model_type="default")
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        logger.warning("LLM Antwort kein JSON: %s", reply)
        data = {"raw": reply}
    data = _add_editable_flags(data)
    projekt.classification_json = data
    projekt.status = BVProject.STATUS_CLASSIFIED
    projekt.save(update_fields=["classification_json", "status"])
    return data


def generate_gutachten(
    projekt_id: int, text: str | None = None, model_name: str | None = None
) -> Path:
    """Erstellt ein Gutachten-Dokument mithilfe eines LLM."""
    projekt = BVProject.objects.get(pk=projekt_id)
    if text is None:
        prefix = get_prompt(
            "generate_gutachten",
            "Erstelle ein technisches Gutachten basierend auf deinem Wissen:\n\n",
        )
        prompt = prefix + projekt.software_typen
        text = query_llm(prompt, model_name=model_name, model_type="gutachten")
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    fname = f"gutachten_{uuid.uuid4().hex}.docx"
    out_dir = Path(settings.MEDIA_ROOT) / "gutachten"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / fname
    # Bestehende Datei entfernen, falls vorhanden
    if projekt.gutachten_file and projekt.gutachten_file.name:
        old_path = Path(settings.MEDIA_ROOT) / projekt.gutachten_file.name
        old_path.unlink(missing_ok=True)
    doc.save(path)
    projekt.gutachten_file.name = f"gutachten/{fname}"
    projekt.status = BVProject.STATUS_GUTACHTEN_OK
    projekt.save(update_fields=["gutachten_file", "status"])
    return path


def _check_anlage(projekt_id: int, nr: int, model_name: str | None = None) -> dict:
    """Pr\xFCft eine Anlage und speichert das Ergebnis."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=nr)
    except BVProjectFile.DoesNotExist as exc:  # pragma: no cover - Test deckt Abwesenheit nicht ab
        raise ValueError(f"Anlage {nr} fehlt") from exc

    prefix = get_prompt(
        f"check_anlage{nr}",
        "Pr\xFCfe die folgende Anlage auf Vollst\xE4ndigkeit. Gib ein JSON mit 'ok' und 'hinweis' zur\xFCck:\n\n",
    )
    prompt = prefix + anlage.text_content

    reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        data = {"raw": reply}

    data = _add_editable_flags(data)
    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    return data


def check_anlage1(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xFCft die erste Anlage nach neuem Schema."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=1)
    except BVProjectFile.DoesNotExist as exc:  # pragma: no cover - sollte selten passieren
        raise ValueError("Anlage 1 fehlt") from exc

    parsed = parse_structured_anlage(anlage.text_content)
    if parsed:
        logger.info("Strukturiertes Dokument erkannt. Parser wird verwendet.")
        questions = {
            str(i): {
                "answer": parsed.get(str(i)),
                "ok": None,
                "note": "Geparst",
            }
            for i in range(1, 10)
        }
        data = {
            "task": "check_anlage1",
            "source": "parser",
            "questions": questions,
        }
        anlage.analysis_json = data
        anlage.save(update_fields=["analysis_json"])
        return data

    default_prompt = (
            "System: Du bist ein juristisch-technischer Pr\u00fcf-Assistent f\u00fcr Systembeschreibungen.\n\n"
            "Frage 1: Extrahiere alle Unternehmen als Liste.\n"
            "Frage 2: Extrahiere alle Fachbereiche als Liste.\n"
            "IT-Landschaft: Fasse den Abschnitt zusammen, der die Einbettung in die IT-Landschaft beschreibt.\n"
            "Frage 3: Liste alle Hersteller und Produktnamen auf.\n"
            "Frage 4: Lege den Textblock als question4_raw ab.\n"
            "Frage 5: Fasse den Zweck des Systems in einem Satz.\n"
            "Frage 6: Extrahiere Web-URLs.\n"
            "Frage 7: Extrahiere ersetzte Systeme.\n"
            "Frage 8: Extrahiere Legacy-Funktionen.\n"
            "Frage 9: Lege den Text als question9_raw ab.\n"
            "Konsistenzpr\u00fcfung und Stichworte. Gib ein JSON im vorgegebenen Schema zur\u00fcck.\n\n"
        )

    prefix = get_prompt("check_anlage1", default_prompt)
    prompt = prefix + anlage.text_content

    reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        data = {"raw": reply}

    def _val(key):
        if isinstance(data.get(key), dict) and "value" in data[key]:
            return data[key]["value"]
        return data.get(key)

    questions = {
        "1": {"answer": _val("companies"), "ok": None, "note": ""},
        "2": {"answer": _val("departments"), "ok": None, "note": ""},
        "3": {"answer": _val("vendors"), "ok": None, "note": ""},
        "4": {"answer": _val("question4_raw"), "ok": None, "note": ""},
        "5": {"answer": _val("purpose_summary"), "ok": None, "note": ""},
        "6": {"answer": _val("documentation_links"), "ok": None, "note": ""},
        "7": {"answer": _val("replaced_systems"), "ok": None, "note": ""},
        "8": {"answer": _val("legacy_functions"), "ok": None, "note": ""},
        "9": {"answer": _val("question9_raw"), "ok": None, "note": ""},
    }

    def _is_purpose(text: str) -> bool:
        if not text:
            return False
        lowered = text.lower()
        return any(k in lowered for k in ["zweck", "dient", " um ", " zur ", " f\u00fcr "])

    q5 = questions.get("5")
    if q5:
        q5["ok"] = _is_purpose(str(q5.get("answer", "")))

    data["questions"] = questions

    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    return data


def check_anlage2(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xFCft die zweite Anlage."""
    return _check_anlage(projekt_id, 2, model_name)


def check_anlage3(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xFCft die dritte Anlage."""
    return _check_anlage(projekt_id, 3, model_name)


def check_anlage4(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xFCft die vierte Anlage."""
    return _check_anlage(projekt_id, 4, model_name)


def check_anlage5(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xFCft die f\xFCnfte Anlage."""
    return _check_anlage(projekt_id, 5, model_name)


def check_anlage6(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xFCft die sechste Anlage."""
    return _check_anlage(projekt_id, 6, model_name)
