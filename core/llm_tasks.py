"""Hilfsfunktionen für LLM-Aufgaben."""

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.base import File

from .models import BVProject, BVProjectFile
from .llm_utils import query_llm


_DEF_ENCODING = "utf-8"


def _read_anlagen(project: BVProject) -> dict[str, str]:
    """Liest alle Textdateien des Projekts ein."""
    texts: dict[str, str] = {}
    for pf in project.files.all():
        try:
            path = Path(pf.file.path)
        except ValueError:
            continue
        if path.suffix.lower() in {".txt", ".md"} and path.exists():
            texts[pf.category or path.stem] = path.read_text(encoding=_DEF_ENCODING)
    return texts


def classify_system(project_id: int) -> dict[str, Any]:
    """Klassifiziert das System anhand der vorhandenen Anlagen."""
    projekt = BVProject.objects.get(pk=project_id)
    texts = _read_anlagen(projekt)
    prompt = (
        "Analysiere folgende Dokumente und erstelle eine JSON-Zusammenfassung "
        "des Softwaresystems:\n\n" + "\n\n".join(texts.values())
    )
    antwort = query_llm(prompt)
    try:
        data = json.loads(antwort)
    except Exception:
        data = {"raw": antwort}
    projekt.system_classification = data
    projekt.save()
    return data


def check_anlage1(project_id: int) -> dict[str, Any]:
    """Prüft Anlage1 mittels LLM."""
    projekt = BVProject.objects.get(pk=project_id)
    texts = _read_anlagen(projekt)
    text = texts.get("anlage1", "")
    prompt = "Prüfe die folgende Anlage 1 und gib ein JSON-Resultat zur Konformität aus:\n" + text
    antwort = query_llm(prompt)
    try:
        data = json.loads(antwort)
    except Exception:
        data = {"raw": antwort}
    projekt.anlage1_check = data
    projekt.save()
    return data


def generate_gutachten(project_id: int) -> BVProjectFile:
    """Erstellt ein Gutachten als DOCX-Datei."""
    from docx import Document

    projekt = BVProject.objects.get(pk=project_id)
    texts = _read_anlagen(projekt)
    prompt = (
        "Erstelle ein Gutachten auf Basis der folgenden Dokumente. Gib nur den reinen Text zurück:\n\n"
        + "\n\n".join(texts.values())
    )
    text = query_llm(prompt)

    doc = Document()
    for para in text.splitlines():
        doc.add_paragraph(para)

    out_dir = Path(settings.MEDIA_ROOT) / "bvprojects" / str(projekt.pk)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_path = out_dir / "gutachten.docx"
    doc.save(doc_path)

    with doc_path.open("rb") as f:
        pf = BVProjectFile.objects.create(
            project=projekt, category="gutachten", file=File(f, name=doc_path.name)
        )
    return pf

