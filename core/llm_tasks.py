"""LLM-gest\xfctzte Aufgaben f\xfcr BV-Projekte."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone
from django_q.tasks import async_task

from .utils import get_project_file

from .models import (
    BVProject,
    BVProjectFile,
    Prompt,
    LLMConfig,
    Anlage1Config,
    Anlage1Question,
    Anlage2Function,
    Anlage2SubQuestion,
    AnlagenFunktionsMetadaten,
    FunktionsErgebnis,
    Anlage2Config,
    FormatBParserRule,
    AntwortErkennungsRegel,
    Anlage4Config,
    Anlage4ParserConfig,
    ZweckKategorieA,
    Anlage5Review,
    ProjectStatus,
    SoftwareKnowledge,
    Gutachten,
    Anlage3Metadata,
)
from .text_parser import (
    build_token_map,
    apply_tokens,
    apply_rules,
)
from .llm_utils import query_llm, query_llm_with_images
from .docx_utils import (
    extract_text,
    _normalize_function_name,
    extract_images,
    get_docx_page_count,
    get_pdf_page_count,
    parse_anlage2_table,
)
from thefuzz import fuzz
from .parser_manager import parser_manager
from .anlage4_parser import parse_anlage4, parse_anlage4_dual
from .anlage3_parser import parse_anlage3
from docx import Document

logger = logging.getLogger(__name__)
debug_logger = logging.getLogger("anlage2_debug")
anlage1_logger = logging.getLogger("anlage1_debug")
anlage2_logger = logging.getLogger("anlage2_debug")
anlage3_logger = logging.getLogger("anlage3_debug")
anlage4_logger = logging.getLogger("anlage4_debug")
workflow_logger = logging.getLogger("workflow_debug")
result_logger = logging.getLogger("anlage2_ergebnis")

# Standard-Prompt für die Prüfung von Anlage 4
_DEFAULT_A4_PROMPT = (
    "Du bist ein Experte für deutsches Betriebsverfassungsrecht und Datenschutz "
    "mit einem besonderen Fokus auf die Verhinderung von Leistungs- und Verhaltenskontrolle bei Mitarbeitern.\n\n"
    "Analysiere die folgende administrative Auswertung. Deine Aufgabe ist es, die Plausibilität zu bewerten, dass diese Auswertung rein administrativen Zwecken dient und nicht zur Überwachung von Mitarbeitern missbraucht werden kann.\n\n"
    "Berücksichtige bei deiner Analyse die Kombination aus dem Namen der Auswertung, den anwendenden Gesellschaften und den zuständigen Fachbereichen.\n\n"
    "Gib deine finale Bewertung ausschließlich als valides JSON-Objekt mit den Schlüsseln 'plausibilitaet', 'score' (0.0-1.0) und 'begruendung' zurück:\n{json}"
)
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


def _extract_bool(value: object) -> bool | None:
    """Extrahiert einen booleschen Wert aus ``value``."""

    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool):
        return value
    return None


def _calc_auto_negotiable(doc: object | None, ai: object | None) -> bool:
    """Berechnet den automatischen Verhandlungsstatus."""

    doc_val = _extract_bool(doc)
    ai_val = _extract_bool(ai)
    return doc_val is not None and ai_val is not None and doc_val == ai_val


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
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = text.replace("\u00b6", " ")
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _split_lines(text: str) -> list[str]:
    """Bereitet einen Text zeilengenau auf."""
    text = text.replace("\u00b6", "\n").replace("\r", "\n")
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        line = re.sub(r"\s{2,}", " ", line.replace("\t", " ")).strip()
        if line:
            cleaned.append(line)
    return cleaned


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
                    r"Frage\s+\d+(?:\.\d+)?[:.]?\s*" + re.escape(_clean_text(rest)),
                    re.IGNORECASE | re.DOTALL,
                )
            else:
                pattern = re.compile(re.escape(clean_var), re.IGNORECASE | re.DOTALL)
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
    debug_logger.debug("Starte Parsing für Anlage 2. Rohtext wird geloggt.")
    debug_logger.debug(
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
    """Analysiert eine Anlage 2 und legt Ergebnisse ab.

    Die Analyse erfolgt zeilenbasiert. Funktionsnamen oder definierte Aliase
    werden exakt dem Text vor dem Doppelpunkt zugeordnet. Mehrere Zeilen zu
    einer Funktion werden dabei zusammengeführt.
    """

    anlage2_logger.debug("Starte run_anlage2_analysis für Datei %s", project_file.pk)
    workflow_logger.info(
        "[%s] - PARSER START - Beginne Dokumenten-Analyse.",
        project_file.projekt_id,
    )

    # Alte Ergebnisse zum Projekt entfernen, damit nur die aktuelle Datei
    # berücksichtigt wird
    AnlagenFunktionsMetadaten.objects.filter(
        anlage_datei__projekt=project_file.projekt
    ).delete()

    cfg = Anlage2Config.get_instance()
    token_map = build_token_map(cfg)
    rules = list(AntwortErkennungsRegel.objects.all())
    if rules:
        result_logger.debug("Geladene AntwortErkennungsRegeln:")
        for r in rules:
            result_logger.debug(
                "- %s | %s | Prio %s",
                r.regel_name,
                r.erkennungs_phrase,
                r.prioritaet,
            )

    functions = list(
        Anlage2Function.objects.prefetch_related("anlage2subquestion_set").all()
    )

    lines = _split_lines(project_file.text_content or "")

    def _normalize_search(text: str) -> str:
        """Normalisiert Begriffe f\xfcr exakte Vergleiche."""
        return re.sub(r"[\W_]+", "", text).lower()

    fields = list({f[0] for f in FormatBParserRule.FIELD_CHOICES})

    func_alias_map: dict[str, Anlage2Function] = {}
    sub_alias_map: dict[str, tuple[Anlage2Function, Anlage2SubQuestion]] = {}

    for func in functions:
        aliases = [func.name]
        if func.detection_phrases:
            aliases.extend(func.detection_phrases.get("name_aliases", []))
        for alias in aliases:
            func_alias_map[_normalize_search(alias)] = func
        for sub in func.anlage2subquestion_set.all():
            sub_aliases = [sub.frage_text]
            if sub.detection_phrases:
                sub_aliases.extend(sub.detection_phrases.get("name_aliases", []))
            for alias in sub_aliases:
                sub_alias_map[_normalize_search(alias)] = (func, sub)

    results_map: dict[str, dict[str, object]] = {}

    def _get_entry(func: Anlage2Function, sub: Anlage2SubQuestion | None) -> dict[str, object]:
        key = func.name if sub is None else f"{func.name}: {sub.frage_text}"
        entry = results_map.get(key)
        if entry is None:
            entry = {"funktion": key}
            if sub is not None:
                entry["subquestion_id"] = sub.id
            for f in fields:
                entry[f] = None
            entry["not_found"] = False
            results_map[key] = entry
        return entry

    for line in lines:
        before, after = (line.split(":", 1) + [""])[0:2]
        norm = _normalize_search(before)
        if norm in func_alias_map:
            func = func_alias_map[norm]
            entry = _get_entry(func, None)
        elif norm in sub_alias_map:
            func, sub = sub_alias_map[norm]
            entry = _get_entry(func, sub)
        else:
            continue

        line_entry: dict[str, object] = {}
        apply_tokens(line_entry, after, token_map)
        apply_rules(line_entry, after, rules)
        for key, value in line_entry.items():
            if key in {"funktion", "subquestion_id"}:
                continue
            if entry.get(key) is None:
                entry[key] = value

    results: list[dict[str, object]] = []

    def _blank_entry(name: str) -> dict[str, object]:
        entry: dict[str, object] = {"funktion": name}
        for f in fields:
            entry[f] = None
        entry["not_found"] = True
        return entry

    for func in functions:
        entry = results_map.pop(func.name, None)
        if entry is None:
            entry = _blank_entry(func.name)
        results.append(entry)
        workflow_logger.info(
            "[%s] - PARSER-ERGEBNIS - Funktion '%s' -> parser_result: %s",
            project_file.projekt_id,
            func.name,
            json.dumps(entry, ensure_ascii=False),
        )

        for sub in func.anlage2subquestion_set.all():
            key = f"{func.name}: {sub.frage_text}"
            sub_entry = results_map.pop(key, None)
            if sub_entry is None:
                sub_entry = {"funktion": key, "subquestion_id": sub.id}
                for f in fields:
                    sub_entry[f] = None
                sub_entry["not_found"] = True
            results.append(sub_entry)

    for row in results:
        sub_id = row.get("subquestion_id")
        func_name = row.get("funktion")
        if not func_name:
            continue
        if sub_id:
            try:
                sub = Anlage2SubQuestion.objects.get(pk=sub_id)
            except Anlage2SubQuestion.DoesNotExist:
                continue
            func = sub.funktion
        else:
            try:
                func = Anlage2Function.objects.get(name=func_name)
            except Anlage2Function.DoesNotExist:
                continue
            sub = None

        tv = _extract_bool(
            row.get("technisch_vorhanden") or row.get("technisch_verfuegbar")
        )
        eins = _extract_bool(
            row.get("einsatz_bei_telefonica") or row.get("einsatz_telefonica")
        )
        lv = _extract_bool(row.get("zur_lv_kontrolle"))
        ki = _extract_bool(row.get("ki_beteiligung"))
        AnlagenFunktionsMetadaten.objects.update_or_create(
            anlage_datei=project_file,
            funktion=func,
            subquestion=sub,
            defaults={},
        )
        FunktionsErgebnis.objects.create(
            projekt=project_file.projekt,
            anlage_datei=project_file,
            funktion=func,
            subquestion=sub,
            quelle="parser",
            technisch_verfuegbar=tv,
            einsatz_bei_telefonica=eins,
            zur_lv_kontrolle=lv,
            ki_beteiligung=ki,
        )

    return results


def run_anlage2_analysis_async(file_id: int) -> list[dict[str, object]]:
    """Asynchrone Variante von ``run_anlage2_analysis``."""

    project_file = BVProjectFile.objects.get(pk=file_id)
    return run_anlage2_analysis(project_file)




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
            try:
                meta = parse_anlage3(anlage)
                if meta:
                    Anlage3Metadata.objects.update_or_create(
                        project_file=anlage, defaults=meta
                    )
            except Exception:
                anlage3_logger.exception("Parser Fehler")
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
            msg = (
                f"Entspricht nicht den Frage Anforderungen der IT Rahmen 2.0: Frage {found_num} statt {q.num}."
            )
            if q_data["hinweis"]:
                q_data["hinweis"] += " " + msg
            else:
                q_data["hinweis"] = msg
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
        debug_logger.error("Fehler im Parser: %s", exc)
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
            debug_logger.debug("Parser fand Funktion '%s' nicht", func.name)

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

        AnlagenFunktionsMetadaten.objects.update_or_create(

            anlage_datei=anlage,
            funktion=func,
        )
        FunktionsErgebnis.objects.create(
            projekt=projekt,
            anlage_datei=anlage,
            funktion=func,
            quelle=source,
            technisch_verfuegbar=_val(vals, "technisch_verfuegbar"),
            ki_beteiligung=_val(vals, "ki_beteiligung"),
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
                debug_logger.debug("Parser fand Unterfrage '%s' nicht", sub_name)
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

    template = ((cfg.prompt_template if cfg else "") or _DEFAULT_A4_PROMPT)

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
    template = ((cfg.prompt_template if cfg else "") or _DEFAULT_A4_PROMPT)
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
    template = ((cfg.prompt_template if cfg else "") or _DEFAULT_A4_PROMPT)
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
    try:
        anlage = projekt.anlagen.get(anlage_nr=2)
    except BVProjectFile.DoesNotExist as exc:  # pragma: no cover - selten
        raise ValueError("Anlage 2 fehlt") from exc
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

        AnlagenFunktionsMetadaten.objects.update_or_create(

            anlage_datei=anlage,
            funktion=func,
        )
        FunktionsErgebnis.objects.create(
            projekt=projekt,
            anlage_datei=anlage,
            funktion=func,
            quelle="llm",
            technisch_verfuegbar=vals.get("technisch_verfuegbar"),
            ki_beteiligung=vals.get("ki_beteiligung"),
        )
        results.append({**vals, "source": "llm", "funktion": func.name})
    if anlage:
        anlage.verification_task_id = ""
        anlage.save(update_fields=["verification_task_id"])
    return results


def run_conditional_anlage2_check(
    projekt_id: int, model_name: str | None = None
) -> None:
    """Prüft Hauptfunktionen und deren Unterfragen bei positivem Ergebnis."""

    projekt = BVProject.objects.get(pk=projekt_id)

    # Alle bisherigen Prüfergebnisse entfernen
    AnlagenFunktionsMetadaten.objects.filter(anlage_datei__projekt=projekt).delete()

    for func in Anlage2Function.objects.prefetch_related(
        "anlage2subquestion_set"
    ).order_by("name"):
        worker_verify_feature(
            projekt_id, "function", func.id, model_name
        )
        res = AnlagenFunktionsMetadaten.objects.filter(
            anlage_datei__projekt_id=projekt_id,
            funktion=func,
            subquestion__isnull=True,
        ).first()

        doc_ok = False

        if doc_ok:
            for sub in func.anlage2subquestion_set.all():
                worker_verify_feature(
                    projekt_id, "subquestion", sub.id, model_name
                )

    pf = get_project_file(projekt, 2)
    if pf:
        pf.verification_task_id = ""
        pf.save(update_fields=["verification_task_id"])


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
    workflow_logger.info(
        "[%s] - KI-CHECK START - Pr\u00fcfe Objekt [Typ: %s, ID: %s]",
        project_id,
        object_type,
        object_id,
    )

    projekt = BVProject.objects.get(pk=project_id)
    pf = get_project_file(projekt, 2)


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

    if object_type == "function":
        obj_to_check = Anlage2Function.objects.get(pk=object_id)
        context["function_name"] = obj_to_check.name
        lookup_key = obj_to_check.name
    elif object_type == "subquestion":
        obj_to_check = Anlage2SubQuestion.objects.get(pk=object_id)
        context["function_name"] = obj_to_check.funktion.name
        context["subquestion_text"] = obj_to_check.frage_text
        lookup_key = f"{obj_to_check.funktion.name}: {obj_to_check.frage_text}"
    else:
        raise ValueError("invalid object_type")

    try:
        prompt_name = (
            "anlage2_feature_verification"
            if object_type == "function"
            else "anlage2_subquestion_possibility_check"
        )
        prompt_obj = Prompt.objects.get(name=prompt_name)
    except Prompt.DoesNotExist:
        logger.error("Prompt '%s' nicht gefunden!", prompt_name)
        if object_type == "function":
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
        else:
            prompt_obj = Prompt(
                text=(
                    "Im Kontext der Funktion '{function_name}' der Software '{software_name}': "
                    "Ist die spezifische Anforderung '{subquestion_text}' technisch m\u00f6glich? "
                    "Antworte nur mit 'Ja', 'Nein' oder 'Unsicher'."
                ),
                use_system_role=False,
            )

    software_list = projekt.software_list

    name = context["function_name"]

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
        try:
            json_data = json.loads(ans)
        except Exception:  # noqa: BLE001
            json_data = None
        if isinstance(json_data, dict) and "technisch_verfuegbar" in json_data:
            val = json_data.get("technisch_verfuegbar")
            individual_results.append(val if isinstance(val, bool) else None)
            continue
        low = ans.lower()
        if low.startswith("ja"):
            individual_results.append(True)
        elif low.startswith("nein"):
            individual_results.append(False)
        else:
            individual_results.append(None)

    has_true = True in individual_results
    has_false = False in individual_results
    has_none = None in individual_results

    if has_true:
        result = True
    elif not has_false and has_none:
        result = None
    elif has_false and not has_none:
        result = False
    elif has_false and has_none:
        result = None
    else:
        result = False

    justification = ""
    ai_involved: bool | None = None
    ai_reason = ""
    if result is True or result is None:
        try:
            just_prompt_name = (
                "anlage2_feature_justification"
                if object_type == "function"
                else "anlage2_subquestion_justification_check"
            )
            just_prompt_obj = Prompt.objects.get(name=just_prompt_name)
        except Prompt.DoesNotExist:
            if object_type == "function":
                just_prompt_obj = Prompt(
                    text=(
                        "Warum besitzt die Software '{software_name}' typischerweise die "
                        "Funktion oder Eigenschaft '{function_name}'?   Ist es m\u00f6glich "
                        "mit der {function_name} eine Leistungskontrolle oder eine "
                        "Verhaltenskontrolle im Sinne des \xa787 Abs. 1 Nr. 6 BetrVg durchzuf\u00fchren?  Wenn ja, wie?"
                    ),
                    use_system_role=False,
                )
            else:
                just_prompt_obj = Prompt(
                    text=(
                        " [SYSTEM]\nDu bist Fachautor*in f\u00fcr IT-Mitbestimmung (\xa787 Abs. 1 Nr. 6 BetrVG).\n"
                        "Antworte Unterfrage pr\u00e4gnant in **maximal zwei S\u00e4tzen** (insgesamt \u2264 65 W\u00f6rter) und erf\u00fclle folgende Regeln :\n\n"
                        "1. Starte Teil A mit \u201eTypischer Zweck: \u2026\u201c  \n2. Starte Teil B mit \u201eKontrolle: Ja, \u2026\u201c oder \u201eKontrolle: Nein, \u2026\u201c.  \n"
                        "3. Nenne exakt die \u00fcbergebene Funktion/Eigenschaft, erfinde nichts dazu.  \n"
                        "4. Erkl\u00e4re knapp *warum* mit der Funktion die Unterfrage (oder warum nicht) eine Leistungs- oder Verhaltenskontrolle m\u00f6glich ist.  \n"
                        "5. Verwende Alltagssprache, keine Marketing-Floskeln.\n\n"
                        " [USER]\nSoftware: {{software_name}}  \nFunktion/Eigenschaft: {{function_name}}  \nUnterfrage: \"{{subquestion_text}}\""
                    ),
                    use_system_role=False,
                )
        idx = 0
        if result is True and True in individual_results:
            idx = individual_results.index(True)
        elif result is None and None in individual_results:
            idx = individual_results.index(None)
        context["software_name"] = software_list[idx]
        justification = query_llm(
            just_prompt_obj,
            context,
            model_name=model_name,
            model_type="anlagen",
            temperature=0.1,
            project_prompt=projekt.project_prompt,
        ).strip()

        if result is True:
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
                    ai_just_obj = Prompt.objects.get(name="anlage2_ai_verification_prompt")
                except Prompt.DoesNotExist:
                    ai_just_obj = Prompt(
                        text=(
                            "Gib eine kurze Begründung, warum die Funktion '{function_name}' "
                            "(oder die Unterfrage '{subquestion_text}') der Software "
                            "'{software_name}' eine KI-Komponente beinhaltet oder beinhalten kann, "
                            "insbesondere im Hinblick auf die Verarbeitung unstrukturierter Daten "
                            "oder nicht-deterministischer Ergebnisse."
                        ),
                        use_system_role=False,
                    )
                ai_reason = query_llm(
                    ai_just_obj,
                    {
                        "software_name": context["software_name"],
                        "function_name": name,
                        "subquestion_text": context.get("subquestion_text", ""),
                    },
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
    workflow_logger.info(
        "[%s] - KI-CHECK ERGEBNIS - Objekt [ID: %s] -> result: %s",
        project_id,
        object_id,
        json.dumps(verification_result, ensure_ascii=False),
    )

    func_id = obj_to_check.id if object_type == "function" else obj_to_check.funktion_id
    sub_obj = None
    if object_type == "subquestion":
        sub_obj = obj_to_check
    tv = verification_result.get("technisch_verfuegbar")
    ki_bet = verification_result.get("ki_beteiligt")
    res, _ = AnlagenFunktionsMetadaten.objects.update_or_create(
        anlage_datei=pf,
        funktion_id=func_id,
        subquestion=sub_obj,
        defaults={},
    )

    auto_val = _calc_auto_negotiable(tv, ki_bet)

    try:
        if res.is_negotiable_manual_override is None:
            res.is_negotiable = auto_val

        res.save(update_fields=["is_negotiable"])
    except DatabaseError:
        logger.warning(
            "FunktionsErgebnis %s wurde während der Verarbeitung gelöscht. Speichern wird übersprungen.",
            res.pk,
        )
        return verification_result

    try:
        FunktionsErgebnis.objects.create(
            projekt_id=project_id,
            anlage_datei=pf,
            funktion_id=func_id,
            subquestion=sub_obj,
            quelle="ki",
            technisch_verfuegbar=tv,
            ki_beteiligung=ki_bet,
            begruendung=justification,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Begr\u00fcndung konnte nicht gespeichert werden: %s", exc)


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


def worker_generate_gap_summary(result_id: int, model_name: str | None = None) -> dict[str, str]:
    """Erzeugt interne und externe Gap-Texte für ein Review-Ergebnis."""

    logger.info("worker_generate_gap_summary gestartet für Result %s", result_id)

    res = (
        AnlagenFunktionsMetadaten.objects.select_related(
            "anlage_datei",
            "funktion",
            "subquestion",
        ).get(pk=result_id)
    )

    pf = res.anlage_datei
    projekt = pf.projekt

    doc_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=res.funktion,
            subquestion=res.subquestion,
            quelle="parser",
        ).order_by("-created_at").first()
    )
    ai_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=res.funktion,
            subquestion=res.subquestion,
            quelle="ki",
        ).order_by("-created_at").first()
    )
    manual_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=res.funktion,
            subquestion=res.subquestion,
            quelle="manuell",
        ).order_by("-created_at").first()
    )

    context = {
        "funktion": res.funktion.name,
        "unterfrage": res.subquestion.frage_text if res.subquestion else "",
        "dokument_wert": getattr(doc_entry, "technisch_verfuegbar", None),
        "ki_wert": getattr(ai_entry, "technisch_verfuegbar", None),
        "manueller_wert": getattr(manual_entry, "technisch_verfuegbar", None),
        "ki_begruendung": getattr(ai_entry, "begruendung", ""),
    }

    prompt_internal = Prompt.objects.filter(name="gap_summary_internal").first()
    if not prompt_internal:
        prompt_internal = Prompt(name="tmp", text="Formuliere eine technische Zusammenfassung des Konflikts.")
    internal = query_llm(
        prompt_internal,
        context,
        model_name=model_name,
        model_type="gutachten",
        project_prompt=projekt.project_prompt,
    ).strip()

    prompt_external = Prompt.objects.filter(name="gap_communication_external").first()
    if not prompt_external:
        prompt_external = Prompt(name="tmp", text="Formuliere eine freundliche Rückfrage an den Fachbereich.")
    external = query_llm(
        prompt_external,
        context,
        model_name=model_name,
        model_type="gutachten",
        project_prompt=projekt.project_prompt,
    ).strip()

    res.gap_notiz = internal
    res.gap_summary = external
    res.save(update_fields=["gap_notiz", "gap_summary"])

    FunktionsErgebnis.objects.create(
        projekt=projekt,
        anlage_datei=pf,
        funktion=res.funktion,
        subquestion=res.subquestion,
        quelle="gap",
        gap_begruendung_intern=internal,
        gap_begruendung_extern=external,
    )

    logger.info("worker_generate_gap_summary beendet für Result %s", result_id)
    return {"intern": internal, "extern": external}



def check_anlage5(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\u00fcft Anlage 5 auf vorhandene Standardzwecke.

    Das optionale Argument ``model_name`` ist derzeit ohne Funktion und dient
    lediglich der Vereinheitlichung der API.\n    """

    anlage5_logger.info("check_anlage5 gestartet f\u00fcr Projekt %s", projekt_id)

    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=5)
    except BVProjectFile.DoesNotExist as exc:
        anlage5_logger.error("Anlage 5 fehlt f\u00fcr Projekt %s", projekt_id)
        raise ValueError("Anlage 5 fehlt") from exc

    path = Path(anlage.upload.path)
    anlage5_logger.debug("Pfad der Anlage 5: %s", path)

    try:
        document_text = extract_text(path)
        anlage5_logger.debug("Textextraktion erfolgreich: %r", document_text[:200])
    except Exception as exc:  # noqa: BLE001 - unerwarteter Fehler beim Parsen
        anlage5_logger.exception("Textextraktion fehlgeschlagen: %s", exc)
        document_text = ""

    found_purposes: list[ZweckKategorieA] = []
    anlage5_logger.debug("Starte Zweck-Analyse")
    for zweck in ZweckKategorieA.objects.order_by("id"):
        threshold = 95
        score = fuzz.partial_ratio(zweck.beschreibung.lower(), document_text.lower())
        anlage5_logger.debug(
            "Zweck '%s' Score=%s -> %s",
            zweck.beschreibung,
            score,
            "gefunden" if score >= threshold else "nicht gefunden",
        )
        if score >= threshold:
            found_purposes.append(zweck)

    other_text = ""
    m = re.search(
        r"Sonstige Zwecke zur Leistungs- oder und Verhaltenskontrolle[:\s-]*([^\n]*)",
        document_text,
        flags=re.I,
    )
    if m:
        other_text = m.group(1).strip()
        anlage5_logger.debug("Sonstige Zwecke gefunden: %r", other_text)
        if re.fullmatch(r"[-_]*", other_text) or other_text.lower() in {
            "n/a",
            "keine",
            "-",
        }:
            other_text = ""
            anlage5_logger.debug("Sonstige Zwecke sind nur ein Platzhalter")
    else:
        anlage5_logger.debug("Sonstige Zwecke nicht gefunden")

    review, created = Anlage5Review.objects.get_or_create(project_file=anlage)
    anlage5_logger.debug(
        "%s Anlage5Review Objekt mit ID %s",
        "Erstelle" if created else "Aktualisiere",
        review.pk,
    )
    review.sonstige_zwecke = other_text
    review.save(update_fields=["sonstige_zwecke"])
    review.found_purposes.set(found_purposes)
    anlage5_logger.debug(
        "Gespeicherte Zwecke: %s, Sonstige Zwecke Text: %r",
        [p.id for p in found_purposes],
        other_text,
    )

    all_found = len(found_purposes) == ZweckKategorieA.objects.count() and not other_text
    anlage5_logger.debug(
        "Alle Zwecke gefunden: %s, Sonstige Zwecke vorhanden: %s -> verhandlungsfaehig=%s",
        len(found_purposes) == ZweckKategorieA.objects.count(),
        bool(other_text),
        all_found,
    )
    anlage.verhandlungsfaehig = all_found
    anlage.save(update_fields=["verhandlungsfaehig"])

    result = {
        "task": "check_anlage5",
        "purposes": [p.id for p in found_purposes],
        "sonstige": other_text,
    }
    anlage5_logger.info("check_anlage5 beendet f\u00fcr Projekt %s mit %s", projekt_id, result)
    return result
