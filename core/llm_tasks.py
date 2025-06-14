"""LLM-gest\xfctzte Aufgaben f\xfcr BV-Projekte."""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.utils import timezone

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
    ProjectStatus,
    SoftwareKnowledge,
)
from .llm_utils import query_llm
from .docx_utils import (
    parse_anlage2_table,
    parse_anlage2_text,
    extract_text,
    _normalize_function_name,
)
from docx import Document

logger = logging.getLogger(__name__)

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
    logger.debug(
        "parse_anlage1_questions: Aufruf mit text_content=%r",
        text_content[:200] if text_content else None,
    )
    if not text_content:
        logger.debug("parse_anlage1_questions: Kein Text übergeben.")
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
        logger.debug("parse_anlage1_questions: Keine aktiven Fragen vorhanden.")
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
            logger.debug(
                "parse_anlage1_questions: Frage %s gefunden an Position %d",
                q.num,
                best[0],
            )

    if not matches:
        logger.debug("parse_anlage1_questions: Keine Fragen im Text gefunden.")
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
        logger.debug(
            "parse_anlage1_questions: Antwort f\xfcr Frage %s: %r",
            num,
            parsed[str(num)]["answer"],
        )

    logger.debug(
        "parse_anlage1_questions: Ergebnis: %r",
        parsed if parsed else None,
    )
    return parsed if parsed else None


def _parse_anlage2(text_content: str) -> list[str] | None:
    """Extrahiert Funktionslisten aus Anlage 2."""
    if not text_content:
        return None
    text = text_content.replace("\u00b6", "\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    table_like = any(
        ("|" in line and line.count("|") >= 1) or "\t" in line for line in lines
    )
    if table_like:
        prompt = get_prompt(
            "anlage2_table",
            "Extrahiere die Funktionsnamen aus der folgenden Tabelle als JSON-Liste:\n\n",
        )
        reply = query_llm(prompt + text_content, model_name=None, model_type="anlagen")
        try:
            data = json.loads(reply)
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:  # noqa: BLE001
            logger.warning("_parse_anlage2: LLM Antwort kein JSON: %s", reply)
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
    """Parst eine Anlage 2-Datei mit Fallback.

    Zunächst wird versucht, die Tabelle zu lesen. Liefert dies keine Daten,
    kommt der Text-Parser zum Einsatz. Das Ergebnis wird als JSON-String im
    Modell gespeichert.
    """

    logger.debug("Starte run_anlage2_analysis für Datei %s", project_file.pk)

    analysis_result = parse_anlage2_table(Path(project_file.upload.path))
    if analysis_result:
        logger.info("Tabellen-Parser verwendet")
    else:
        analysis_result = parse_anlage2_text(project_file.text_content)
        logger.info("Text-Parser als Fallback verwendet")

    project_file.analysis_json = json.dumps(analysis_result, ensure_ascii=False)
    project_file.save(update_fields=["analysis_json"])
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

    table_data = parse_anlage2_table(Path(anlage2.upload.path))
    table_names = [row["funktion"] for row in table_data]
    anlage_funcs = _parse_anlage2(anlage2.text_content) or []

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
    prefix = get_prompt(
        "classify_system",
        "Bitte klassifiziere das folgende Softwaresystem. Gib ein JSON mit den Schl\xfcsseln 'kategorie' und 'begruendung' zur\xfcck.\n\n",
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
    projekt.status = ProjectStatus.objects.get(key="CLASSIFIED")
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
    projekt.status = ProjectStatus.objects.get(key="GUTACHTEN_OK")
    projekt.save(update_fields=["gutachten_file", "status"])
    return path


def worker_generate_gutachten(project_id: int) -> str:
    """Erzeugt im Hintergrund ein Gutachten."""
    projekt = BVProject.objects.get(pk=project_id)
    prefix = get_prompt(
        "generate_gutachten",
        "Erstelle ein technisches Gutachten basierend auf deinem Wissen:\n\n",
    )
    model = LLMConfig.get_default("gutachten")
    text = query_llm(
        prefix + projekt.software_typen, model_name=model, model_type="gutachten"
    )
    path = generate_gutachten(projekt.id, text, model_name=model)
    return str(path)


def _check_anlage(projekt_id: int, nr: int, model_name: str | None = None) -> dict:
    """Pr\xfcft eine Anlage und speichert das Ergebnis."""
    projekt = BVProject.objects.get(pk=projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=nr)
    except (
        BVProjectFile.DoesNotExist
    ) as exc:  # pragma: no cover - Test deckt Abwesenheit nicht ab
        raise ValueError(f"Anlage {nr} fehlt") from exc

    prefix = get_prompt(
        f"check_anlage{nr}",
        "Pr\xfcfe die folgende Anlage auf Vollst\xe4ndigkeit. Gib ein JSON mit 'ok' und 'hinweis' zur\xfcck:\n\n",
    )
    prompt = prefix + anlage.text_content

    reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
    try:
        data = json.loads(reply)
    except Exception as _:
        data = {"raw": reply}

    data = _add_editable_flags(data)
    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
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
    logger.debug(
        "check_anlage1: Zu parsende Anlage1 text_content (ersten 500 Zeichen): %r",
        anlage.text_content[:500] if anlage.text_content else None,
    )

    parsed = parse_anlage1_questions(anlage.text_content)
    answers: dict[str, str | list | None]
    found_nums: dict[str, str | None] = {}
    data: dict

    if parsed:
        logger.info("Strukturiertes Dokument erkannt. Parser wird verwendet.")
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
        prompt = prefix + anlage.text_content

        logger.debug(
            "check_anlage1: Sende Prompt an LLM (ersten 500 Zeichen): %r", prompt[:500]
        )
        reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
        logger.debug("check_anlage1: LLM Antwort (ersten 500 Zeichen): %r", reply[:500])
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
            prompt = _ANLAGE1_EVAL.format(num=q.num, question=q.text, answer=ans)
            logger.debug(
                "check_anlage1: Sende Bewertungs-Prompt an LLM (Frage %s): %r",
                q.num,
                prompt,
            )
            try:
                reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
                logger.debug(
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
    logger.debug("Starte check_anlage2 f\u00fcr Projekt %s", projekt_id)
    try:
        anlage = projekt.anlagen.get(anlage_nr=2)
    except (
        BVProjectFile.DoesNotExist
    ) as exc:  # pragma: no cover - sollte selten passieren
        raise ValueError("Anlage 2 fehlt") from exc

    logger.debug("Anlage 2 Pfad: %s", anlage.upload.path)
    table = parse_anlage2_table(Path(anlage.upload.path))
    logger.debug("Anlage2 table data: %r", table)
    text = _collect_text(projekt)
    logger.debug("Collected project text: %r", text)
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
        logger.debug("Pr\u00fcfe Funktion '%s'", func.name)
        norm = _normalize_function_name(func.name)
        row = next(
            (r for r in table if _normalize_function_name(r["funktion"]) == norm),
            None,
        )
        logger.debug("Tabellenzeile: %s", row)
        def _val(item, key):
            value = item.get(key)
            if isinstance(value, dict) and "value" in value:
                return value["value"]
            return value

        if row and _val(row, "technisch_verfuegbar") is not None and _val(row, "ki_beteiligung") is not None:
            vals = {
                "technisch_verfuegbar": row.get("technisch_verfuegbar"),
                "ki_beteiligung": row.get("ki_beteiligung"),
            }
            source = "parser"
            raw = row
        else:
            # Sonst LLM befragen
            prompt = f"{prompt_base}Funktion: {func.name}\n\n{text}"
            logger.debug("LLM Prompt f\u00fcr Funktion '%s': %s", func.name, prompt)
            reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
            logger.debug("LLM Antwort f\u00fcr Funktion '%s': %s", func.name, reply)
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
        logger.debug("Ergebnis Funktion '%s': %s", func.name, vals)
        entry = {"funktion": func.name, **vals, "source": source}
        sub_list: list[dict] = []
        # Für jede Subfrage ebenfalls LLM befragen
        for sub in func.anlage2subquestion_set.all().order_by("id"):
            prompt = f"{prompt_base}Funktion: {sub.frage_text}\n\n{text}"
            logger.debug(
                "LLM Prompt f\u00fcr Subfrage '%s': %s", sub.frage_text, prompt
            )
            reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
            logger.debug(
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
    anlage.analysis_json = data
    anlage.save(update_fields=["analysis_json"])
    logger.debug("check_anlage2 Ergebnis: %s", data)
    return data


def check_anlage3(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xfcft die dritte Anlage."""
    return _check_anlage(projekt_id, 3, model_name)


def check_anlage4(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xfcft die vierte Anlage."""
    return _check_anlage(projekt_id, 4, model_name)


def check_anlage5(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xfcft die f\xfcnfte Anlage."""
    return _check_anlage(projekt_id, 5, model_name)


def check_anlage6(projekt_id: int, model_name: str | None = None) -> dict:
    """Pr\xfcft die sechste Anlage."""
    return _check_anlage(projekt_id, 6, model_name)


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
        prompt = f"{prompt_base}Funktion: {func.name}\n\n{text}"
        reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
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
                "source": "llm",
            },
        )
        results.append({**vals, "source": "llm", "funktion": func.name})
    return results


def worker_verify_feature(
    project_id: int,
    object_type: str,
    object_id: int,
    model_name: str | None = None,
) -> dict[str, bool | str | None]:
    """Pr\u00fcft im Hintergrund das Vorhandensein einer Einzelfunktion."""

    projekt = BVProject.objects.get(pk=project_id)
    if object_type == "function":
        feature_obj = Anlage2Function.objects.get(pk=object_id)
    elif object_type == "subquestion":
        feature_obj = Anlage2SubQuestion.objects.get(pk=object_id)
    else:
        raise ValueError("invalid object_type")

    prompt_base = get_prompt(
        "anlage2_feature_verification",
        (
            "Du bist ein Experte f\u00fcr IT-Systeme und Software-Architektur. "
            "Bewerte die folgende Aussage ausschlie\u00dflich basierend auf deinem "
            "allgemeinen Wissen \u00fcber die Software '{software_name}'. "
            'Antworte NUR mit "Ja", "Nein" oder "Unsicher". '
            "Aussage: Besitzt die Software '{software_name}' typischerweise "
            "die Funktion oder Eigenschaft '{function_name}'?"
        ),
    )

    software_list = [s.strip() for s in projekt.software_typen.split(",") if s.strip()]

    name = getattr(feature_obj, "name", None) or getattr(feature_obj, "frage_text")

    answers: list[str] = []
    for software in software_list:
        prompt = prompt_base.format(software_name=software, function_name=name)
        reply = query_llm(prompt, model_name=model_name, model_type="anlagen")
        answers.append(reply.strip())

    lower = [ans.lower() for ans in answers]
    if any(a.startswith("ja") for a in lower):
        result = True
    elif all(a.startswith("nein") for a in lower):
        result = False
    else:
        result = None

    justification = ""
    if result:
        # Zusätzliche Rückfrage beim LLM, warum die Funktion
        # üblicherweise vorhanden ist. Die Antwort wird später im
        # Review als Tooltip angezeigt.
        just_base = get_prompt(
            "anlage2_feature_justification",
            (
                "Warum besitzt die Software '{software_name}' typischerweise die "
                "Funktion oder Eigenschaft '{function_name}'?"
            ),
        )
        idx = next((i for i, a in enumerate(lower) if a.startswith("ja")), 0)
        just_prompt = just_base.format(
            software_name=software_list[idx],
            function_name=name,
        )
        justification = query_llm(
            just_prompt, model_name=model_name, model_type="anlagen"
        ).strip()

    data = {"technisch_verfuegbar": result, "ki_begruendung": justification}

    pf = (
        BVProjectFile.objects.filter(projekt_id=project_id, anlage_nr=2).first()
    )
    if not pf:
        return data

    verif = pf.verification_json or {}
    if object_type == "function":
        key = name
    else:
        key = f"{feature_obj.funktion.name}: {feature_obj.frage_text}"
    verif[key] = data
    pf.verification_json = verif
    pf.save(update_fields=["verification_json"])

    return data


def worker_run_initial_check(project_id: int, software_name: str) -> dict[str, object]:
    """Führt eine zweistufige LLM-Abfrage zu einer Software durch."""

    projekt = BVProject.objects.get(pk=project_id)
    sk, _ = SoftwareKnowledge.objects.get_or_create(
        projekt=projekt, software_name=software_name
    )

    result = {"is_known_by_llm": False, "description": ""}
    try:
        prompt1 = f"Kennst du die Software '{software_name}'?"
        reply1 = query_llm(prompt1, model_type="default")
        if reply1.strip().lower().startswith("ja"):
            sk.is_known_by_llm = True
            result["is_known_by_llm"] = True
            prompt2 = f"Beschreibe kurz die Software '{software_name}'."
            reply2 = query_llm(prompt2, model_type="default")
            description = reply2.strip()
            sk.description = description
            result["description"] = description
        else:
            sk.is_known_by_llm = False
            sk.description = ""
    except Exception:  # noqa: BLE001
        logger.exception("worker_run_initial_check: LLM Fehler")
        sk.is_known_by_llm = False
        sk.description = ""

    sk.last_checked = timezone.now()
    sk.save(update_fields=["is_known_by_llm", "description", "last_checked"])
    return result


def check_gutachten_functions(projekt_id: int, model_name: str | None = None) -> str:
    """Prüft das Gutachten auf fehlende Funktionen."""
    projekt = BVProject.objects.get(pk=projekt_id)
    if not projekt.gutachten_file:
        raise ValueError("kein Gutachten")
    path = Path(settings.MEDIA_ROOT) / projekt.gutachten_file.name
    text = extract_text(path)
    prefix = get_prompt(
        "check_gutachten_functions",
        (
            "Prüfe das folgende Gutachten auf weitere Funktionen, die nach "
            "\xa7 87 Abs. 1 Nr. 6 mitbestimmungspflichtig sein könnten. "
            "Gib eine kurze Empfehlung als Text zurück.\n\n"
        ),
    )
    reply = query_llm(prefix + text, model_name=model_name, model_type="gutachten")
    projekt.gutachten_function_note = reply
    projekt.save(update_fields=["gutachten_function_note"])
    return reply
