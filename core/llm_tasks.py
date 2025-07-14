"""LLM-gest\xfctzte Aufgaben f\xfcr BV-Projekte."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django_q.tasks import async_task

from .models import (
    BVProject,
    BVProjectFile,
    Prompt,
    LLMConfig,
    Anlage1Config,
    Anlage1Question,
    Anlage2Function,
    Anlage2SubQuestion,
    Anlage2FunctionResult,
    Anlage2Config,
    Anlage4Config,
    Anlage4ParserConfig,
    ProjectStatus,
    SoftwareKnowledge,
    Gutachten,
)
from .text_parser import parse_anlage2_text
from .llm_utils import query_llm, query_llm_with_images
from .docx_utils import (
    extract_text,
    _normalize_function_name,
    extract_images,
    get_docx_page_count,
    get_pdf_page_count,
)
from .parser_manager import parser_manager
from .anlage4_parser import parse_anlage4, parse_anlage4_dual
from docx import Document

logger = logging.getLogger(__name__)
parser_logger = logging.getLogger("parser_debug")
anlage1_logger = logging.getLogger("anlage1_debug")
anlage2_logger = logging.getLogger("anlage2_debug")
anlage3_logger = logging.getLogger("anlage3_debug")
anlage4_logger = logging.getLogger("anlage4_debug")
anlage5_logger = logging.getLogger("anlage5_debug")

ANLAGE1_QUESTIONS = [
    "Frage 1: Extrahiere alle Unternehmen als Liste.",
    "Frage 2: Extrahiere alle Fachbereiche als Liste.",
    "Frage 3: Liste alle Hersteller und Produktnamen auf.",
    "Frage 4: Lege den Textblock als question4_raw ab.",
    "Frage 5: Fasse den Zweck des Systems in einem Satz.",
    "Frage 6: Extrahiere Web-URLs.",
    "Frage 7: Extrahiere ersetzte Systeme.",
    "Frage 8: Extrahiere Legacy-Funktionen.",
    "Frage 9: Lege den Text als question9_raw ab.",
]

# Vorlage für die Bewertung einzelner Antworten.
_ANLAGE1_EVAL = (
    "Bewerte die Antwort auf Frage {num}. Mögliche Status: 'ok', 'unklar',"
    " 'unvollständig'. Gib ein JSON mit den Schlüsseln 'status',"
    " 'hinweis' und optional 'vorschlag' zurück.\n\nFrage: {question}\nAntwort: {answer}"
)

_ANLAGE1_INTRO = "System: Du bist ein juristisch-technischer Prüf-Assistent für Systembeschreibungen.\n\n"
_ANLAGE1_IT = "IT-Landschaft: Fasse den Abschnitt zusammen, der die Einbettung in die IT-Landschaft beschreibt.\n"
_ANLAGE1_SUFFIX = (
    "Konsistenzprüfung und Stichworte. Gib ein JSON im vorgegebenen Schema zurück.\n\n"
)


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


def _clean_text(text: str) -> str:
    """Bereinigt Sonderzeichen vor dem Parsen."""
    text = text.replace("\\n", " ")
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = text.replace("\u00b6", " ")
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def parse_anlage1_questions(
    text_content: str,
) -> dict[str, dict[str, str | None]] | None:
    """Sucht die Texte der Anlage-1-Fragen und extrahiert die Antworten."""
    anlage1_logger.debug(
        "parse_anlage1_questions: Aufruf mit text_content=%r",
        text_content[:200] if text_content else None,
    )
    if not text_content:
        anlage1_logger.debug("parse_anlage1_questions: Kein Text übergeben.")
        return None

    text_content = _clean_text(text_content)

    cfg = Anlage1Config.objects.first()
    questions_all = list(
        Anlage1Question.objects.prefetch_related("variants").order_by("num")
    )
    questions = []
    for q in questions_all:
        enabled = q.parser_enabled
        if cfg:
            enabled = enabled and getattr(cfg, f"enable_q{q.num}", True)
        if enabled:
            questions.append(q)
    if not questions:
        anlage1_logger.debug("parse_anlage1_questions: Keine aktiven Fragen vorhanden.")
        return None

    matches: list[tuple[int, int, int, str]] = []
    for q in questions:
        best: tuple[int, int, str] | None = None
        variants = [q.text] + [v.text for v in q.variants.all()]
        for var in variants:
            clean_var = _clean_text(var)
            m_start = re.match(r"Frage\s+\d+(?:\.\d+)?[:.]?\s*(.*)", clean_var)
            if m_start:
                rest = m_start.group(1)
                pattern = re.compile(
                    r"Frage\s+\d+(?:\.\d+)?[:.]?\s*" + re.escape(_clean_text(rest))
                )
            else:
                pattern = re.compile(re.escape(clean_var))
            m = pattern.search(text_content)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), m.end(), m.group(0))
        if best:
            matches.append((best[0], best[1], q.num, best[2]))
            anlage1_logger.debug(
                "parse_anlage1_questions: Frage %s gefunden an Position %d",
                q.num,
                best[0],
            )

    if not matches:
        anlage1_logger.debug("parse_anlage1_questions: Keine Fragen im Text gefunden.")
        return None

    matches.sort(key=lambda x: x[0])
    parsed: dict[str, dict[str, str | None]] = {}
    for idx, (start, end, num, matched_text) in enumerate(matches):
        next_start = (
            matches[idx + 1][0] if idx + 1 < len(matches) else len(text_content)
        )
        ans = text_content[end:next_start].replace("\u00b6", "").strip() or None
        found = re.search(r"Frage\s+(\d+(?:\.\d+)?)", matched_text)
        found_num = found.group(1) if found else None
        parsed[str(num)] = {"answer": ans, "found_num": found_num}
        anlage1_logger.debug(
            "parse_anlage1_questions: Antwort f\xfcr Frage %s: %r",
            num,
            parsed[str(num)]["answer"],
        )

    anlage1_logger.debug(
        "parse_anlage1_questions: Ergebnis: %r",
        parsed if parsed else None,
    )
    return parsed if parsed else None


def _parse_anlage2(text_content: str, project_prompt: str | None = None) -> list[str] | None:
    """Extrahiert Funktionslisten aus Anlage 2."""
    if not text_content:
        return None
    text = text_content.replace("\u00b6", "\n")
    parser_logger.debug("Starte Parsing für Anlage 2. Rohtext wird geloggt.")
    parser_logger.debug(
        f"--- ANFANG ROH-TEXT ANLAGE 2 ---\n{text}\n--- ENDE ROH-TEXT ANLAGE 2 ---"
    )
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    table_like = any(
        ("|" in line and line.count("|") >= 1) or "\t" in line for line in lines
    )
    if table_like:
        base_obj = Prompt.objects.filter(name="anlage2_table").first()
        prompt_text = (
            base_obj.text
            if base_obj
            else "Extrahiere die Funktionsnamen aus der folgenden Tabelle als JSON-Liste:\n\n"
        ) + text_content
        prompt_obj = Prompt(
            name="tmp", text=prompt_text, role=base_obj.role if base_obj else None
        )
        reply = query_llm(
            prompt_obj,
            {},
            model_name=None,
            model_type="anlagen",
            project_prompt=project_prompt,
        )
        try:
            data = json.loads(reply)
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:  # noqa: BLE001
            anlage2_logger.warning("_parse_anlage2: LLM Antwort kein JSON: %s", reply)
        return None

    bullet_re = re.compile(r"^(?:[-*]|\d+[.)]|[a-z]\))\s*(.+)$", re.I)
    functions: list[str] = []
    capture = False
    for line in lines:
        lower = line.lower()
        if not capture and "funktion" in lower and "?" in line:
            capture = True
            continue
        m = bullet_re.match(line)
        if capture and m:
            functions.append(m.group(1).strip())
            continue
        if capture and not m:
            break
        if not capture and m:
            functions.append(m.group(1).strip())
    return functions or None


def run_anlage2_analysis(project_file: BVProjectFile) -> list[dict[str, object]]:
    """Parst eine Anlage 2-Datei anhand der Konfiguration.

    Das Ergebnis wird als JSON-String im Feld ``analysis_json`` gespeichert,
    damit die originale Struktur unverändert erhalten bleibt.
    """

    anlage2_logger.debug("Starte run_anlage2_analysis für Datei %s", project_file.pk)

    cfg = Anlage2Config.get_instance()
    mode = cfg.parser_mode

    if mode == "table_only":
        analysis_result = parse_anlage2_table(Path(project_file.upload.path))
    elif mode == "text_only":
        parser_logger.debug(
            "Textinhalt vor Text-Parser:\n%s",
            project_file.text_content,
        )
        analysis_result = parse_anlage2_text(project_file.text_content)
    else:
        analysis_result = parser_manager.parse_anlage2(project_file)

    project_file.analysis_json = json.dumps(analysis_result, ensure_ascii=False)
    project_file.save(update_fields=["analysis_json"])

    # Dokumentergebnisse in Anlage2FunctionResult speichern
    for row in analysis_result or []:
        name = row.get("funktion")
        if not name:
            continue
        try:
            func = Anlage2Function.objects.get(name=name)
        except Anlage2Function.DoesNotExist:
            continue
        res, _ = Anlage2FunctionResult.objects.update_or_create(
            projekt=project_file.projekt,
            funktion=func,
            defaults={"doc_result": row},
        )

        doc_val = None
        col = row.get("technisch_verfuegbar")
        if isinstance(col, dict):
            doc_val = col.get("value")
        elif isinstance(col, bool):
            doc_val = col

        ai_val = None
        if isinstance(res.ai_result, dict):
            ai_val = res.ai_result.get("technisch_verfuegbar")

        res.is_negotiable = (
            doc_val is not None and ai_val is not None and doc_val == ai_val
        )
        res.doc_result = row
        res.save(update_fields=["doc_result", "is_negotiable"])

    return analysis_result


def analyse_anlage2(projekt_id: int, model_name: str | None = None) -> dict:
    """Analysiert Anlage 2 im Kontext der Systembeschreibung."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage2 = projekt.anlagen.get(anlage_nr=2)
    except (
        BVProjectFile.DoesNotExist
    ) as exc:  # pragma: no cover - sollte selten passieren
        raise ValueError("Anlage 2 fehlt") from exc

    try:
        table_data = parser_manager.parse_anlage2(anlage2)
    except ValueError as exc:  # pragma: no cover - Fehlkonfiguration
        parser_logger.error("Fehler im Parser: %s", exc)
        table_data = []
    table_names = [row["funktion"] for row in table_data]
    anlage_funcs = _parse_anlage2(anlage2.text_content, projekt.project_prompt) or []

    missing = [f for f in anlage_funcs if f not in table_names]
    additional = [f for f in table_names if f not in anlage_funcs]

    result = {
        "functions": table_data,
        "anlage2_functions": anlage_funcs,
        "missing": missing,
        "additional": additional,
    }

    result = _add_editable_flags(result)
    anlage2.analysis_json = result
    anlage2.save(update_fields=["analysis_json"])
    return result


def classify_system(projekt_id: int, model_name: str | None = None) -> dict:
    """Klassifiziert das System eines Projekts und speichert das Ergebnis."""
    projekt = BVProject.objects.get(pk=projekt_id)
    base_obj = Prompt.objects.filter(name="classify_system").first()
    prefix = (
        base_obj.text
        if base_obj
        else "Bitte klassifiziere das folgende Softwaresystem. Gib ein JSON mit den Schl\xfcsseln 'kategorie' und 'begruendung' zur\xfcck.\n\n"
    )
    prompt_text = prefix + _collect_text(projekt)
    prompt_obj = Prompt(
        name="tmp", text=prompt_text, role=base_obj.role if base_obj else None
    )
    reply = query_llm(
        prompt_obj,
        {},
        model_name=model_name,
        model_type="default",
        project_prompt=projekt.project_prompt,
    )
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        logger.warning("LLM Antwort kein JSON: %s", reply)
        data = {"raw": reply}
    data = _add_editable_flags(data)
    projekt.classification_json = data
    projekt.status = ProjectStatus.objects.get(key="CLASSIFIED")
    projekt.save(update_fields=["classification_json", "status"])
    return data


def generate_gutachten(
    projekt_id: int, text: str | None = None, model_name: str | None = None
) -> Path:
    """Erstellt ein Gutachten-Dokument mithilfe eines LLM."""
    projekt = BVProject.objects.get(pk=projekt_id)
    if text is None:
        base_obj = Prompt.objects.filter(name="generate_gutachten").first()
        prefix = (
            base_obj.text
            if base_obj
            else "Erstelle ein technisches Gutachten basierend auf deinem Wissen:\n\n"
        )
        prompt_text = prefix + projekt.software_string
        prompt_obj = Prompt(
            name="tmp", text=prompt_text, role=base_obj.role if base_obj else None
        )
        text = query_llm(
            prompt_obj,
            {},
            model_name=model_name,
            model_type="gutachten",
            project_prompt=projekt.project_prompt,
        )
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
    try:
        projekt.status = ProjectStatus.objects.get(key="GUTACHTEN_OK")
    except ProjectStatus.DoesNotExist:
        pass
    projekt.save(update_fields=["gutachten_file", "status"])
    return path


def worker_generate_gutachten(
    project_id: int, software_type_id: int | None = None
) -> str:
    """Erzeugt im Hintergrund ein Gutachten.

    Ist ``software_type_id`` angegeben, wird ein Gutachten f\u00fcr die
    entsprechende Software erstellt. Andernfalls erzeugt die Funktion ein
    Gesamtgutachten f\u00fcr das Projekt.
    """

    logger.info("worker_generate_gutachten gestartet für Projekt %s", project_id)
    try:
        projekt = BVProject.objects.get(pk=project_id)
    except BVProject.DoesNotExist:
        logger.warning(
            "Task f\u00fcr Gutachten-Erstellung (Projekt-ID: %s) gestartet, "
            "aber das Projekt existiert nicht mehr. Breche ab.",
            project_id,
        )
        return ""
    model = LLMConfig.get_default("gutachten")

    base_obj = Prompt.objects.filter(name="generate_gutachten").first()
    prefix = (
        base_obj.text
        if base_obj
        else "Erstelle ein technisches Gutachten basierend auf deinem Wissen:\n\n"
    )

    knowledge = None
    if software_type_id:
        knowledge = SoftwareKnowledge.objects.get(pk=software_type_id)
        target = knowledge.software_name
    else:
        target = projekt.software_string

    prompt_obj = Prompt(
        name="tmp", text=prefix + target, role=base_obj.role if base_obj else None
    )
    text = query_llm(
        prompt_obj,
        {},
        model_name=model,
        model_type="gutachten",
        project_prompt=projekt.project_prompt,
    )
    path = generate_gutachten(projekt.id, text, model_name=model)

    if knowledge:
        gutachten, _ = Gutachten.objects.get_or_create(software_knowledge=knowledge)
        gutachten.text = text
        gutachten.save(update_fields=["text"])

    logger.info("worker_generate_gutachten beendet für Projekt %s", project_id)
    return str(path)


def analyse_anlage3(projekt_id: int, model_name: str | None = None) -> dict:
    """Analysiert die dritte Anlage hinsichtlich der Seitenzahl.

    Erkennt automatisch ein kleines Dokument (eine Seite oder weniger) und
    markiert die Anlage als verhandlungsf\xe4hig. Bei mehr Seiten wird ein
    manueller Check erforderlich.

    :param projekt_id: ID des Projekts
    :param model_name: Optionaler Name des LLM-Modells (wird aktuell
        nicht verwendet)
    """

    anlage3_logger.debug(
        "Starte analyse_anlage3 für Projekt %s mit Modell %s",
        projekt_id,
        model_name,
    )
    projekt = BVProject.objects.get(pk=projekt_id)
    anlagen = list(projekt.anlagen.filter(anlage_nr=3))
    if not anlagen:
        raise ValueError("Anlage 3 fehlt")

    result: dict | None = None
    for anlage in anlagen:
        anlage3_logger.debug("Prüfe Datei %s", anlage.upload.path)
        path = Path(anlage.upload.path)
        if path.suffix.lower() == ".pdf":
            pages = get_pdf_page_count(path)
        else:
            pages = get_docx_page_count(path)
        anlage3_logger.debug("Seitenzahl der Datei: %s", pages)

        if pages <= 1:
            data = {"task": "analyse_anlage3", "auto_ok": True, "pages": pages}
            verhandlungsfaehig = True
        else:
            data = {
                "task": "analyse_anlage3",
                "manual_required": True,
                "pages": pages,
            }
            verhandlungsfaehig = False

        anlage3_logger.debug("Analyseergebnis: %s", data)

        anlage.analysis_json = data
        if hasattr(anlage, "verhandlungsfaehig"):
            anlage.verhandlungsfaehig = verhandlungsfaehig
            anlage.save(update_fields=["analysis_json", "verhandlungsfaehig"])
        else:  # pragma: no cover - fallback f\xfcr fehlendes Feld
            anlage.save(update_fields=["analysis_json"])

        if result is None:
            result = data

    anlage3_logger.debug("Analyse abgeschlossen mit Ergebnis: %s", result)
    return result or {}


def _read_pdf_images(path: Path) -> list[bytes]:
    """Liest die Bytes einer PDF-Datei ein."""
    try:
        with open(path, "rb") as fh:
            return [fh.read()]
    except Exception as exc:  # pragma: no cover - ungültige Datei
        anlage3_logger.error("Fehler beim Lesen des PDF %s: %s", path, exc)
        return []


def check_anlage3_vision(projekt_id: int, model_name: str | None = None) -> dict:
    """Prüft Anlage 3 anhand der enthaltenen Bilder."""

    projekt = BVProject.objects.get(pk=projekt_id)
    anlagen = projekt.anlagen.filter(anlage_nr=3)
    if not anlagen:
        raise ValueError("Anlage 3 fehlt")

    prompt_obj = Prompt.objects.filter(name="check_anlage3_vision").first()
    prompt = (
        prompt_obj.text
        if prompt_obj
        else "Prüfe die folgende Anlage auf Basis der Bilder. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n"
    )
    model = model_name or LLMConfig.get_default("vision")
    result: dict | None = None
    for anlage in anlagen:
        path = Path(anlage.upload.path)
        if path.suffix.lower() == ".docx":
            images = extract_images(path)
        elif path.suffix.lower() == ".pdf":
            images = _read_pdf_images(path)
        else:
            try:
                with open(path, "rb") as fh:
                    images = [fh.read()]
            except Exception as exc:  # pragma: no cover - ungültige Datei
                anlage3_logger.error("Fehler beim Lesen von %s: %s", path, exc)
                images = []

        reply = query_llm_with_images(
            prompt,
            images,
            model,
            project_prompt=projekt.project_prompt,
        )
        try:
            data = json.loads(reply)
        except Exception:  # noqa: BLE001
            data = {"raw": reply}

        data = _add_editable_flags(data)
        anlage.analysis_json = data
        anlage.save(update_fields=["analysis_json"])
        if result is None:
            result = data

    return result or {}


def _check_anlage(projekt_id: int, nr: int, model_name: str | None = None) -> dict:
    """Pr\xfcft eine Anlage und speichert das Ergebnis."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=nr)
    except (
        BVProjectFile.DoesNotExist
    ) as exc:  # pragma: no cover - Test deckt Abwesenheit nicht ab
        raise ValueError(f"Anlage {nr} fehlt") from exc

    base_obj = Prompt.objects.filter(name=f"check_anlage{nr}").first()
    prefix = (
        base_obj.text
        if base_obj
        else "Pr\xfcfe die folgende Anlage auf Vollst\xe4ndigkeit. Gib ein JSON mit 'ok' und 'hinweis' zur\xfcck:\n\n"
    )
    prompt_text = prefix + anlage.text_content
    prompt_obj = Prompt(
        name="tmp", text=prompt_text, role=base_obj.role if base_obj else None
    )

    reply = query_llm(
        prompt_obj,
        {},
        model_name=model_name,
        model_type="anlagen",
        project_prompt=projekt.project_prompt,
    )
    try:
        data = json.loads(reply)
    except Exception as _:
        data = {"raw": reply}

    data = _add_editable_flags(data)
    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    anlage4_logger.debug("Gesamtergebnis gespeichert: %s", data)
    return data


def check_anlage1(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xfcft die erste Anlage nach neuem Schema."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=1)
    except (
        BVProjectFile.DoesNotExist
    ) as exc:  # pragma: no cover - sollte selten passieren
        raise ValueError("Anlage 1 fehlt") from exc

    question_objs = list(Anlage1Question.objects.order_by("num"))
    if not question_objs:
        question_objs = [
            Anlage1Question(
                num=i,
                text=t,
                enabled=True,
                parser_enabled=True,
                llm_enabled=True,
            )
            for i, t in enumerate(ANLAGE1_QUESTIONS, start=1)
        ]

    cfg = Anlage1Config.objects.first()

    # Ermittele separat, welche Fragen für das LLM aktiviert sind.
    def _llm_enabled(q: Anlage1Question) -> bool:
        enabled = q.llm_enabled
        if cfg:
            enabled = enabled and getattr(cfg, f"enable_q{q.num}", True)
        return enabled

    llm_questions = [q for q in question_objs if _llm_enabled(q)]

    # Debug-Log für den zu parsenden Text
    anlage1_logger.debug(
        "check_anlage1: Zu parsende Anlage1 text_content (ersten 500 Zeichen): %r",
        anlage.text_content[:500] if anlage.text_content else None,
    )

    parsed = parse_anlage1_questions(anlage.text_content)
    answers: dict[str, str | list | None]
    found_nums: dict[str, str | None] = {}
    data: dict

    if parsed:
        anlage1_logger.info("Strukturiertes Dokument erkannt. Parser wird verwendet.")
        answers = {
            str(q.num): parsed.get(str(q.num), {}).get("answer") for q in question_objs
        }
        found_nums = {
            str(q.num): parsed.get(str(q.num), {}).get("found_num")
            for q in question_objs
        }
        data = {"task": "check_anlage1", "source": "parser"}
    else:
        parts = [_ANLAGE1_INTRO]
        for q in llm_questions:
            parts.append(get_prompt(f"anlage1_q{q.num}", q.text) + "\n")
        insert_at = 3 if len(parts) > 2 else len(parts)
        parts.insert(insert_at, _ANLAGE1_IT)
        parts.append(_ANLAGE1_SUFFIX)
        prefix = "".join(parts)
        base_obj = Prompt.objects.filter(
            name=f"anlage1_q{llm_questions[0].num}"
        ).first()
        prompt_text = prefix + anlage.text_content
        prompt_obj = Prompt(
            name="tmp", text=prompt_text, role=base_obj.role if base_obj else None
        )

        anlage1_logger.debug(
            "check_anlage1: Sende Prompt an LLM (ersten 500 Zeichen): %r",
            prompt_text[:500],
        )
        reply = query_llm(
            prompt_obj,
            {},
            model_name=model_name,
            model_type="anlagen",
            project_prompt=projekt.project_prompt,
        )
        anlage1_logger.debug(
            "check_anlage1: LLM Antwort (ersten 500 Zeichen): %r", reply[:500]
        )
        try:
            data = json.loads(reply)
        except Exception:  # noqa: BLE001
            data = {"raw": reply}
        if data.get("task") != "check_anlage1":
            data = {"task": "check_anlage1"}

        def _val(key: str):
            if isinstance(data.get(key), dict) and "value" in data[key]:
                return data[key]["value"]
            return data.get(key)

        base_answers = {
            "1": _val("companies"),
            "2": _val("departments"),
            "3": _val("vendors"),
            "4": _val("question4_raw"),
            "5": _val("purpose_summary"),
            "6": _val("documentation_links"),
            "7": _val("replaced_systems"),
            "8": _val("legacy_functions"),
            "9": _val("question9_raw"),
        }
        answers = {str(q.num): base_answers.get(str(q.num)) for q in question_objs}
        data["questions"] = {}

    questions: dict[str, dict] = {}
    for q in question_objs:
        key = str(q.num)
        ans = answers.get(key)
        if ans in (None, "", []):
            ans = "leer"
        q_data = {"answer": ans, "status": None, "hinweis": "", "vorschlag": ""}
        if _llm_enabled(q):
            prompt_text = _ANLAGE1_EVAL.format(num=q.num, question=q.text, answer=ans)
            prompt_obj = Prompt(name="tmp", text=prompt_text)
            anlage1_logger.debug(
                "check_anlage1: Sende Bewertungs-Prompt an LLM (Frage %s): %r",
                q.num,
                prompt_text,
            )
            try:
                reply = query_llm(
                    prompt_obj,
                    {},
                    model_name=model_name,
                    model_type="anlagen",
                    project_prompt=projekt.project_prompt,
                )
                anlage1_logger.debug(
                    "check_anlage1: Bewertungs-LLM Antwort (Frage %s): %r", q.num, reply
                )
                fb = json.loads(reply)
            except Exception:  # noqa: BLE001
                fb = {"status": "unklar", "hinweis": "LLM Fehler"}
            q_data["status"] = fb.get("status")
            q_data["hinweis"] = fb.get("hinweis", "")
            q_data["vorschlag"] = fb.get("vorschlag", "")
        found_num = found_nums.get(key)
        if found_num and str(found_num) != key:
            q_data["hinweis"] = (
                f"Entspricht nicht den Frage Anforderungen der IT Rahmen 2.0: Frage {found_num} statt {q.num}."
            )
        questions[key] = q_data

    data["questions"] = questions

    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    return data


def check_anlage2(projekt_id: int, model_name: str | None = None) -> dict:
    """Prüft die zweite Anlage.

    Für jede Funktion aus Anlage 2 wird geprüft, ob sie in der Tabelle der Anlage vorhanden ist.
    Falls ja, werden die Werte direkt übernommen (Quelle: parser).
    Falls nein, wird ein LLM befragt (Quelle: llm).
    Zusätzlich werden für jede Subfrage (anlage2subquestion_set) ebenfalls LLM-Abfragen durchgeführt.
    Das Ergebnis wird als JSON im Analysefeld der Anlage gespeichert.
    """
    projekt = BVProject.objects.get(pk=projekt_id)
    anlage2_logger.debug("Starte check_anlage2 f\u00fcr Projekt %s", projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=2)
    except (
        BVProjectFile.DoesNotExist
    ) as exc:  # pragma: no cover - sollte selten passieren
        raise ValueError("Anlage 2 fehlt") from exc

    anlage2_logger.debug("Anlage 2 Pfad: %s", anlage.upload.path)
    parser_error: str | None = None
    try:
        table = parser_manager.parse_anlage2(anlage)
    except ValueError as exc:  # pragma: no cover - Fehlkonfiguration
        parser_error = str(exc)
        parser_logger.error("Fehler im Parser: %s", exc)
        anlage.analysis_json = {"parser_error": parser_error}
        anlage.save(update_fields=["analysis_json"])
        table = []
    anlage2_logger.debug("Anlage2 table data: %r", table)
    text = _collect_text(projekt)
    anlage2_logger.debug("Collected project text: %r", text)
    prompt_base = get_prompt(
        "check_anlage2_function",
        (
            "Pr\u00fcfe anhand des folgenden Textes die Funktion. "
            "Gib ein JSON mit den Schl\u00fcsseln 'technisch_verfuegbar' "
            "und 'ki_beteiligung' zur\u00fcck.\n\n"
        ),
    )

    results: list[dict] = []
    for func in Anlage2Function.objects.prefetch_related(
        "anlage2subquestion_set"
    ).order_by("name"):
        anlage2_logger.debug("Pr\u00fcfe Funktion '%s'", func.name)
        norm = _normalize_function_name(func.name)
        row = next(
            (r for r in table if _normalize_function_name(r["funktion"]) == norm),
            None,
        )
        anlage2_logger.debug("Tabellenzeile: %s", row)
        if row is None:
            parser_logger.debug("Parser fand Funktion '%s' nicht", func.name)

        def _val(item, key):
            value = item.get(key)
            if isinstance(value, dict) and "value" in value:
                return value["value"]
            return value

        if (
            row
            and _val(row, "technisch_verfuegbar") is not None
            and _val(row, "ki_beteiligung") is not None
        ):
            vals = {
                "technisch_verfuegbar": row.get("technisch_verfuegbar"),
                "ki_beteiligung": row.get("ki_beteiligung"),
            }
            source = "parser"
            raw = row
        else:
            # Sonst LLM befragen
            prompt_text = f"{prompt_base}Funktion: {func.name}\n\n{text}"
            anlage2_logger.debug(
                "LLM Prompt f\u00fcr Funktion '%s': %s", func.name, prompt_text
            )
            prompt_obj = Prompt(name="tmp", text=prompt_text)
            reply = query_llm(
                prompt_obj,
                {},
                model_name=model_name,
                model_type="anlagen",
                project_prompt=projekt.project_prompt,
            )
            anlage2_logger.debug(
                "LLM Antwort f\u00fcr Funktion '%s': %s", func.name, reply
            )
            try:
                raw = json.loads(reply)
            except Exception:  # noqa: BLE001
                raw = {"raw": reply}
            vals = {
                "technisch_verfuegbar": raw.get("technisch_verfuegbar"),
                "ki_beteiligung": raw.get("ki_beteiligung"),
            }
            source = "llm"
        Anlage2FunctionResult.objects.update_or_create(
            projekt=projekt,
            funktion=func,
            defaults={
                "technisch_verfuegbar": _val(vals, "technisch_verfuegbar"),
                "ki_beteiligung": _val(vals, "ki_beteiligung"),
                "raw_json": raw,
                "source": source,
            },
        )
        anlage2_logger.debug("Ergebnis Funktion '%s': %s", func.name, vals)
        entry = {"funktion": func.name, **vals, "source": source}
        sub_list: list[dict] = []
        # Für jede Subfrage ebenfalls LLM befragen
        for sub in func.anlage2subquestion_set.all().order_by("id"):
            sub_name = f"{func.name}: {sub.frage_text}"
            sub_row = next(
                (
                    r
                    for r in table
                    if _normalize_function_name(r["funktion"])
                    == _normalize_function_name(sub_name)
                ),
                None,
            )
            if sub_row is None:
                parser_logger.debug("Parser fand Unterfrage '%s' nicht", sub_name)
            prompt_text = f"{prompt_base}Funktion: {sub.frage_text}\n\n{text}"
            anlage2_logger.debug(
                "LLM Prompt f\u00fcr Subfrage '%s': %s", sub.frage_text, prompt_text
            )
            prompt_obj = Prompt(name="tmp", text=prompt_text)
            reply = query_llm(
                prompt_obj,
                {},
                model_name=model_name,
                model_type="anlagen",
                project_prompt=projekt.project_prompt,
            )
            anlage2_logger.debug(
                "LLM Antwort f\u00fcr Subfrage '%s': %s", sub.frage_text, reply
            )
            try:
                s_raw = json.loads(reply)
            except Exception:  # noqa: BLE001
                s_raw = {"raw": reply}
            sub_list.append(
                {
                    "frage_text": sub.frage_text,
                    "technisch_verfuegbar": s_raw.get("technisch_verfuegbar"),
                    "ki_beteiligung": s_raw.get("ki_beteiligung"),
                    "source": "llm",
                }
            )
        if sub_list:
            entry["subquestions"] = sub_list
        results.append(entry)

    data = {"task": "check_anlage2", "functions": results}
    if parser_error:
        data["parser_error"] = parser_error
    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    anlage2_logger.debug("check_anlage2 Ergebnis: %s", data)
    return data


def analyse_anlage4(projekt_id: int, model_name: str | None = None) -> dict:
    """Analysiert die vierte Anlage."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=4)
    except BVProjectFile.DoesNotExist as exc:  # pragma: no cover - selten
        raise ValueError("Anlage 4 fehlt") from exc

    cfg = anlage.anlage4_config or Anlage4Config.objects.first()
    parser_cfg = anlage.anlage4_parser_config or Anlage4ParserConfig.objects.first()
    if parser_cfg and (parser_cfg.delimiter_phrase or parser_cfg.table_columns):
        anlage4_logger.debug(
            "analyse_anlage4: benutze Dual-Parser mit config %s", parser_cfg.pk
        )
        auswertungen = parse_anlage4_dual(anlage)
    else:
        anlage4_logger.debug("analyse_anlage4: benutze Standard-Parser")
        auswertungen = parse_anlage4(anlage, cfg)
    anlage4_logger.debug("Gefundene Auswertungen: %s", auswertungen)

    template = (
        cfg.prompt_template
        or (
            "Du bist ein Experte f\u00fcr deutsches Betriebsverfassungsrecht und Datenschutz "
            "mit einem besonderen Fokus auf die Verhinderung von Leistungs- und Verhaltenskontrolle bei Mitarbeitern.\n\n"
            "Analysiere die folgende administrative Auswertung. Deine Aufgabe ist es, die Plausibilit\xe4t zu bewerten, dass diese Auswertung rein administrativen Zwecken dient und nicht zur \xdcberwachung von Mitarbeitern missbraucht werden kann.\n\n"
            "Ber\u00fccksichtige bei deiner Analyse die Kombination aus dem Namen der Auswertung, den anwendenden Gesellschaften und den zust\u00e4ndigen Fachbereichen.\n\n"
            "Gib deine finale Bewertung ausschlie\xdflich als valides JSON-Objekt mit den Sch\xfcsseln 'plausibilitaet', 'score' (0.0-1.0) und 'begruendung' zur\u00fcck:\n{json}"
        )
    )

    items: list[dict] = []
    for idx, entry in enumerate(auswertungen):
        if isinstance(entry, dict):
            structured = entry
        else:
            structured = {"name_der_auswertung": entry}
        plausi_data = {**structured, "kontext": projekt.title}
        data_json = json.dumps(plausi_data, ensure_ascii=False)
        try:
            prompt_text = template.format(json=data_json, json_data=data_json)
        except KeyError as exc:  # pragma: no cover - falsches Template
            raise KeyError(f"Platzhalter fehlt im Prompt-Template: {exc}") from exc
        anlage4_logger.debug("A4 Sync Prompt #%s: %s", idx, prompt_text)
        prompt_obj = Prompt(name="tmp", text=prompt_text)
        reply = query_llm(
            prompt_obj,
            {},
            model_name=model_name,
            model_type="anlagen",
            project_prompt=projekt.project_prompt,
        )
        anlage4_logger.debug("A4 Sync Raw Response #%s: %s", idx, reply)
        if "```json" in reply:
            reply = reply.split("```json", 1)[1].split("```")[0]
        try:
            result = json.loads(reply)
        except Exception:  # noqa: BLE001
            result = {"raw": reply}
        anlage4_logger.debug("A4 Sync Parsed JSON #%s: %s", idx, result)
        items.append({"structured": structured, "plausibility": result})

    data = {"task": "analyse_anlage4", "items": items}
    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    anlage4_logger.debug("A4 Sync Gesamtdaten: %s", data)
    return data


def worker_anlage4_evaluate(
    item_text: str, project_file_id: int, index: int, model_name: str | None = None
) -> dict:
    """Bewertet eine Auswertung aus Anlage 4 im Hintergrund."""

    anlage4_logger.info(
        "worker_anlage4_evaluate gestartet f\u00fcr Datei %s Index %s",
        project_file_id,
        index,
    )
    anlage4_logger.debug("Pr\u00fcfe Auswertung #%s: %s", index, item_text)

    pf = BVProjectFile.objects.get(pk=project_file_id)
    cfg = pf.anlage4_config or Anlage4Config.objects.first()
    template = (
        cfg.prompt_template
        or (
            "Du bist ein Experte f\u00fcr deutsches Betriebsverfassungsrecht und Datenschutz "
            "mit einem besonderen Fokus auf die Verhinderung von Leistungs- und Verhaltenskontrolle bei Mitarbeitern.\n\n"
            "Analysiere die folgende administrative Auswertung. Deine Aufgabe ist es, die Plausibilit\xe4t zu bewerten, dass diese Auswertung rein administrativen Zwecken dient und nicht zur \xdcberwachung von Mitarbeitern missbraucht werden kann.\n\n"
            "Ber\u00fccksichtige bei deiner Analyse die Kombination aus dem Namen der Auswertung, den anwendenden Gesellschaften und den zust\u00e4ndigen Fachbereichen.\n\n"
            "Gib deine finale Bewertung ausschlie\xdflich als valides JSON-Objekt mit den Sch\xfcsseln 'plausibilitaet', 'score' (0.0-1.0) und 'begruendung' zur\u00fcck:\n{json}"
        )
    )
    structured = {"name": item_text, "kontext": pf.projekt.title}
    data_json = json.dumps(structured, ensure_ascii=False)
    try:
        prompt_text = template.format(json=data_json, json_data=data_json)
    except KeyError as exc:  # pragma: no cover - falsches Template
        raise KeyError(f"Platzhalter fehlt im Prompt-Template: {exc}") from exc
    anlage4_logger.debug("Anlage4 Prompt #%s: %s", index, prompt_text)
    prompt_obj = Prompt(name="tmp", text=prompt_text)
    reply = query_llm(
        prompt_obj,
        {},
        model_name=model_name,
        model_type="anlagen",
        project_prompt=pf.projekt.project_prompt,
    )
    anlage4_logger.debug("Anlage4 Raw Response #%s: %s", index, reply)
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        data = {"raw": reply}
    anlage4_logger.debug("Anlage4 Parsed JSON #%s: %s", index, data)
    anlage4_logger.debug("Ergebnis f\u00fcr Auswertung #%s: %s", index, data)

    analysis = pf.analysis_json or {"items": []}
    items = analysis.get("items") or []
    while len(items) <= index:
        items.append({"text": item_text, "structured": {"name_der_auswertung": item_text}})
    items[index]["structured"] = {"name_der_auswertung": item_text}
    items[index]["plausibility"] = data
    analysis["items"] = items
    pf.analysis_json = analysis
    pf.save(update_fields=["analysis_json"])
    anlage4_logger.debug("Speichere Analyse JSON: %s", analysis)
    anlage4_logger.info(
        "worker_anlage4_evaluate beendet für Datei %s Index %s",
        project_file_id,
        index,
    )
    return data



def worker_a4_plausibility(structured: dict, pf_id: int, index: int, model_name: str | None = None) -> dict:
    """Bewertet einen strukturierten Eintrag."""

    pf = BVProjectFile.objects.get(pk=pf_id)
    cfg = pf.anlage4_config or Anlage4Config.objects.first()
    template = (
        cfg.prompt_template
        or (
            "Du bist ein Experte f\u00fcr deutsches Betriebsverfassungsrecht und Datenschutz "
            "mit einem besonderen Fokus auf die Verhinderung von Leistungs- und Verhaltenskontrolle bei Mitarbeitern.\n\n"
            "Analysiere die folgende administrative Auswertung. Deine Aufgabe ist es, die Plausibilit\xe4t zu bewerten, dass diese Auswertung rein administrativen Zwecken dient und nicht zur \xdcberwachung von Mitarbeitern missbraucht werden kann.\n\n"
            "Ber\u00fccksichtige bei deiner Analyse die Kombination aus dem Namen der Auswertung, den anwendenden Gesellschaften und den zust\u00e4ndigen Fachbereichen.\n\n"
            "Gib deine finale Bewertung ausschlie\xdflich als valides JSON-Objekt mit den Sch\xfcsseln 'plausibilitaet', 'score' (0.0-1.0) und 'begruendung' zur\u00fcck:\n{json}"
        )
    )
    data_json = json.dumps(structured, ensure_ascii=False)
    try:
        prompt_text = template.format(json=data_json, json_data=data_json)
    except KeyError as exc:  # pragma: no cover - falsches Template
        raise KeyError(f"Platzhalter fehlt im Prompt-Template: {exc}") from exc
    anlage4_logger.debug("A4 Plausi Prompt #%s: %s", index, prompt_text)
    prompt_obj = Prompt(name="tmp", text=prompt_text)
    reply = query_llm(
        prompt_obj,
        {},
        model_name=model_name,
        model_type="anlagen",
        project_prompt=pf.projekt.project_prompt,
    )
    anlage4_logger.debug("A4 Plausi Raw Response #%s: %s", index, reply)
    try:
        data = json.loads(reply)
    except Exception:  # noqa: BLE001
        data = {"raw": reply}
    anlage4_logger.debug("A4 Plausi Parsed JSON #%s: %s", index, data)

    analysis = pf.analysis_json or {"items": []}
    items = analysis.get("items") or []
    while len(items) <= index:
        items.append({})
    items[index]["plausibility"] = data
    analysis["items"] = items
    pf.analysis_json = analysis
    pf.save(update_fields=["analysis_json"])
    anlage4_logger.debug("A4 Plausi gespeichertes JSON #%s: %s", index, analysis)
    return data


def analyse_anlage4_async(projekt_id: int, model_name: str | None = None) -> dict:
    """Startet die asynchrone Analyse von Anlage 4."""

    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=4)
    except BVProjectFile.DoesNotExist as exc:  # pragma: no cover - selten
        raise ValueError("Anlage 4 fehlt") from exc

    cfg = anlage.anlage4_config or Anlage4Config.objects.first()
    parser_cfg = anlage.anlage4_parser_config or Anlage4ParserConfig.objects.first()
    use_dual = parser_cfg and (parser_cfg.delimiter_phrase or parser_cfg.table_columns)
    if use_dual:
        anlage4_logger.debug(
            "analyse_anlage4_async: benutze Dual-Parser mit config %s",
            parser_cfg.pk,
        )
        auswertungen = parse_anlage4_dual(anlage)
    else:
        anlage4_logger.debug("analyse_anlage4_async: benutze Standard-Parser")
        auswertungen = parse_anlage4(anlage, cfg)
    anlage4_logger.debug("Async gefundene Auswertungen: %s", auswertungen)
    if use_dual:
        items = [{"structured": z} for z in auswertungen]
    else:
        items = [
            {"text": z, "structured": {"name_der_auswertung": z}}
            for z in auswertungen
        ]
    anlage.analysis_json = {"items": items}
    anlage.save(update_fields=["analysis_json"])
    anlage4_logger.debug("Async initiales JSON gespeichert: %s", anlage.analysis_json)

    for idx, item in enumerate(items):
        if use_dual:
            async_task(
                "core.llm_tasks.worker_a4_plausibility",
                {**item["structured"], "kontext": projekt.title},
                anlage.pk,
                idx,
                model_name,
            )
        else:
            async_task(
                "core.llm_tasks.worker_anlage4_evaluate",
                item["text"],
                anlage.pk,
                idx,
                model_name,
            )
        anlage4_logger.debug("A4 Eval Task #%s geplant", idx)

    return anlage.analysis_json


def check_anlage2_functions(
    projekt_id: int, model_name: str | None = None
) -> list[dict]:
    """Pr\xfcft alle Funktionen aus Anlage 2 einzeln."""
    projekt = BVProject.objects.get(pk=projekt_id)
    text = _collect_text(projekt)
    prompt_base = get_prompt(
        "check_anlage2_function",
        (
            "Pr\u00fcfe anhand des folgenden Textes die Funktion. "
            "Gib ein JSON mit den Schl\u00fcsseln 'technisch_verfuegbar' "
            "und 'ki_beteiligung' zur\u00fcck.\n\n"
        ),
    )
    results: list[dict] = []
    for func in Anlage2Function.objects.order_by("name"):
        prompt_text = f"{prompt_base}Funktion: {func.name}\n\n{text}"
        prompt_obj = Prompt(name="tmp", text=prompt_text)
        reply = query_llm(
            prompt_obj,
            {},
            model_name=model_name,
            model_type="anlagen",
            project_prompt=projekt.project_prompt,
        )
        try:
            data = json.loads(reply)
        except Exception:  # noqa: BLE001
            data = {"raw": reply}
        vals = {
            "technisch_verfuegbar": data.get("technisch_verfuegbar"),
            "ki_beteiligung": data.get("ki_beteiligung"),
        }
        Anlage2FunctionResult.objects.update_or_create(
            projekt=projekt,
            funktion=func,
            defaults={
                "technisch_verfuegbar": vals.get("technisch_verfuegbar"),
                "ki_beteiligung": vals.get("ki_beteiligung"),
                "raw_json": data,
                "ai_result": data,
                "source": "llm",
            },
        )
        results.append({**vals, "source": "llm", "funktion": func.name})
    pf = BVProjectFile.objects.filter(projekt_id=projekt_id, anlage_nr=2).first()
    if pf:
        pf.verification_task_id = ""
        pf.save(update_fields=["verification_task_id"])
    return results


def worker_verify_feature(
    project_id: int,
    object_type: str,
    object_id: int,
    model_name: str | None = None,
) -> dict[str, bool | str | None]:
    """Pr\u00fcft im Hintergrund das Vorhandensein einer Einzelfunktion."""

    logger.info(
        "worker_verify_feature gestartet für Projekt %s Objekt %s %s",
        project_id,
        object_type,
        object_id,
    )

    projekt = BVProject.objects.get(pk=project_id)

    gutachten_text = ""
    if projekt.gutachten_file:
        path = Path(settings.MEDIA_ROOT) / projekt.gutachten_file.name
        try:
            gutachten_text = extract_text(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gutachten konnte nicht geladen werden: %s", exc)
    context: dict[str, str] = {"gutachten": gutachten_text}

    obj_to_check = None
    lookup_key: str | None = None
    verification_prompt_key = "anlage2_feature_verification"
    justification_prompt_key = "anlage2_feature_justification"
    ai_function_name = ""

    if object_type == "function":
        obj_to_check = Anlage2Function.objects.get(pk=object_id)
        context["function_name"] = obj_to_check.name
        lookup_key = obj_to_check.name
        ai_function_name = obj_to_check.name
    elif object_type == "subquestion":
        obj_to_check = Anlage2SubQuestion.objects.get(pk=object_id)
        context["subquestion_text"] = obj_to_check.frage_text
        lookup_key = f"{obj_to_check.funktion.name}: {obj_to_check.frage_text}"
        verification_prompt_key = "anlage2_subquestion_verification"
        justification_prompt_key = "anlage2_subquestion_justification"
        ai_function_name = obj_to_check.funktion.name
    else:
        raise ValueError("invalid object_type")

    try:
        prompt_obj = Prompt.objects.get(name=verification_prompt_key)
    except Prompt.DoesNotExist:
        logger.error("Prompt '%s' nicht gefunden!", verification_prompt_key)
        prompt_obj = Prompt(
            text=(
                "Du bist ein Experte f\u00fcr IT-Systeme und Software-Architektur. "
                "Bewerte die folgende Aussage ausschlie\u00dflich basierend auf deinem "
                "allgemeinen Wissen \u00fcber die Software '{software_name}'. "
                'Antworte NUR mit "Ja", "Nein" oder "Unsicher". '
                "Aussage: Besitzt die Software '{software_name}' typischerweise "
                "die Funktion oder Eigenschaft '{function_name}'?\n\n{gutachten}"
            ),
            use_system_role=False,
        )

    software_list = projekt.software_list

    name = ai_function_name

    individual_results: list[bool | None] = []
    for software in software_list:
        context["software_name"] = software
        reply = query_llm(
            prompt_obj,
            context,
            model_name=model_name,
            model_type="anlagen",
            temperature=0.1,
            project_prompt=projekt.project_prompt,
        )
        ans = reply.strip()
        low = ans.lower()
        if low.startswith("ja"):
            individual_results.append(True)
        elif low.startswith("nein"):
            individual_results.append(False)
        else:
            individual_results.append(None)

    result = False
    if True in individual_results:
        result = True
    elif None in individual_results:
        result = None

    justification = ""
    ai_involved: bool | None = None
    ai_reason = ""
    if result:
        try:
            just_prompt_obj = Prompt.objects.get(name=justification_prompt_key)
        except Prompt.DoesNotExist:
            just_prompt_obj = Prompt(
                text=(
                    "Warum besitzt die Software '{software_name}' typischerweise die "
                    "Funktion oder Eigenschaft '{function_name}'?"
                ),
                use_system_role=False,
            )
        idx = individual_results.index(True) if True in individual_results else 0
        context["software_name"] = software_list[idx]
        justification = query_llm(
            just_prompt_obj,
            context,
            model_name=model_name,
            model_type="anlagen",
            temperature=0.1,
            project_prompt=projekt.project_prompt,
        ).strip()

        try:
            ai_check_obj = Prompt.objects.get(name="anlage2_ai_involvement_check")
        except Prompt.DoesNotExist:
            ai_check_obj = Prompt(
                text=(
                    "Antworte ausschließlich mit 'Ja' oder 'Nein'. Frage: Beinhaltet die "
                    "Funktion '{function_name}' der Software '{software_name}' typischerweise eine KI-Komponente?"
                ),
                use_system_role=False,
            )
        context["software_name"] = software_list[idx]
        ai_reply = (
            query_llm(
                ai_check_obj,
                {"software_name": context["software_name"], "function_name": name},
                model_name=model_name,
                model_type="anlagen",
                temperature=0.1,
                project_prompt=projekt.project_prompt,
            )
            .strip()
            .lower()
        )
        if ai_reply.startswith("ja"):
            ai_involved = True
        elif ai_reply.startswith("nein"):
            ai_involved = False
        else:
            ai_involved = None

        if ai_involved:
            try:
                ai_just_obj = Prompt.objects.get(
                    name="anlage2_ai_involvement_justification"
                )
            except Prompt.DoesNotExist:
                ai_just_obj = Prompt(
                    text=(
                        "Gib eine kurze Begründung, warum die Funktion '{function_name}' "
                        "der Software '{software_name}' eine KI-Komponente beinhaltet."
                    ),
                    use_system_role=False,
                )
            ai_reason = query_llm(
                ai_just_obj,
                {"software_name": context["software_name"], "function_name": name},
                model_name=model_name,
                model_type="anlagen",
                temperature=0.1,
                project_prompt=projekt.project_prompt,
            ).strip()

    # Ergebnisdictionary für Datenbank und Rückgabewert
    verification_result = {
        "technisch_verfuegbar": result,
        "ki_begruendung": justification,
        "ki_beteiligt": ai_involved,
        "ki_beteiligt_begruendung": ai_reason,
    }

    pf = BVProjectFile.objects.filter(projekt_id=project_id, anlage_nr=2).first()
    if not pf:
        logger.info(
            "worker_verify_feature beendet für Projekt %s Objekt %s %s",
            project_id,
            object_type,
            object_id,
        )
        return verification_result

    verif = pf.verification_json or {}
    if lookup_key:
        verif[lookup_key] = verification_result
    pf.verification_json = verif
    pf.save(update_fields=["verification_json"])

    func_id = obj_to_check.id if object_type == "function" else obj_to_check.funktion_id
    res, _ = Anlage2FunctionResult.objects.update_or_create(
        projekt_id=project_id,
        funktion_id=func_id,
        defaults={"ai_result": verification_result},
    )

    doc_val = None
    if isinstance(res.doc_result, dict):
        d = res.doc_result.get("technisch_verfuegbar")
        if isinstance(d, dict):
            doc_val = d.get("value")
        elif isinstance(d, bool):
            doc_val = d
    ai_val = verification_result.get("technisch_verfuegbar")
    res.is_negotiable = doc_val is not None and ai_val is not None and doc_val == ai_val
    res.save(update_fields=["ai_result", "is_negotiable"])

    if object_type == "function":
        Anlage2FunctionResult.objects.filter(
            projekt_id=project_id,
            funktion_id=object_id,
            source="manual",
        ).delete()
    elif object_type == "subquestion":
        Anlage2FunctionResult.objects.filter(
            projekt_id=project_id,
            funktion_id=obj_to_check.funktion_id,
            source="manual",
            raw_json__subquestion_id=object_id,
        ).delete()

    logger.info(
        "worker_verify_feature beendet für Projekt %s Objekt %s %s",
        project_id,
        object_type,
        object_id,
    )
    return verification_result


def worker_run_initial_check(
    knowledge_id: int, user_context: str | None = None
) -> dict[str, object]:
    """Führt eine zweistufige LLM-Abfrage zu einer Software durch.

    ``user_context`` ermöglicht Zusatzinformationen, falls die Software nicht
    erkannt wurde.
    """

    logger.info(
        "worker_run_initial_check gestartet für Knowledge %s",
        knowledge_id,
    )
    sk = SoftwareKnowledge.objects.get(pk=knowledge_id)
    software_name = sk.software_name

    result = {"is_known_by_llm": False, "description": ""}
    try:
        # --- Stufe 1: Wissens-Check ---
        prompt_name = (
            "initial_check_knowledge_with_context"
            if user_context
            else "initial_check_knowledge"
        )
        prompt_knowledge = Prompt.objects.get(name=prompt_name)
        prompt1_text = prompt_knowledge.text.format(
            name=software_name,
            user_context=user_context or "",
        )
        tmp_prompt = Prompt(text=prompt1_text, use_system_role=False)
        reply1 = query_llm(
            tmp_prompt,
            {},
            model_type="default",
            project_prompt=sk.projekt.project_prompt,
        )
        sk.is_known_by_llm = "ja" in reply1.strip().lower()
        result["is_known_by_llm"] = sk.is_known_by_llm

        # --- Stufe 2: Beschreibung nur bei positiver Kenntnis ---
        if sk.is_known_by_llm:
            description_prompt = Prompt.objects.get(name="initial_llm_check")
            reply2 = query_llm(
                description_prompt,
                {"name": software_name},
                model_type="default",
                project_prompt=sk.projekt.project_prompt,
            )
            description = reply2.strip()
            sk.description = description
            result["description"] = description
        else:
            sk.description = ""
            result["description"] = ""

    except Prompt.DoesNotExist as exc:  # noqa: BLE001
        logger.error(f"Benötigter Prompt für Initial-Check nicht gefunden: {exc}")
    except Exception:  # noqa: BLE001
        logger.exception("worker_run_initial_check: LLM Fehler")
        sk.is_known_by_llm = False
        sk.description = ""

    sk.last_checked = timezone.now()
    sk.save(update_fields=["is_known_by_llm", "description", "last_checked"])
    logger.info(
        "worker_run_initial_check beendet für Knowledge %s",
        knowledge_id,
    )
    return result


def worker_run_anlage3_vision(project_id: int, model_name: str | None = None) -> dict:
    """Führt die Vision-Prüfung für Anlage 3 im Hintergrund aus."""

    logger.info(
        "worker_run_anlage3_vision gestartet für Projekt %s",
        project_id,
    )
    result = check_anlage3_vision(project_id, model_name=model_name)
    logger.info(
        "worker_run_anlage3_vision beendet für Projekt %s",
        project_id,
    )
    return result


def check_gutachten_functions(projekt_id: int, model_name: str | None = None) -> str:
    """Prüft das Gutachten auf fehlende Funktionen."""
    projekt = BVProject.objects.get(pk=projekt_id)
    if not projekt.gutachten_file:
        raise ValueError("kein Gutachten")
    path = Path(settings.MEDIA_ROOT) / projekt.gutachten_file.name
    text = extract_text(path)
    base_obj = Prompt.objects.filter(name="check_gutachten_functions").first()
    prefix = (
        base_obj.text
        if base_obj
        else (
            "Prüfe das folgende Gutachten auf weitere Funktionen, die nach "
            "\xa7 87 Abs. 1 Nr. 6 mitbestimmungspflichtig sein könnten. "
            "Gib eine kurze Empfehlung als Text zurück.\n\n"
        )
    )
    prompt_obj = Prompt(
        name="tmp", text=prefix + text, role=base_obj.role if base_obj else None
    )
    reply = query_llm(
        prompt_obj,
        {},
        model_name=model_name,
        model_type="gutachten",
        project_prompt=projekt.project_prompt,
    )
    projekt.gutachten_function_note = reply
    projekt.save(update_fields=["gutachten_function_note"])
    return reply


def worker_generate_gap_summary(result_id: int, model_name: str | None = None) -> str:
    """Erzeugt eine Gap-Zusammenfassung f\u00fcr ein Review-Ergebnis."""

    logger.info("worker_generate_gap_summary gestartet f\u00fcr Result %s", result_id)
    res = Anlage2FunctionResult.objects.select_related("projekt", "funktion").get(pk=result_id)

    ai_val = None
    if isinstance(res.ai_result, dict):
        ai_val = res.ai_result.get("technisch_verfuegbar")
    manual_val = None
    if isinstance(res.manual_result, dict):
        manual_val = res.manual_result.get("technisch_vorhanden")

    conflict = f"KI-Check: {ai_val} / Review: {manual_val}"

    gut_text = ""
    projekt = res.projekt
    if projekt.gutachten_file:
        path = Path(settings.MEDIA_ROOT) / projekt.gutachten_file.name
        try:
            gut_text = extract_text(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Gutachten konnte nicht geladen werden: %s", exc)

    snippet = gut_text[:500]

    base_prompt = Prompt.objects.filter(name="gap_summary").first()
    prefix = (
        base_prompt.text
        if base_prompt
        else (
            "Fasse kurz zusammen, warum der manuelle Review von der KI-Einschätzung abweicht.\n\n"
        )
    )
    text = f"Funktion: {res.funktion.name}\n{conflict}\n{snippet}"
    prompt_obj = Prompt(name="tmp", text=prefix + text, role=base_prompt.role if base_prompt else None)
    reply = query_llm(
        prompt_obj,
        {},
        model_name=model_name,
        model_type="gutachten",
        project_prompt=projekt.project_prompt,
    )
    res.gap_summary = reply.strip()
    res.save(update_fields=["gap_summary"])
    logger.info("worker_generate_gap_summary beendet f\u00fcr Result %s", result_id)
    return reply.strip()
