"""LLM-gest\xFCtzte Aufgaben f\xFCr BV-Projekte."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from django.conf import settings

from .models import BVProject, BVProjectFile
from .llm_utils import query_llm
from docx import Document

logger = logging.getLogger(__name__)


def _collect_text(projekt: BVProject) -> str:
    """Fasst die Textinhalte aller Anlagen zusammen."""
    parts: list[str] = []
    for anlage in projekt.anlagen.all():
        if anlage.text_content:
            parts.append(f"Anlage {anlage.anlage_nr}\n{anlage.text_content}")
    return "\n\n".join(parts)


def classify_system(projekt_id: int) -> dict:
    """Klassifiziert das System eines Projekts und speichert das Ergebnis."""
    projekt = BVProject.objects.get(pk=projekt_id)
    prompt = (
        "Bitte klassifiziere das folgende Softwaresystem. "
        "Gib ein JSON mit den Schl\xFCsseln 'kategorie' und 'begruendung' zur\xFCck.\n\n"
        + _collect_text(projekt)
    )
    reply = query_llm(prompt)
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        logger.warning("LLM Antwort kein JSON: %s", reply)
        data = {"raw": reply}
    projekt.classification_json = data
    projekt.status = BVProject.STATUS_CLASSIFIED
    projekt.save(update_fields=["classification_json", "status"])
    return data


def generate_gutachten(projekt_id: int) -> Path:
    """Erstellt ein Gutachten-Dokument mithilfe eines LLM."""
    projekt = BVProject.objects.get(pk=projekt_id)
    prompt = "Erstelle ein kurzes Gutachten basierend auf diesen Unterlagen:\n\n" + _collect_text(projekt)
    text = query_llm(prompt)
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    fname = f"gutachten_{uuid.uuid4().hex}.docx"
    out_dir = Path(settings.MEDIA_ROOT) / "gutachten"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / fname
    doc.save(path)
    projekt.gutachten_file.name = f"gutachten/{fname}"
    projekt.status = BVProject.STATUS_GUTACHTEN_OK
    projekt.save(update_fields=["gutachten_file", "status"])
    return path


def _check_anlage(projekt_id: int, nr: int) -> dict:
    """Pr\xFCft eine Anlage und speichert das Ergebnis."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=nr)
    except BVProjectFile.DoesNotExist as exc:  # pragma: no cover - Test deckt Abwesenheit nicht ab
        raise ValueError(f"Anlage {nr} fehlt") from exc

    prompt = (
        "Pr\xFCfe die folgende Anlage auf Vollst\xE4ndigkeit. "
        "Gib ein JSON mit 'ok' und 'hinweis' zur\xFCck:\n\n" + anlage.text_content
    )

    reply = query_llm(prompt)
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        data = {"raw": reply}

    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    return data


def check_anlage1(projekt_id: int) -> dict:
    """Pr\xFCft die erste Anlage."""
    return _check_anlage(projekt_id, 1)


def check_anlage2(projekt_id: int) -> dict:
    """Pr\xFCft die zweite Anlage."""
    return _check_anlage(projekt_id, 2)


def check_anlage3(projekt_id: int) -> dict:
    """Pr\xFCft die dritte Anlage."""
    return _check_anlage(projekt_id, 3)


def check_anlage4(projekt_id: int) -> dict:
    """Pr\xFCft die vierte Anlage."""
    return _check_anlage(projekt_id, 4)


def check_anlage5(projekt_id: int) -> dict:
    """Pr\xFCft die f\xFCnfte Anlage."""
    return _check_anlage(projekt_id, 5)


def check_anlage6(projekt_id: int) -> dict:
    """Pr\xFCft die sechste Anlage."""
    return _check_anlage(projekt_id, 6)
