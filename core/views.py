from pathlib import Path
from tempfile import NamedTemporaryFile
import tempfile
import os
import re
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group, Permission
from django.http import (
    HttpRequest,
    HttpResponseBadRequest,
    Http404,
    HttpResponse,
    HttpResponseForbidden,
)
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib import messages
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.core.paginator import Paginator
from django.urls import reverse, reverse_lazy
from typing import Any
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
import io
import zipfile
from django.db import connection, transaction
from django.db.models import Q
import subprocess
import whisper
import torch
import json
import asyncio
from django_q.tasks import async_task, fetch, result, Task

from .forms import (
    RecordingForm,
    BVProjectForm,
    BVProjectUploadForm,
    BVProjectFileForm,
    BVProjectFileJSONForm,
    BVGapNotesForm,
    Anlage1ReviewForm,
    Anlage2ReviewForm,
    Anlage4ReviewForm,
    Anlage3MetadataForm,
    Anlage5ReviewForm,
    Anlage6ReviewForm,
    get_anlage2_fields,
    Anlage2FunctionForm,
    Anlage2FunctionImportForm,
    PromptImportForm,
    Anlage1ImportForm,
    Anlage2SubQuestionForm,
    get_anlage1_numbers,
    Anlage2ConfigForm,
    get_parser_choices,
    EditJustificationForm,
    JustificationForm,
    KnowledgeDescriptionForm,
    ProjectContextForm,
    ProjectStatusForm,
    ProjectStatusImportForm,
    LLMRoleForm,
    LLMRoleImportForm,
    UserPermissionsForm,
    UserImportForm,
    Anlage2ConfigImportForm,
    ProjectImportForm,
    Anlage2ParserRuleImportForm,
    ZweckKategorieAForm,
    SupervisionStandardNoteForm,
    AntwortErkennungsRegelForm,
    Anlage4ParserConfigForm,
    ParserSettingsForm,
    ActionForm,
    Anlage3ParserRuleForm,
)
from .text_parser import PHRASE_TYPE_CHOICES
from .models import (
    Recording,
    BVProject,
    BVProjectFile,
    transcript_upload_path,
    Prompt,
    LLMConfig,
    Anlage1Question,
    Anlage1QuestionVariant,
    Anlage2Function,
    Anlage2SubQuestion,
    Anlage2Config,
    Anlage2ColumnHeading,
    AnlagenFunktionsMetadaten,
    FunktionsErgebnis,
    SoftwareKnowledge,
    Gutachten,
    Tile,
    Area,
    ProjectStatus,
    LLMRole,
    AntwortErkennungsRegel,
    Anlage4Config,
    Anlage4ParserConfig,
    ZweckKategorieA,
    Anlage5Review,
    Anlage3ParserRule,
    Anlage3Metadata,
    SupervisionStandardNote,
)
from .docx_utils import extract_text, get_docx_page_count
from .llm_utils import query_llm
from .prompt_context import build_prompt_context
from .workflow import set_project_status
from .reporting import generate_gap_analysis, generate_management_summary
from .llm_tasks import (
    check_anlage1,
    analyse_anlage3,
    check_anlage2,
    analyse_anlage4,
    analyse_anlage4_async,
    check_anlage5,
    run_conditional_anlage2_check,
    run_anlage2_analysis,
    check_gutachten_functions,
    generate_gutachten,
    get_prompt,
    ANLAGE1_QUESTIONS,
    _calc_auto_negotiable,
    _extract_bool,
    summarize_anlage1_gaps,
    summarize_anlage2_gaps,
)
from .parser_manager import parser_manager

from .decorators import admin_required, tile_required
from .obs_utils import start_recording, stop_recording, is_recording
from .utils import get_project_file, start_analysis_for_file, has_any_gap
from django.forms import formset_factory, modelformset_factory


class StaffRequiredMixin(UserPassesTestMixin):
    """Mixin erlaubt Zugriff nur fÃ¼r Mitarbeiter."""

    def test_func(self) -> bool:
        return self.request.user.is_staff


import logging
import sys
import copy

import time

import markdown
import pypandoc
from django.conf import settings
from .templatetags.recording_extras import markdownify

logger = logging.getLogger(__name__)
detail_logger = logging.getLogger("anlage2_detail")
admin_a2_logger = logging.getLogger("anlage2_detail")
anlage2_logger = logging.getLogger("anlage2_detail")
ergebnis_logger = logging.getLogger("anlage2_result")
anlage4_logger = logging.getLogger("anlage4_detail")
workflow_logger = logging.getLogger("workflow_debug")


ADMIN_ROOT = ("admin_projects", "Admin")


def build_breadcrumbs(*crumbs: tuple[str, str] | str) -> list[dict[str, str]]:
    """Erzeugt eine Breadcrumb-Liste."""

    items: list[dict[str, str]] = []
    for c in crumbs:
        if isinstance(c, tuple):
            url_name, label = c
            items.append({"url": reverse(url_name), "label": label})
        else:
            items.append({"label": c})
    return items


_WHISPER_MODEL = None


def _get_whisper_model():
    """Lade das Whisper-Modell nur einmal."""
    global _WHISPER_MODEL
    logger.debug("Whisper-Modell wird angefordert")
    if _WHISPER_MODEL is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.debug("Lade Whisper-Modell auf %s", device)
        _WHISPER_MODEL = whisper.load_model("base", device=device)
        logger.debug("Whisper-Modell geladen")
    return _WHISPER_MODEL


def get_user_tiles(user, bereich: str) -> tuple[list[Area], list[Tile]]:
    """Ermittelt Bereiche und Tiles, auf die ``user`` Zugriff hat.

    Liefert eine Liste aller zugÃ¤nglichen Bereiche sowie die Tiles im
    angegebenen ``bereich``.
    """

    areas = Area.objects.filter(
        Q(userareaaccess__user=user)
        | Q(groupareaaccess__group__in=user.groups.all())
    ).distinct()
    tiles = Tile.objects.filter(areas__slug=bereich).filter(
        Q(groups__in=user.groups.all()) | Q(users=user)
    ).distinct()
    return list(areas), list(tiles)


def _user_can_edit_project(user: User, projekt: BVProject) -> bool:
    """PrÃ¼ft, ob ``user`` das angegebene ``projekt`` bearbeiten darf."""

    if user.is_superuser or user.is_staff:
        return True
    has_user_attr = hasattr(projekt, "user") and hasattr(projekt, "user_id")
    has_team_attr = hasattr(projekt, "team_members")
    user_assigned = has_user_attr and projekt.user_id is not None
    team_assigned = has_team_attr and projekt.team_members.exists()
    if not user_assigned and not team_assigned:
        return user.is_authenticated
    if user_assigned and projekt.user_id == user.id:
        return True
    if has_team_attr and projekt.team_members.filter(pk=user.pk).exists():
        return True
    return False


def get_cockpit_context(projekt: BVProject) -> dict:
    """Ermittelt Kennzahlen fÃ¼r das Projektcockpit."""

    all_files = projekt.anlagen.all()
    reviewed = all_files.filter(manual_reviewed=True).count()

    software_list = projekt.software_list
    knowledge_map = {k.software_name: k for k in projekt.softwareknowledge.all()}
    checked = 0
    for name in software_list:
        entry = knowledge_map.get(name)
        if entry and entry.last_checked:
            checked += 1

    return {
        "projekt": projekt,
        "history": projekt.status_history.all(),
        "num_attachments": all_files.count(),
        "num_reviewed": reviewed,
        "is_verhandlungsfaehig": projekt.is_verhandlungsfaehig,
        "knowledge_checked": checked,
        "total_software": len(software_list),
    }

# Felder ohne KI-UnterstÃ¼tzung: Werte stammen ausschlieÃŸlich aus
# Dokumentenparser oder manueller Eingabe.
NO_AI_FIELDS = {"einsatz_bei_telefonica", "zur_lv_kontrolle"}

def _analysis1_to_initial(anlage: BVProjectFile) -> dict:
    """Wandelt ``analysis_json`` in das Initialformat fÃ¼r ``Anlage1ReviewForm``."""

    data = anlage.analysis_json or {}
    if not isinstance(data, dict):
        return {}

    questions = data.get("questions")
    if not isinstance(questions, dict):
        return {}

    out: dict[str, dict] = {}
    for num in get_anlage1_numbers():
        q = questions.get(str(num), {})
        if not isinstance(q, dict):
            continue
        out[str(num)] = {
            "hinweis": q.get("hinweis", ""),
            "vorschlag": q.get("vorschlag", ""),
        }

    return out

def _analysis_to_initial(anlage: BVProjectFile) -> dict:
    """Ermittelt die Dokumentergebnisse aus der Datenbank.

    Fehlen Parser-Ergebnisse vollstÃ¤ndig, werden Analysewerte genutzt."""
    initial = {"functions": {}}
    field_names = [f[0] for f in get_anlage2_fields()]
    analysis_data: dict[str, dict] = {}

    if isinstance(anlage.analysis_json, dict):
        funcs = anlage.analysis_json.get("functions")
        if not isinstance(funcs, list):
            funcs = []
        for item in funcs:
            name = item.get("funktion") or item.get("name")
            func = Anlage2Function.objects.filter(name__iexact=name).first()
            if not func:
                continue
            fid = str(func.id)
            target = analysis_data.setdefault(fid, {})
            for f in field_names:
                target[f] = item.get(f)
            subs = item.get("subquestions", [])
            for sub in subs:
                text = sub.get("frage_text")
                if not text:
                    continue
                sub_obj = Anlage2SubQuestion.objects.filter(
                    funktion=func, frage_text=text
                ).first()
                if not sub_obj:
                    continue
                sid = str(sub_obj.id)
                sub_target = target.setdefault("subquestions", {}).setdefault(
                    sid, {}
                )
                for f in field_names:
                    sub_target[f] = sub.get(f)

    results = AnlagenFunktionsMetadaten.objects.filter(anlage_datei=anlage)
    has_parser_data = False

    for res in results:
        func_id = str(res.funktion_id)
        target = initial["functions"].setdefault(func_id, {})
        dest = target
        if res.subquestion_id:
            dest = target.setdefault("subquestions", {}).setdefault(
                str(res.subquestion_id), {},
            )
        latest = (
            FunktionsErgebnis.objects.filter(
                anlage_datei=anlage,
                funktion_id=res.funktion_id,
                subquestion_id=res.subquestion_id,
                quelle="parser",
            )
            .order_by("-created_at")
            .first()
        )
        if latest:
            dest["technisch_vorhanden"] = latest.technisch_verfuegbar
            dest["einsatz_bei_telefonica"] = latest.einsatz_bei_telefonica
            dest["zur_lv_kontrolle"] = latest.zur_lv_kontrolle
            dest["ki_beteiligung"] = latest.ki_beteiligung
            has_parser_data = True
        if res.gap_summary:
            dest["gap_summary"] = res.gap_summary
        if res.gap_notiz:
            dest["gap_notiz"] = res.gap_notiz

    if not has_parser_data and analysis_data:
        initial["functions"] = analysis_data
    else:
        for fid, data in analysis_data.items():
            initial["functions"].setdefault(fid, data)

    detail_logger.debug("Ergebnis initial: %r", initial)
    return initial


def _verification_to_initial(pf: BVProjectFile | None) -> dict:
    """Liest KI-PrÃ¼fergebnisse einer Anlage aus der Datenbank."""
    initial = {"functions": {}}

    results = (
        AnlagenFunktionsMetadaten.objects.filter(anlage_datei=pf)
        if isinstance(pf, BVProjectFile)
        else []
    )

    for res in results:
        func_id = str(res.funktion_id)
        target = initial["functions"].setdefault(func_id, {})
        dest = target
        if res.subquestion_id:
            dest = target.setdefault("subquestions", {}).setdefault(
                str(res.subquestion_id), {}
            )
        latest = (
            FunktionsErgebnis.objects.filter(
                anlage_datei=res.anlage_datei,
                funktion_id=res.funktion_id,
                subquestion_id=res.subquestion_id,
                quelle="ki",
            )
            .order_by("-created_at")
            .first()
        )
        if latest:
            dest["technisch_vorhanden"] = latest.technisch_verfuegbar
            dest["ki_beteiligt"] = latest.ki_beteiligung
            dest["einsatz_bei_telefonica"] = latest.einsatz_bei_telefonica
            dest["zur_lv_kontrolle"] = latest.zur_lv_kontrolle
            dest["begruendung"] = latest.begruendung

    return initial


def _initial_to_lookup(data: dict) -> dict[str, dict]:
    """Wandelt das Initialformat in ein Lookup nach Namen um."""
    lookup: dict[str, dict] = {}
    fields = get_anlage2_fields()
    for func in Anlage2Function.objects.prefetch_related(
        "anlage2subquestion_set"
    ).order_by("name"):
        fid = str(func.id)
        func_data = data.get("functions", {}).get(fid)
        if isinstance(func_data, dict):
            lookup[func.name] = {
                field: func_data[field] for field, _ in fields if field in func_data
            }
        else:
            lookup[func.name] = {}
        for sub in func.anlage2subquestion_set.all():
            sid = str(sub.id)
            sub_data: dict | None = None
            if isinstance(func_data, dict):
                sub_data = func_data.get("subquestions", {}).get(sid)
            if isinstance(sub_data, dict):
                lookup[f"{func.name}: {sub.frage_text}"] = {
                    field: sub_data[field] for field, _ in fields if field in sub_data
                }
            else:
                lookup[f"{func.name}: {sub.frage_text}"] = {}
    return lookup


def _resolve_value(
    manual_val: bool | None,
    ai_val: bool | None,
    doc_val: bool | None,
    field: str,
    manual_exists: bool = False,
    doc_exists: bool = False,
) -> tuple[bool | None, str]:
    """Ermittelt den Review-Wert und dessen Quelle.

    Berücksichtigt manuelle Angaben, KI-Vorschläge und ob eine Dokumenten-Analyse vorliegt.
    Zusätzlich werden Objektwerte ({"value": bool, ...}) auf bool/None normalisiert.
    """

    def _to_bool(val):
        if isinstance(val, dict):
            val = val.get("value")
        if isinstance(val, bool):
            return val
        return None

    man_b = _to_bool(manual_val)
    ai_b = _to_bool(ai_val)
    doc_b = _to_bool(doc_val)

    src = "Dokumenten-Analyse" if doc_exists or doc_b is not None else "N/A"

    # Für doc-only Felder (kein KI, Anzeige nur nach Dokument)
    if field in NO_AI_FIELDS:
        if doc_b is not None:
            return doc_b, src
        return False, src

    # Bei übrigen Feldern: manuelle Werte haben Vorrang
    if manual_exists or manual_val is not None:
        return man_b, "Manuell"

    # Danach KI, dann Dokument
    if ai_b is not None:
        return ai_b, src
    if doc_b is not None:
        return doc_b, src

    # Fallback
    return False, src


def _get_display_data(
    lookup_key: str,
    analysis_data: dict[str, dict],
    verification_data: dict[str, dict],
    manual_results_map: dict[str, dict],
) -> dict[str, object]:
    """Ermittelt finale Werte und Quellen fÃ¼r eine Funktion oder Unterfrage."""

    fields = get_anlage2_fields()
    doc_exists = bool(analysis_data.get(lookup_key))
    a_data = analysis_data.get(lookup_key, {})
    v_data = verification_data.get(lookup_key, {})
    m_data = manual_results_map.get(lookup_key, {})

    values: dict[str, bool] = {}
    sources: dict[str, str] = {}
    manual_flags: dict[str, bool] = {}

    for field, _ in fields:
        man_val = m_data.get(field)
        ai_val = v_data.get(field)
        doc_val = a_data.get(field)
        # Normalize values from analysis/verification: they can be dicts like
        # {"value": bool, "note": str}. Extract the boolean for display logic.
        if isinstance(doc_val, dict) and "value" in doc_val:
            doc_val = doc_val.get("value")
        if isinstance(ai_val, dict) and "value" in ai_val:
            ai_val = ai_val.get("value")
        manual_exists = field in m_data
        val, src = _resolve_value(man_val, ai_val, doc_val, field, manual_exists, doc_exists)
        values[field] = val
        sources[field] = src
        manual_flags[field] = manual_exists

    return {
        "values": values,
        "sources": sources,
        "status": values.get("technisch_vorhanden"),
        "source": sources.get("technisch_vorhanden"),
        "manual_flags": manual_flags,
    }


def _has_manual_gap(doc_data: dict, manual_data: dict) -> bool:
    """Ermittelt, ob manuelle Angaben von den Dokumentdaten abweichen."""

    for field, man_val in manual_data.items():
        if man_val is not None:
            man_bool = _extract_bool(man_val)
            doc_val = doc_data.get(field)
            doc_bool = _extract_bool(doc_val) if doc_val is not None else None
            if field in ["einsatz_bei_telefonica", "zur_lv_kontrolle"]:
                if doc_bool is not None and man_bool != doc_bool:
                    return True
            else:
                if doc_bool is None or man_bool != doc_bool:
                    return True
    return False


def _build_row_data(
    display_name: str,
    lookup_key: str,
    func_id: int,
    form_prefix: str,
    form,
    answers: dict[str, dict],
    ki_map: dict[tuple[str, str | None], str],
    beteilig_map: dict[tuple[str, str | None], tuple[bool | None, str]],
    manual_lookup: dict[str, dict],
    result_map: dict[str, AnlagenFunktionsMetadaten],
    sub_id: int | None = None,
) -> dict:
    """Erzeugt die Darstellungsdaten fÃ¼r eine Funktion oder Unterfrage."""

    result_obj = result_map.get(lookup_key)
    # Fallback: Bei Unterfragen ggf. Ergebnis der Hauptfunktion verwenden
    if result_obj is None and sub_id is not None:
        parent_key = lookup_key.split(":", 1)[0].strip()
        result_obj = result_map.get(parent_key)

    if result_obj:
        pf = result_obj.anlage_datei
        parser_entry = (
            FunktionsErgebnis.objects.filter(
                anlage_datei=pf,
                funktion=result_obj.funktion,
                subquestion=result_obj.subquestion,
                quelle="parser",
            )
            .order_by("-created_at")
            .first()
        )
        ai_entry = (
            FunktionsErgebnis.objects.filter(
                anlage_datei=pf,
                funktion=result_obj.funktion,
                subquestion=result_obj.subquestion,
                quelle="ki",
            )
            .order_by("-created_at")
            .first()
        )
        doc_data = {
            "technisch_vorhanden": parser_entry.technisch_verfuegbar
            if parser_entry
            else None,
            "einsatz_bei_telefonica": parser_entry.einsatz_bei_telefonica
            if parser_entry
            else None,
            "zur_lv_kontrolle": parser_entry.zur_lv_kontrolle if parser_entry else None,
            "ki_beteiligung": parser_entry.ki_beteiligung if parser_entry else None,
            "begruendung": parser_entry.begruendung if parser_entry else None,
            "ki_beteiligt_begruendung": parser_entry.ki_beteiligt_begruendung
            if parser_entry
            else None,
        }
        ai_data = {
            "technisch_vorhanden": ai_entry.technisch_verfuegbar if ai_entry else None,
            "ki_beteiligung": ai_entry.ki_beteiligung if ai_entry else None,
            "begruendung": ai_entry.begruendung if ai_entry else None,
            "ki_beteiligt_begruendung": ai_entry.ki_beteiligt_begruendung
            if ai_entry
            else None,
        }
    else:
        doc_data = {}
        ai_data = {}

    if not doc_data:
        doc_answers = answers.get(lookup_key)
        if doc_answers:
            # Fallback auf analysierte Felder, falls keine Dokumentdaten vorliegen
            for field in (
                "technisch_vorhanden",
                "einsatz_bei_telefonica",
                "zur_lv_kontrolle",
                "ki_beteiligung",
            ):
                if field in doc_answers:
                    doc_data[field] = doc_answers[field]

    override_val = result_obj.is_negotiable_manual_override if result_obj else None
    manual_data = manual_lookup.get(lookup_key, {})
    doc_json = json.dumps(doc_data, ensure_ascii=False)
    ai_json = json.dumps(ai_data, ensure_ascii=False)
    manual_json = json.dumps(manual_data, ensure_ascii=False)

    disp = _get_display_data(
        lookup_key, answers, {lookup_key: ai_data}, manual_lookup
    )
    fields_def = get_anlage2_fields()
    form_fields_map: dict[str, dict] = {}
    rev_origin = {}
    for field, _ in fields_def:
        bf = form[f"{form_prefix}{field}"]
        initial_value = disp["values"].get(field)
        state = (
            "true"
            if initial_value is True
            else "false"
            if initial_value is False
            else "unknown"
        )
        origin_val = "none"
        if field == "technisch_vorhanden":
            man_val = manual_lookup.get(lookup_key, {}).get(field)
            ai_val = ai_data.get(field)
            if man_val is not None:
                origin_val = "manual"
            elif ai_val is not None:
                origin_val = "ai"
        rev_origin[field] = origin_val
        attrs = {
            "data-tristate": "true",
            "data-initial-state": state,
            "style": "display: none;",
            "data-origin": origin_val,
        }
        if field == "technisch_vorhanden" and sub_id is not None:
            attrs.update(
                {
                    "disabled": True,
                    "class": "opacity-50 pointer-events-none",
                    "data-initial-state": "unknown",
                }
            )
        bf.field.widget.attrs.update(attrs)
        form_fields_map[field] = {
            "widget": bf,
            "source": disp["sources"][field],
            "origin": rev_origin.get(field),
        }

    auto_val = _calc_auto_negotiable(
        doc_data.get("technisch_vorhanden"), ai_data.get("technisch_vorhanden")
    )
    manual_gap = _has_manual_gap(doc_data, manual_data)
    if override_val is not None:
        is_negotiable = override_val
    else:
        is_negotiable = False if manual_gap else auto_val
    gap_widget = form[f"{form_prefix}gap_summary"]
    note_widget = form[f"{form_prefix}gap_notiz"]
    begr_md = ki_map.get((str(func_id), str(sub_id) if sub_id else None))
    bet_val, bet_reason = beteilig_map.get(
        (str(func_id), str(sub_id) if sub_id else None), (None, "")
    )
    has_gap = False
    # Manuelle NachprÃ¼fung erforderlich, wenn Dokument und KI sich unterscheiden
    # und kein manueller Wert hinterlegt ist
    manual_review_required = False
    for field, _ in fields_def:
        doc_val = doc_data.get(field)
        ai_val = ai_data.get(field)
        manual_val = manual_lookup.get(lookup_key, {}).get(field)
        if field not in ["einsatz_bei_telefonica", "zur_lv_kontrolle"]:
            if (
                doc_val is not None
                and ai_val is not None
                and doc_val != ai_val
                and manual_val is None
            ):
                has_gap = True
                manual_review_required = True
                break
    return {
        "name": display_name,
        "doc_result": doc_data,
        "doc_json": doc_json,
        "ai_result": ai_data,
        "ai_json": ai_json,
        "manual_result": manual_data,
        "manual_json": manual_json,
        "initial": disp["values"],
        "manual_flags": disp["manual_flags"],
        "form_fields": form_fields_map,
        "is_negotiable": is_negotiable,
        "negotiable_manual_override": override_val,
        "gap_summary_widget": gap_widget,
        "gap_notiz_widget": note_widget,
        "gap_notiz": result_obj.gap_notiz if result_obj else "",
        "gap_summary": result_obj.gap_summary if result_obj else "",
        "has_notes": bool(
            result_obj and (result_obj.gap_notiz or result_obj.gap_summary)
        ),
        "sub": sub_id is not None,
        "func_id": func_id,
        "sub_id": sub_id,
        "result_id": result_obj.id if result_obj else None,
        "verif_key": lookup_key,
        "source_text": disp["source"],
        "ki_begruendung": begr_md,
        "ki_begruendung_md": begr_md,
        "ki_begruendung_html": markdownify(begr_md) if begr_md else "",
        "has_justification": bool(begr_md and begr_md.strip()),
        "ki_beteiligt": bet_val,
        "ki_beteiligt_begruendung": bet_reason,
        "has_preliminary_gap": has_gap,
        "requires_manual_review": manual_review_required,
    }


def _build_supervision_row(
    result: AnlagenFunktionsMetadaten, pf: BVProjectFile
) -> dict:
    """Erzeugt eine einfache Datenstruktur fÃ¼r die Supervisions-Ansicht."""

    parser_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion=result.subquestion,
            quelle="parser",
        )
        .order_by("-created_at")
        .first()
    )
    ai_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion=result.subquestion,
            quelle="ki",
        )
        .order_by("-created_at")
        .first()
    )
    manual_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion=result.subquestion,
            quelle="manuell",
        )
        .order_by("-created_at")
        .first()
    )

    doc_val = parser_entry.technisch_verfuegbar if parser_entry else None
    ai_val = ai_entry.technisch_verfuegbar if ai_entry else None
    final_val = manual_entry.technisch_verfuegbar if manual_entry else None

    if result.is_negotiable_manual_override:
        has_discrepancy = False
    elif manual_entry is not None:
        has_discrepancy = doc_val is not None and final_val != doc_val
    else:
        has_discrepancy = (
            doc_val is not None and ai_val is not None and doc_val != ai_val
        )

    return {
        "result_id": result.id,
        "name": result.get_lookup_key(),
        "doc_val": doc_val,
        "doc_snippet": parser_entry.begruendung if parser_entry else "",
        "ai_val": ai_val,
        # Nutze die allgemeine KI-BegrÃ¼ndung der Funktion
        "ai_reason": ai_entry.begruendung if ai_entry else "",
        "final_val": final_val,
        "notes": result.supervisor_notes or "",
        "has_discrepancy": has_discrepancy,
    }


def _build_supervision_groups(pf: BVProjectFile) -> list[dict]:
    """Gruppiert Hauptfunktionen und Unterfragen fÃ¼r die Supervision.

    Funktionen, die manuell als verhandlungsfÃ¤hig markiert wurden, werden
    vollstÃ¤ndig ignoriert.
    """

    # IDs von Funktionen, bei denen die VerhandlungsfÃ¤higkeit manuell
    # Ã¼berschrieben wurde. Diese werden samt Unterfragen Ã¼bersprungen.
    overridden_funcs = set(
        AnlagenFunktionsMetadaten.objects.filter(
            anlage_datei=pf,
            is_negotiable_manual_override=True,
        ).values_list("funktion_id", flat=True)
    )

    results = (
        AnlagenFunktionsMetadaten.objects.filter(anlage_datei=pf)
        .select_related("funktion", "subquestion")
        .order_by("funktion__name", "subquestion__id")
    )

    grouped: dict[int, dict] = {}
    for r in results:
        if r.funktion_id in overridden_funcs:
            continue
        row_data = _build_supervision_row(r, pf)
        if not row_data["has_discrepancy"]:
            continue
        key = r.funktion_id
        grouped.setdefault(
            key, {"function": None, "subrows": [], "name": r.funktion.name}
        )
        if r.subquestion_id:
            grouped[key]["subrows"].append(row_data)
        else:
            grouped[key]["function"] = row_data

    groups: list[dict] = []
    for g in grouped.values():
        func = g.get("function")
        subrows = g.get("subrows", [])
        if not func and not subrows:
            continue
        if not subrows and func and not func["has_discrepancy"]:
            continue
        present = func["final_val"] if func else None
        if present is None and func:
            present = func["doc_val"] if func["doc_val"] is not None else func["ai_val"]
        groups.append(
            {
                "function": func,
                "subrows": subrows,
                "show_subs": bool(present) or not func,
            }
        )
    return groups


def get_cockpit_context(projekt: BVProject) -> dict[str, Any]:
    """Stellt alle Kontextinformationen fÃ¼r das Cockpit bereit."""

    files = []
    next_steps: list[str] = []
    for f in projekt.anlagen.all():
        files.append(
            {
                "id": f.id,
                "anlage_nr": f.anlage_nr,
                "name": os.path.basename(f.upload.name),
                "processing_status": f.processing_status,
                "verhandlungsfaehig": f.verhandlungsfaehig,
            }
        )
        data = f.analysis_json if isinstance(f.analysis_json, dict) else {}
        if data.get("manual_required"):
            next_steps.append(f"Anlage {f.anlage_nr}: manuelle PrÃ¼fung notwendig")
        elif f.processing_status != BVProjectFile.COMPLETE:
            next_steps.append(f"Anlage {f.anlage_nr}: Analyse starten")

    status_history = list(projekt.status_history.order_by("-changed_at")[:5])
    recent_uploads = list(projekt.anlagen.order_by("-created_at")[:5])

    return {
        "title": projekt.title,
        "status": projekt.status.name if projekt.status else "",
        "software": projekt.software_string,
        "created_at": projekt.created_at,
        "files": files,
        "next_steps": next_steps,
        "status_history": status_history,
        "recent_uploads": recent_uploads,
    }


@login_required
def home(request):
    # Logic from codex/prÃ¼fen-und-weiterleiten-basierend-auf-tile-typ
    # Assuming get_user_tiles is defined elsewhere and correctly retrieves tiles
    _, tiles_personal = get_user_tiles(request.user, Tile.PERSONAL)
    _, tiles_work = get_user_tiles(request.user, Tile.WORK)

    if tiles_personal and not tiles_work:
        return redirect("personal")
    if tiles_work and not tiles_personal:
        return redirect("work")

    work_area = Area.objects.filter(slug="work").first() if tiles_work else None
    personal_area = (
        Area.objects.filter(slug="personal").first() if tiles_personal else None
    )
    context = {
        "work_area": work_area,
        "personal_area": personal_area,
    }
    return render(request, "home.html", context)


@login_required
def work(request):
    is_admin = request.user.groups.filter(name__iexact="admin").exists()
    _, tiles = get_user_tiles(request.user, Tile.WORK)
    context = {
        "is_admin": is_admin,
        "tiles": tiles,
    }
    return render(request, "work.html", context)


@login_required
def personal(request):
    is_admin = request.user.groups.filter(name__iexact="admin").exists()
    _, tiles = get_user_tiles(request.user, Tile.PERSONAL)
    context = {
        "is_admin": is_admin,
        "tiles": tiles,
    }
    return render(request, "personal.html", context)


@login_required
def account(request):
    return render(request, "account.html")


@login_required
@admin_required
def recording_page(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect("home")
    rec_dir = Path(settings.MEDIA_ROOT) / "recordings" / bereich
    files = []
    if rec_dir.exists():
        for f in sorted(rec_dir.iterdir(), reverse=True):
            files.append({"name": f.name, "mtime": f.stat().st_mtime})
    context = {
        "bereich": bereich,
        "is_recording": is_recording(),
        "recordings": files,
    }
    return render(request, "recording.html", context)


@login_required
def start_recording_view(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect("home")
    start_recording(bereich, Path(settings.MEDIA_ROOT))
    return redirect("recording_page", bereich=bereich)


@login_required
def stop_recording_view(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect("home")
    stop_recording()
    time.sleep(1)
    _process_recordings_for_user(bereich, request.user)
    return redirect("recording_page", bereich=bereich)


@login_required
def toggle_recording_view(request, bereich):
    """Toggle OBS recording status from the TalkDiary page."""
    if bereich not in ["work", "personal"]:
        return redirect("home")

    if is_recording():
        stop_recording()

        # wait a moment to allow OBS to finalize the file
        time.sleep(1)
        _process_recordings_for_user(bereich, request.user)
        rec_dir = Path(settings.MEDIA_ROOT) / "recordings" / bereich
        if not list(rec_dir.glob("*.mkv")) and not list(rec_dir.glob("*.wav")):
            messages.warning(request, "Keine Aufnahme gefunden")

    else:
        start_recording(bereich, Path(settings.MEDIA_ROOT))
        messages.success(request, "Aufnahme gestartet")

    if "HTTP_REFERER" in request.META:
        return redirect(request.META["HTTP_REFERER"])
    return redirect("talkdiary_%s" % bereich)


@login_required
def upload_recording(request):
    if request.method == "POST":
        form = RecordingForm(request.POST, request.FILES)
        if form.is_valid():
            bereich = form.cleaned_data["bereich"]
            uploaded = form.cleaned_data["audio_file"]
            logger.debug(
                "Upload erhalten: %s f\u00fcr Bereich %s", uploaded.name, bereich
            )

            rel_path = Path("recordings") / bereich / uploaded.name
            storage_name = default_storage.get_available_name(str(rel_path))
            if storage_name != str(rel_path):
                messages.info(request, "Datei existierte bereits, wurde umbenannt.")

            file_path = default_storage.save(storage_name, uploaded)
            logger.debug("Datei gespeichert: %s", file_path)

            abs_path = default_storage.path(file_path)
            final_rel = file_path
            if Path(abs_path).suffix.lower() == ".mkv":
                ffmpeg = (
                    Path(settings.BASE_DIR)
                    / "tools"
                    / (
                        "ffmpeg.exe"
                        if (Path(settings.BASE_DIR) / "tools" / "ffmpeg.exe").exists()
                        else "ffmpeg"
                    )
                )
                if not ffmpeg.exists():
                    ffmpeg = "ffmpeg"
                wav_rel = Path(file_path).with_suffix(".wav")
                wav_storage = default_storage.get_available_name(str(wav_rel))
                wav_abs = default_storage.path(wav_storage)
                try:
                    logger.debug("Konvertiere %s nach %s", abs_path, wav_abs)
                    subprocess.run(
                        [str(ffmpeg), "-y", "-i", abs_path, wav_abs], check=True
                    )
                    Path(abs_path).unlink(missing_ok=True)
                    final_rel = wav_storage
                except Exception:
                    return HttpResponseBadRequest("Konvertierung fehlgeschlagen")

            if Recording.objects.filter(
                audio_file=final_rel, user=request.user
            ).exists():
                messages.info(request, "Aufnahme bereits in der Datenbank.")
                return redirect("dashboard")

            recording = Recording.objects.create(
                user=request.user,
                bereich=Area.objects.get(slug=bereich),
                audio_file=final_rel,
            )

            out_dir = (
                Path(settings.MEDIA_ROOT) / f"transcripts/{recording.bereich.slug}"
            )
            out_dir.mkdir(parents=True, exist_ok=True)

            model = _get_whisper_model()
            try:
                logger.debug("Starte Transkription: %s", recording.audio_file.path)
                result = model.transcribe(recording.audio_file.path, language="de")
            except Exception:
                return HttpResponseBadRequest("Transkription fehlgeschlagen")

            md_path = out_dir / f"{Path(recording.audio_file.name).stem}.md"
            md_path.write_text(result["text"], encoding="utf-8")
            with md_path.open("rb") as f:
                recording.transcript_file.save(md_path.name, f, save=False)
            lines = result["text"].splitlines()[:5]
            recording.excerpt = "\n".join(lines)
            recording.save()
            logger.debug("Aufnahme gespeichert: %s", recording)

            return redirect("dashboard")
    else:
        form = RecordingForm()

    return render(request, "upload_recording.html", {"form": form})


@login_required
def dashboard(request):
    recordings = Recording.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "dashboard.html", {"recordings": recordings})


@login_required
def upload_transcript(request):
    """ErmÃ¶glicht das manuelle Hochladen eines Transkript-Files."""
    from .forms import TranscriptUploadForm

    if request.method == "POST":
        form = TranscriptUploadForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            rec = form.cleaned_data["recording"]
            uploaded = form.cleaned_data["transcript_file"]

            rel_path = transcript_upload_path(rec, uploaded.name)
            storage_name = default_storage.get_available_name(rel_path)
            path = default_storage.save(storage_name, uploaded)

            with default_storage.open(path, "rb") as f:
                rec.transcript_file.save(Path(path).name, f, save=False)

            txt = default_storage.open(path).read().decode("utf-8")
            rec.excerpt = "\n".join(txt.splitlines()[:2])
            rec.save()
            return redirect("talkdiary_%s" % rec.bereich)
    else:
        form = TranscriptUploadForm(user=request.user)

    return render(request, "upload_transcript.html", {"form": form})


def _process_recordings_for_user(bereich: str, user) -> list:
    """Convert and transcribe recordings for ``bereich`` and ``user``.

    Returns a list of :class:`Recording` objects found or created.
    """

    logger.debug(
        "Beginne Verarbeitung f\u00fcr Bereich '%s' und Benutzer '%s'", bereich, user
    )
    media_root = Path(settings.MEDIA_ROOT)
    base_dir = Path(settings.BASE_DIR)
    rec_dir = media_root / "recordings" / bereich
    trans_dir = media_root / "transcripts" / bereich

    rec_dir.mkdir(parents=True, exist_ok=True)
    trans_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = (
        base_dir
        / "tools"
        / ("ffmpeg.exe" if (base_dir / "tools" / "ffmpeg.exe").exists() else "ffmpeg")
    )
    if not ffmpeg.exists():
        ffmpeg = "ffmpeg"

    # Pfad zu ffmpeg dem System-PATH hinzufÃ¼gen, falls notwendig
    tools_dir = str(base_dir / "tools")
    current_path = os.environ.get("PATH", "")
    if tools_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = current_path + os.pathsep + tools_dir

    logger.debug("Konvertiere mkv-Dateien")
    # convert mkv to wav and remove mkv
    for mkv in list(rec_dir.glob("*.mkv")) + list(rec_dir.glob("*.MKV")):
        wav = mkv.with_suffix(".wav")
        if not wav.exists() and mkv.exists():
            try:
                logger.debug("ffmpeg %s -> %s", mkv, wav)
                subprocess.run(
                    [str(ffmpeg), "-y", "-i", str(mkv), str(wav)], check=True
                )

                mkv.unlink(missing_ok=True)

            except Exception as exc:
                logger.error("ffmpeg failed: %s", exc)

    logger.debug("Transkribiere wav-Dateien")

    for wav in list(rec_dir.glob("*.wav")) + list(rec_dir.glob("*.WAV")):
        if not wav.exists():
            continue

        md = trans_dir / f"{wav.stem}.md"
        if not md.exists():
            logger.debug("Transkribiere %s", wav)
            model = _get_whisper_model()
            try:
                result = model.transcribe(str(wav), language="de")
            except Exception as exc:
                logger.error("whisper failed: %s", exc)
                continue

            md.write_text(result["text"], encoding="utf-8")
            logger.debug("Transkript gespeichert: %s", md)

    recordings = []

    for wav in list(rec_dir.glob("*.wav")) + list(rec_dir.glob("*.WAV")):
        md = trans_dir / f"{wav.stem}.md"
        excerpt = ""
        if md.exists():
            lines = md.read_text(encoding="utf-8").splitlines()[:5]
            excerpt = "\n".join(lines)
        rel_wav = Path("recordings") / bereich / wav.name
        rel_md = Path("transcripts") / bereich / md.name if md.exists() else None
        rec_obj, _ = Recording.objects.get_or_create(
            user=user,
            bereich=Area.objects.get(slug=bereich),
            audio_file=str(rel_wav),
        )
        if rel_md and not rec_obj.transcript_file:
            with md.open("rb") as f:
                rec_obj.transcript_file.save(md.name, f, save=False)
        if excerpt:
            rec_obj.excerpt = excerpt
        rec_obj.save()
        logger.debug("Recording verarbeitet: %s", rec_obj)
        recordings.append(rec_obj)

    logger.debug("Verarbeitung abgeschlossen")
    return recordings


@login_required
@tile_required("talkdiary")
def talkdiary(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect("home")

    # always process new recordings; manual rescan available via query param
    _process_recordings_for_user(bereich, request.user)

    recordings = Recording.objects.filter(
        user=request.user, bereich__slug=bereich
    ).order_by("-created_at")

    context = {
        "bereich": bereich,
        "recordings": recordings,
        "is_recording": is_recording(),
        "is_admin": request.user.groups.filter(name__iexact="admin").exists(),
    }
    return render(request, "talkdiary.html", context)


@login_required
@tile_required("talkdiary")
def talkdiary_detail(request, pk):
    try:
        rec = Recording.objects.get(pk=pk, user=request.user)
    except Recording.DoesNotExist:
        return redirect("home")

    md_text = ""
    if rec.transcript_file:
        md_path = Path(settings.MEDIA_ROOT) / rec.transcript_file.name
        if md_path.exists():
            md_text = md_path.read_text(encoding="utf-8")

    area_slug = getattr(rec.bereich, "slug", "")
    if area_slug == "work":
        list_url = reverse("talkdiary_work")
    else:
        list_url = reverse("talkdiary_personal")

    filename = Path(rec.audio_file.name).name
    breadcrumbs = [
        {"url": list_url, "label": "TalkDiary"},
        {"label": filename},
    ]

    context = {
        "recording": rec,
        "transcript_text": md_text,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "talkdiary_detail.html", context)


@login_required
def transcribe_recording(request, pk):
    """Startet die Transkription fÃ¼r eine einzelne Aufnahme."""
    try:
        rec = Recording.objects.get(pk=pk, user=request.user)
    except Recording.DoesNotExist:
        return redirect("home")

    out_dir = Path(settings.MEDIA_ROOT) / f"transcripts/{rec.bereich}"
    out_dir.mkdir(parents=True, exist_ok=True)

    audio_path = Path(rec.audio_file.path)
    if not audio_path.exists():
        messages.error(request, "Audio-Datei nicht gefunden")
        return redirect("talkdiary_%s" % rec.bereich)

    if rec.transcript_file:
        messages.info(request, "Transkript existiert bereits")
        return redirect("talkdiary_%s" % rec.bereich)

    track = int(request.POST.get("track", "1"))

    ffmpeg = (
        Path(settings.BASE_DIR)
        / "tools"
        / (
            "ffmpeg.exe"
            if (Path(settings.BASE_DIR) / "tools" / "ffmpeg.exe").exists()
            else "ffmpeg"
        )
    )
    if not ffmpeg.exists():
        ffmpeg = "ffmpeg"

    source = (
        audio_path
        if audio_path.suffix.lower() == ".mkv"
        else audio_path.with_suffix(".mkv")
    )

    if track != 1 or source.suffix.lower() == ".mkv":
        if not source.exists():
            messages.error(request, "Originaldatei mit mehreren Spuren nicht gefunden")
            return redirect("talkdiary_%s" % rec.bereich)
        wav_path = source.with_name(f"{source.stem}_track{track}.wav")
        try:
            logger.debug("Extrahiere Spur %s: %s -> %s", track, source, wav_path)
            subprocess.run(
                [
                    str(ffmpeg),
                    "-y",
                    "-i",
                    str(source),
                    "-map",
                    f"0:a:{track - 1}",
                    str(wav_path),
                ],
                check=True,
            )
        except Exception as exc:
            logger.error("ffmpeg failed: %s", exc)
            messages.error(request, "Konvertierung fehlgeschlagen")
            return redirect("talkdiary_%s" % rec.bereich)
        if track == 1:
            rec.audio_file.name = f"recordings/{rec.bereich}/{wav_path.name}"
            rec.save()
        audio_path = wav_path

    messages.info(request, "Transkription gestartet")

    model = _get_whisper_model()
    try:
        logger.debug("Starte Transkription: %s", audio_path)
        result = model.transcribe(str(audio_path), language="de", word_timestamps=True)
    except Exception as exc:
        logger.error("whisper failed: %s", exc)
        messages.error(request, "Transkription fehlgeschlagen")
        return redirect("talkdiary_%s" % rec.bereich)

    stem = Path(rec.audio_file.name).stem
    md_name = f"{stem}.md" if track == 1 else f"{stem}_track{track}.md"
    md_path = out_dir / md_name
    md_path.write_text(result["text"], encoding="utf-8")

    if track == 1:
        with md_path.open("rb") as f:
            rec.transcript_file.save(md_path.name, f, save=False)
        rec.excerpt = "\n".join(result["text"].splitlines()[:5])
        rec.save()
    logger.debug("Transkription abgeschlossen f\u00fcr %s", rec)
    messages.success(request, "Transkription abgeschlossen")

    return redirect("talkdiary_%s" % rec.bereich)


@login_required
@require_http_methods(["POST"])
def recording_delete(request, pk):
    """LÃ¶scht eine Aufnahme des angemeldeten Benutzers."""
    try:
        rec = Recording.objects.get(pk=pk, user=request.user)
    except Recording.DoesNotExist:
        raise Http404

    if rec.audio_file:
        (Path(settings.MEDIA_ROOT) / rec.audio_file.name).unlink(missing_ok=True)
    if rec.transcript_file:
        (Path(settings.MEDIA_ROOT) / rec.transcript_file.name).unlink(missing_ok=True)

    bereich = rec.bereich.slug if hasattr(rec.bereich, "slug") else rec.bereich
    rec.delete()
    messages.success(request, "Aufnahme gelöscht")
    return redirect("talkdiary_%s" % bereich)


@login_required
@admin_required
def admin_talkdiary(request):
    recordings = list(Recording.objects.all().order_by("-created_at"))

    active_filter = request.GET.get("filter")
    filtered = []
    for rec in recordings:
        audio_path = Path(settings.MEDIA_ROOT) / rec.audio_file.name
        transcript_path = (
            Path(settings.MEDIA_ROOT) / rec.transcript_file.name
            if rec.transcript_file
            else None
        )
        rec.audio_missing = not audio_path.exists()
        rec.transcript_missing = rec.transcript_file == "" or (
            transcript_path and not transcript_path.exists()
        )
        rec.incomplete = rec.audio_missing or rec.transcript_missing

        if active_filter == "missing_audio" and not rec.audio_missing:
            continue
        if active_filter == "missing_transcript" and not rec.transcript_missing:
            continue
        if active_filter == "incomplete" and not rec.incomplete:
            continue
        filtered.append(rec)

    if request.method == "POST":
        ids = request.POST.getlist("delete")
        for rec in Recording.objects.filter(id__in=ids):
            if rec.audio_file:
                (Path(settings.MEDIA_ROOT) / rec.audio_file.name).unlink(
                    missing_ok=True
                )
            if rec.transcript_file:
                (Path(settings.MEDIA_ROOT) / rec.transcript_file.name).unlink(
                    missing_ok=True
                )
            rec.delete()
        return redirect("admin_talkdiary")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "TalkDiary")
    context = {
        "recordings": filtered,
        "active_filter": active_filter or "",
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "admin_talkdiary.html", context)


@login_required
@admin_required
def admin_projects(request):
    """Verwaltet die Projektliste mit Such- und Filterfunktionen."""
    projects = BVProject.objects.all().order_by("-created_at")

    if request.method == "POST":
        # Fall 1: Der globale Knopf zum LÃ¶schen markierter Projekte wurde gedrÃ¼ckt
        if "delete_selected" in request.POST:
            selected_ids = request.POST.getlist("selected_projects")
            if not selected_ids:
                messages.warning(request, "Keine Projekte zum Löschen ausgewählt.")
            else:
                try:
                    projects_to_delete = BVProject.objects.filter(id__in=selected_ids)
                    count = projects_to_delete.count()
                    projects_to_delete.delete()
                    messages.success(
                        request, f"{count} Projekt(e) erfolgreich gelöscht."
                    )
                except Exception as e:
                    messages.error(
                        request, "Ein Fehler ist beim Löschen der Projekte aufgetreten."
                    )
                    logger.error(
                        f"Error deleting multiple projects: {e}", exc_info=True
                    )

        # Fall 2: Ein individueller LÃ¶schknopf wurde gedrÃ¼ckt
        elif "delete_single" in request.POST:
            project_id_to_delete = request.POST.get("delete_single")
            try:
                project = BVProject.objects.get(id=project_id_to_delete)
                project_title = project.title
                project.delete()
                messages.success(
                    request, f"Projekt '{project_title}' wurde erfolgreich gelöscht."
                )
            except BVProject.DoesNotExist:
                messages.error(
                    request, "Das zu löschende Projekt wurde nicht gefunden."
                )
            except Exception as e:
                messages.error(
                    request,
                    "Projekt konnte nicht gelöscht werden. Ein unerwarteter Fehler ist aufgetreten.",
                )
                logger.error(
                    f"Error deleting single project {project_id_to_delete}: {e}",
                    exc_info=True,
                )

        return redirect("admin_projects")

    # GET-Logik: Suche und Filter
    search_query = request.GET.get("q", "")
    if search_query:
        projects = projects.filter(title__icontains=search_query)

    status_filter = request.GET.get("status", "")
    if status_filter:
        projects = projects.filter(status__key=status_filter)

    software_filter = request.GET.get("software", "")
    if software_filter:
        projects = projects.filter(
            bvsoftware__name__icontains=software_filter
        ).distinct()
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Projekte")
    context = {
        "projects": projects,
        "projekte": projects,
        "form": BVProjectForm(),
        "search_query": search_query,
        "status_filter": status_filter,
        "software_filter": software_filter,
        "status_choices": ProjectStatus.objects.all(),
        "breadcrumbs": breadcrumbs,
    }
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "partials/_admin_project_rows.html", context)
    return render(request, "admin_projects.html", context)


@login_required
@admin_required
@require_http_methods(["POST"])
def admin_project_delete(request, pk):
    """LÃ¶scht ein einzelnes Projekt."""
    projekt = get_object_or_404(BVProject, pk=pk)
    projekt_title = projekt.title
    try:
        projekt.delete()
        messages.success(
            request, f"Projekt '{projekt_title}' wurde erfolgreich gelöscht."
        )
    except Exception as e:
        messages.error(
            request,
            f"Projekt '{projekt_title}' konnte nicht gelöscht werden. Ein unerwarteter Fehler ist aufgetreten.",
        )
        logger.error(
            f"Error deleting project {projekt.id} ('{projekt_title}'): {e}",
            exc_info=True,
        )
    return redirect("admin_projects")


@login_required
@admin_required
def admin_project_cleanup(request, pk):
    """Bietet LÃ¶schfunktionen fÃ¼r Projektdaten."""
    projekt = get_object_or_404(BVProject, pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete_file":
            file_id = request.POST.get("file_id")
            try:
                anlage = projekt.anlagen.get(pk=file_id)
            except BVProjectFile.DoesNotExist:
                raise Http404
            if anlage.upload:
                (Path(settings.MEDIA_ROOT) / anlage.upload.name).unlink(missing_ok=True)
            anlage.delete()
            messages.success(request, "Anlage gelöscht")
            return redirect("admin_project_cleanup", pk=projekt.pk)
        if action == "delete_gutachten":
            if projekt.gutachten_file:
                projekt.gutachten_file.delete(save=False)
                projekt.gutachten_file = ""
                projekt.save(update_fields=["gutachten_file"])
            messages.success(request, "Gutachten gelöscht")
            return redirect("admin_project_cleanup", pk=projekt.pk)
        if action == "delete_classification":
            projekt.classification_json = None
            projekt.save(update_fields=["classification_json"])
            messages.success(request, "Bewertung gelöscht")
            return redirect("admin_project_cleanup", pk=projekt.pk)
        if action == "delete_summary":
            projekt.llm_initial_output = ""
            projekt.llm_antwort = ""
            projekt.llm_geprueft = False
            projekt.llm_geprueft_am = None
            projekt.llm_validated = False
            projekt.save(
                update_fields=[
                    "llm_initial_output",
                    "llm_antwort",
                    "llm_geprueft",
                    "llm_geprueft_am",
                    "llm_validated",
                ]
            )
            messages.success(request, "Summary gelöscht")
            return redirect("admin_project_cleanup", pk=projekt.pk)
        if action == "delete_gap_report":
            pf1 = get_project_file(projekt, 1)
            pf2 = get_project_file(projekt, 2)
            if pf1:
                pf1.gap_summary = ""
                pf1.save(update_fields=["gap_summary"])
            if pf2:
                pf2.gap_summary = ""
                pf2.save(update_fields=["gap_summary"])
            messages.success(request, "GAP-Bericht gelöscht")
            return redirect("admin_project_cleanup", pk=projekt.pk)

    gap_report_exists = (
        projekt.anlagen.filter(anlage_nr__in=[1, 2]).exclude(gap_summary="").exists()
    )
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Projekt bereinigen")
    context = {
        "projekt": projekt,
        # Dateien nach Anlagennummer und Version sortieren
        "files": projekt.anlagen.all().order_by("anlage_nr", "version"),
        "gap_report_exists": gap_report_exists,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "admin_project_cleanup.html", context)


@login_required
@admin_required
@require_http_methods(["POST"])
def admin_project_export(request):
    """Exportiert ausgewÃ¤hlte Projekte als ZIP-Archiv."""
    ids = request.POST.getlist("selected_projects")
    if not ids:
        messages.error(request, "Keine Projekte zum Export ausgewÃ¤hlt.")
        return redirect("admin_projects")

    projects = BVProject.objects.filter(id__in=ids)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        data = []
        for proj in projects:
            item = {
                "title": proj.title,
                "beschreibung": proj.beschreibung,
                "status": proj.status.key if proj.status else "",
                "classification_json": proj.classification_json,
                "gutachten_function_note": proj.gutachten_function_note,
                "software": list(proj.bvsoftware_set.values_list("name", flat=True)),
                "files": [],
            }
            if proj.gutachten_file:
                path = Path(settings.MEDIA_ROOT) / proj.gutachten_file.name
                if path.exists():
                    zip_name = f"gutachten/{path.name}"
                    zf.write(path, zip_name)
                    item["gutachten_file"] = zip_name
            for f in proj.anlagen.all():
                fitem = {
                    "anlage_nr": f.anlage_nr,
                    "manual_comment": f.manual_comment,
                    "analysis_json": f.analysis_json,
                    "manual_reviewed": f.manual_reviewed,
                    "verhandlungsfaehig": f.verhandlungsfaehig,
                    "filename": None,
                }
                if f.upload:
                    p = Path(settings.MEDIA_ROOT) / f.upload.name
                    if p.exists():
                        zip_name = f"files/{p.name}"
                        zf.write(p, zip_name)
                        fitem["filename"] = zip_name
                item["files"].append(fitem)
            data.append(item)
        zf.writestr("projects.json", json.dumps(data, ensure_ascii=False, indent=2))
    buffer.seek(0)
    resp = HttpResponse(buffer.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = "attachment; filename=projects_export.zip"
    return resp


@login_required
@admin_required
@require_http_methods(["POST"])
def admin_project_import(request):
    """Importiert Projekte aus einem ZIP-Archiv."""
    form = ProjectImportForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Keine gÃ¼ltige Datei hochgeladen.")
        return redirect("admin_projects")

    uploaded = form.cleaned_data["json_file"]
    try:
        with zipfile.ZipFile(uploaded) as zf:
            raw = zf.read("projects.json").decode("utf-8")
            items = json.loads(raw)
            with transaction.atomic():
                for entry in items:
                    status = ProjectStatus.objects.filter(
                        key=entry.get("status")
                    ).first()
                    proj = BVProject.objects.create(
                        title=entry.get("title", ""),
                        beschreibung=entry.get("beschreibung", ""),
                        status=status,
                        classification_json=entry.get("classification_json"),
                        gutachten_function_note=entry.get(
                            "gutachten_function_note", ""
                        ),
                    )
                    if entry.get("gutachten_file"):
                        content = zf.read(entry["gutachten_file"])
                        saved = default_storage.save(
                            f"gutachten/{Path(entry['gutachten_file']).name}",
                            ContentFile(content),
                        )
                        proj.gutachten_file = saved
                        proj.save(update_fields=["gutachten_file"])
                    for name in entry.get("software", []):
                        BVSoftware.objects.create(project=proj, name=name)
                    for fentry in entry.get("files", []):
                        upload_name = ""
                        if fentry.get("filename"):
                            content = zf.read(fentry["filename"])
                            upload_name = default_storage.save(
                                f"bv_files/{Path(fentry['filename']).name}",
                                ContentFile(content),
                            )
                        BVProjectFile.objects.create(
                            project=proj,
                            anlage_nr=fentry.get("anlage_nr"),
                            upload=upload_name,
                            manual_comment=fentry.get("manual_comment", ""),
                            analysis_json=fentry.get("analysis_json"),
                            manual_reviewed=fentry.get("manual_reviewed", False),
                            verhandlungsfaehig=fentry.get("verhandlungsfaehig", False),
                        )
        messages.success(request, "Projekte importiert.")
    except Exception as exc:  # noqa: BLE001
        messages.error(request, "Fehler beim Import: %s" % exc)
        logger.error("Import error", exc_info=True)
    return redirect("admin_projects")


@login_required
@admin_required
def admin_prompts(request):
    """Verwaltet die gespeicherten Prompts."""
    prompts = list(Prompt.objects.all().order_by("name"))
    roles = list(LLMRole.objects.all().order_by("name"))
    groups = {
        "general": [],
        "anlage1": [],
        "anlage2": [],
        "anlage3": [],
        "anlage4": [],
    }
    for p in prompts:
        name = p.name.lower()
        if "anlage1" in name:
            groups["anlage1"].append(p)
        elif "anlage2" in name:
            groups["anlage2"].append(p)
        elif "anlage3" in name:
            groups["anlage3"].append(p)
        elif "anlage4" in name:
            groups["anlage4"].append(p)
        else:
            groups["general"].append(p)

    if request.method == "POST":
        pk = request.POST.get("pk")
        action = request.POST.get("action")
        if pk:
            try:
                prompt = Prompt.objects.get(pk=pk)
            except Prompt.DoesNotExist:
                raise Http404
            if action == "delete":
                prompt.delete()
            elif action == "save":
                prompt.text = request.POST.get("text", "")
                role_id = request.POST.get("role")
                prompt.role = (
                    LLMRole.objects.filter(pk=role_id).first() if role_id else None
                )
                prompt.use_system_role = bool(request.POST.get("use_system_role"))
                prompt.use_project_context = bool(
                    request.POST.get("use_project_context")
                )
                prompt.save(
                    update_fields=[
                        "text",
                        "role",
                        "use_system_role",
                        "use_project_context",
                    ]
                )
        return redirect("admin_prompts")

    labels = [
        ("general", "Allgemeine Projektprompts"),
        ("anlage1", "Anlage 1 Prompts"),
        ("anlage2", "Anlage 2 Prompts"),
        ("anlage3", "Anlage 3 Prompts"),
        ("anlage4", "Anlage 4 Prompts"),
    ]

    grouped = [(key, label, groups[key]) for key, label in labels]
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Prompts")
    context = {
        "grouped": grouped,
        "roles": roles,
        
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "admin_prompts.html", context)


@login_required
@admin_required
def admin_prompt_export(request):
    """Exportiert alle Prompts als JSON-Datei."""
    items = [
        {
            "name": p.name,
            "text": p.text,
            "role_id": p.role_id,
            "use_system_role": p.use_system_role,
            "use_project_context": p.use_project_context,
        }
        for p in Prompt.objects.all().order_by("name")
    ]
    content = json.dumps(items, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=prompts.json"
    return resp


@login_required
@admin_required
def admin_prompt_import(request):
    """Importiert Prompts aus einer JSON-Datei."""
    form = PromptImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(data)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("admin_prompt_import")
        if form.cleaned_data["clear_first"]:
            Prompt.objects.all().delete()
        for item in items:
            name = item.get("name") or item.get("key") or ""
            Prompt.objects.update_or_create(
                name=name,
                defaults={
                    "text": item.get("text") or item.get("prompt_text", ""),
                    "role_id": item.get("role_id"),
                    "use_system_role": item.get("use_system_role", True),
                    "use_project_context": item.get("use_project_context", True),
                },
        )
        messages.success(request, "Prompts importiert")
        return redirect("admin_prompts")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Prompts importieren")
    return render(
        request,
        "admin_prompt_import.html",
        {"form": form, "breadcrumbs": breadcrumbs},
    )


@login_required
@admin_required
def admin_models(request):
    """ErmÃ¶glicht die Auswahl der Standard-LLM-Modelle."""
    cfg = LLMConfig.objects.first() or LLMConfig.objects.create()
    if request.method == "POST":
        cfg.default_model = request.POST.get("default_model", cfg.default_model)
        cfg.gutachten_model = request.POST.get("gutachten_model", cfg.gutachten_model)
        cfg.anlagen_model = request.POST.get("anlagen_model", cfg.anlagen_model)
        cfg.vision_model = request.POST.get("vision_model", cfg.vision_model)
        cfg.models_changed = False
        cfg.save()
        return redirect("admin_models")
    if cfg.models_changed:
        cfg.models_changed = False
        cfg.save(update_fields=["models_changed"])
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "LLM-Modelle")
    context = {"config": cfg, "models": LLMConfig.get_available(), "breadcrumbs": breadcrumbs}
    return render(request, "admin_models.html", context)


@staff_member_required
def config_export_import_view(request: HttpRequest) -> HttpResponse:
    """Exportiert und importiert Konfigurationen Ã¼ber das Admin-Interface."""

    if request.method == "POST" and "export" in request.POST:
        buffer = io.StringIO()
        call_command("export_configs", stdout=buffer)
        buffer.seek(0)
        resp = HttpResponse(buffer.read(), content_type="application/json")
        resp["Content-Disposition"] = "attachment; filename=configs.json"
        return resp

    if request.method == "POST" and request.FILES.get("config_file"):
        tmp = NamedTemporaryFile(delete=False)
        for chunk in request.FILES["config_file"].chunks():
            tmp.write(chunk)
        tmp_path = tmp.name
        tmp.close()
        try:
            call_command("import_configs", tmp_path)
            messages.success(request, "Konfigurationen importiert")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, f"Import fehlgeschlagen: {exc}")
        finally:
            os.unlink(tmp_path)
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Konfigurationen")
    return render(request, "admin/config_transfer.html", {"breadcrumbs": breadcrumbs})


@login_required
@admin_required
def admin_anlage1(request):
    """Konfiguriert Fragen fÃ¼r Anlage 1."""
    questions = list(
        Anlage1Question.objects.all().prefetch_related("variants").order_by("num")
    )
    if request.method == "POST":
        for q in questions:
            if request.POST.get(f"delete{q.id}"):
                q.delete()
                continue
            q.parser_enabled = bool(request.POST.get(f"parser_enabled{q.id}"))
            q.llm_enabled = bool(request.POST.get(f"llm_enabled{q.id}"))
            q.text = request.POST.get(f"text{q.id}", q.text)
            q.save()
            for v in list(q.variants.all()):
                if request.POST.get(f"delvar{v.id}"):
                    v.delete()
                    continue
                v.text = request.POST.get(f"variant{v.id}", v.text)
                v.save()
            new_var = request.POST.get(f"new_variant{q.id}")
            if new_var:
                Anlage1QuestionVariant.objects.create(question=q, text=new_var)
        new_text = request.POST.get("new_text")
        if new_text:
            num = questions[-1].num + 1 if questions else 1
            Anlage1Question.objects.create(
                num=num,
                text=new_text,
                parser_enabled=bool(request.POST.get("new_parser_enabled")),
                llm_enabled=bool(request.POST.get("new_llm_enabled")),
            )
        return redirect("admin_anlage1")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Anlage 1")
    context = {"questions": questions, "breadcrumbs": breadcrumbs}
    return render(request, "admin_anlage1.html", context)


@login_required
@admin_required
def admin_anlage1_export(request):
    """Exportiert alle Anlage-1-Fragen als JSON-Datei."""
    questions = (
        Anlage1Question.objects.all().prefetch_related("variants").order_by("num")
    )
    items = [
        {
            "text": q.text,
            "variants": [v.text for v in q.variants.all()],
            "parser_enabled": q.parser_enabled,
            "llm_enabled": q.llm_enabled,
        }
        for q in questions
    ]
    content = json.dumps(items, ensure_ascii=False, indent=2)
    response = HttpResponse(content, content_type="application/json")
    response["Content-Disposition"] = "attachment; filename=anlage1_questions.json"
    return response


@login_required
@admin_required
def admin_anlage1_import(request):
    """Importiert Anlage-1-Fragen aus einer JSON-Datei."""
    form = Anlage1ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(raw)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("admin_anlage1_import")
        if form.cleaned_data.get("clear_first"):
            Anlage1Question.objects.all().delete()
        for idx, item in enumerate(items, start=1):
            obj, _ = Anlage1Question.objects.update_or_create(
                text=item.get("text", ""),
                defaults={
                    "num": idx,
                    "parser_enabled": item.get("parser_enabled", True),
                    "llm_enabled": item.get("llm_enabled", True),
                    "enabled": True,
                },
            )
            obj.variants.all().delete()
            for v_text in item.get("variants", []):
                Anlage1QuestionVariant.objects.create(question=obj, text=v_text)
        messages.success(request, "Fragen importiert")
        return redirect("admin_anlage1")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Anlage 1 importieren")
    return render(
        request,
        "admin_anlage1_import.html",
        {"form": form, "breadcrumbs": breadcrumbs},
    )


@login_required
@admin_required
def admin_project_statuses(request):
    """Zeigt alle vorhandenen Projektstatus an."""
    statuses = list(ProjectStatus.objects.all().order_by("ordering", "name"))
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Projekt-Status")
    context = {"statuses": statuses, "breadcrumbs": breadcrumbs}
    return render(request, "admin_project_statuses.html", context)


@login_required
@admin_required
def admin_project_status_export(request):
    """Exportiert alle Projektstatus als JSON-Datei."""
    items = [
        {
            "name": s.name,
            "key": s.key,
            "ordering": s.ordering,
            "is_default": s.is_default,
            "is_done_status": s.is_done_status,
        }
        for s in ProjectStatus.objects.all().order_by("ordering", "name")
    ]
    content = json.dumps(items, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=project_statuses.json"
    return resp


@login_required
@admin_required
def admin_project_status_import(request):
    """Importiert Projektstatus aus einer JSON-Datei."""
    form = ProjectStatusImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(raw)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("admin_project_status_import")
        for item in items:
            key = item.get("key")
            if not key:
                continue
            ProjectStatus.objects.update_or_create(
                key=key,
                defaults={
                    "name": item.get("name", ""),
                    "ordering": item.get("ordering", 0),
                    "is_default": item.get("is_default", False),
                    "is_done_status": item.get("is_done_status", False),
                },
            )
        messages.success(request, "Statusdaten importiert")
        return redirect("admin_project_statuses")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Status importieren")
    return render(
        request,
        "admin_project_status_import.html",
        {"form": form, "breadcrumbs": breadcrumbs},
    )


@login_required
@admin_required
def admin_project_status_form(request, pk=None):
    """Erstellt oder bearbeitet einen Projektstatus."""
    status = get_object_or_404(ProjectStatus, pk=pk) if pk else None
    form = ProjectStatusForm(request.POST or None, instance=status)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("admin_project_statuses")
    breadcrumbs = build_breadcrumbs(
        ADMIN_ROOT, "Status bearbeiten" if pk else "Status anlegen"
    )
    context = {"form": form, "status": status, "breadcrumbs": breadcrumbs}
    return render(request, "admin_project_status_form.html", context)


@login_required
@admin_required
@require_POST
def admin_project_status_delete(request, pk):
    """LÃ¶scht einen Projektstatus."""
    status = get_object_or_404(ProjectStatus, pk=pk)
    status.delete()
    return redirect("admin_project_statuses")


@login_required
@admin_required
def admin_llm_roles(request):
    """Liste aller vorhandenen LLM-Rollen."""
    roles = list(LLMRole.objects.all().order_by("name"))
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "LLM-Rollen")
    context = {"roles": roles, "breadcrumbs": breadcrumbs}
    return render(request, "admin_llm_roles.html", context)


@login_required
@admin_required
def admin_llm_role_form(request, pk=None):
    """Erstellt oder bearbeitet eine LLM-Rolle."""
    role = get_object_or_404(LLMRole, pk=pk) if pk else None
    form = LLMRoleForm(request.POST or None, instance=role)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("admin_llm_roles")
    breadcrumbs = build_breadcrumbs(
        ADMIN_ROOT, "LLM-Rolle bearbeiten" if pk else "LLM-Rolle anlegen"
    )
    context = {"form": form, "role": role, "breadcrumbs": breadcrumbs}
    return render(request, "admin_llm_role_form.html", context)


@login_required
@admin_required
@require_POST
def admin_llm_role_delete(request, pk):
    """LÃ¶scht eine LLM-Rolle."""
    role = get_object_or_404(LLMRole, pk=pk)
    role.delete()
    return redirect("admin_llm_roles")


@login_required
@admin_required
def admin_llm_role_export(request):
    """Exportiert alle LLM-Rollen als JSON-Datei."""
    roles = [
        {
            "name": r.name,
            "role_prompt": r.role_prompt,
            "is_default": r.is_default,
        }
        for r in LLMRole.objects.all().order_by("name")
    ]
    content = json.dumps(roles, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=llm_roles.json"
    return resp


@login_required
@admin_required
def admin_llm_role_import(request):
    """Importiert LLM-Rollen aus einer JSON-Datei."""
    form = LLMRoleImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(data)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("admin_llm_role_import")
        for item in items:
            LLMRole.objects.update_or_create(
                name=item.get("name", ""),
                defaults={
                    "role_prompt": item.get("role_prompt", ""),
                    "is_default": item.get("is_default", False),
                },
            )
        messages.success(request, "LLM-Rollen importiert")
        return redirect("admin_llm_roles")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "LLM-Rollen importieren")
    context = {"form": form, "breadcrumbs": breadcrumbs}
    return render(request, "admin_llm_role_import.html", context)


@login_required
@admin_required
def admin_user_list(request):
    """Listet alle Benutzer mit zugehÃ¶rigen Gruppen und Tiles auf."""
    users = list(User.objects.all().prefetch_related("groups", "tiles"))
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Benutzer")
    context = {"users": users, "breadcrumbs": breadcrumbs}
    return render(request, "admin_user_list.html", context)


@login_required
@admin_required
def admin_edit_user_permissions(request, user_id):
    """Bearbeitet Gruppen- und Tile-Zuordnungen fÃ¼r einen Benutzer."""
    user_obj = get_object_or_404(User, pk=user_id)
    form = UserPermissionsForm(request.POST or None, user=user_obj)
    if request.method == "POST" and form.is_valid():
        user_obj.groups.set(form.cleaned_data.get("groups"))
        user_obj.tiles.set(form.cleaned_data.get("tiles"))
        messages.success(request, "Berechtigungen gespeichert")
        return redirect("admin_user_list")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Benutzerrechte")
    context = {"form": form, "user_obj": user_obj, "breadcrumbs": breadcrumbs}
    return render(request, "admin_user_permissions_form.html", context)


@login_required
@admin_required
def admin_export_users_permissions(request):
    """Exportiert Benutzer, Gruppen und Tile-Zuordnungen als JSON."""
    users = (
        User.objects.all()
        .prefetch_related("groups", "tiles", "userareaaccess_set__area")
        .order_by("username")
    )
    data = []
    for user in users:
        group_tiles = Tile.objects.filter(groups__in=user.groups.all()).values_list(
            "url_name", flat=True
        )
        group_areas = Area.objects.filter(groups__in=user.groups.all()).values_list(
            "slug", flat=True
        )
        user_areas = Area.objects.filter(
            userareaaccess__user=user
        ).values_list("slug", flat=True)
        tiles = set(user.tiles.values_list("url_name", flat=True)) | set(group_tiles)


        areas = set(user_areas) | set(group_areas)
        data.append(
            {
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "groups": [g.name for g in user.groups.all()],
                "areas": sorted(areas),
                "tiles": sorted(tiles),
            }
        )
    content = json.dumps(data, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=users.json"
    return resp


@login_required
@admin_required
def admin_import_users_permissions(request):
    """Importiert Benutzer, Gruppen und Tile-Zuordnungen aus JSON."""
    form = UserImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            users = json.loads(raw)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("admin_import_users_permissions")
        for item in users:
            username = item.get("username")
            if not username:
                continue
            user_obj, created = User.objects.update_or_create(
                username=username,
                defaults={
                    "email": item.get("email", ""),
                    "first_name": item.get("first_name", ""),
                    "last_name": item.get("last_name", ""),
                    "is_active": item.get("is_active", True),
                    "is_staff": item.get("is_staff", False),
                },
            )
            if created:
                user_obj.set_unusable_password()
                user_obj.save(update_fields=["password"])

            group_qs = Group.objects.filter(name__in=item.get("groups", []))
            tile_qs = Tile.objects.filter(url_name__in=item.get("tiles", []))
            user_obj.groups.set(group_qs)
            user_obj.tiles.set(tile_qs)
        messages.success(request, "Benutzerdaten importiert")
        return redirect("admin_user_list")
    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Benutzer importieren")
    return render(
        request,
        "admin_user_import.html",
        {"form": form, "breadcrumbs": breadcrumbs},
    )


@login_required
@admin_required
def admin_anlage2_config_export(request):
    """Exportiert die komplette Anlage-2-Konfiguration als JSON."""
    cfg = Anlage2Config.get_instance()
    alias_headings = cfg.headers.all().values("field_name", "text")
    rules = AntwortErkennungsRegel.objects.all().order_by("prioritaet")
    a4_cfg = Anlage4ParserConfig.objects.first() or Anlage4ParserConfig.objects.create()

    cfg_data = {
        "enforce_subquestion_override": cfg.enforce_subquestion_override,
        "parser_mode": cfg.parser_mode,
        "parser_order": cfg.parser_order,
    }
    for key, _ in PHRASE_TYPE_CHOICES:
        cfg_data[f"text_{key}"] = getattr(cfg, f"text_{key}")

    rules_data = [
        {
            "regel_name": r.regel_name,
            "erkennungs_phrase": r.erkennungs_phrase,
            "regel_anwendungsbereich": r.regel_anwendungsbereich,
            "actions": r.actions_json,
            "prioritaet": r.prioritaet,
        }
        for r in rules
    ]

    a4_data = {
        "table_columns": a4_cfg.table_columns,
        "delimiter_phrase": a4_cfg.delimiter_phrase,
        "gesellschaften_phrase": a4_cfg.gesellschaften_phrase,
        "fachbereiche_phrase": a4_cfg.fachbereiche_phrase,
        "name_aliases": a4_cfg.name_aliases,
        "gesellschaft_aliases": a4_cfg.gesellschaft_aliases,
        "fachbereich_aliases": a4_cfg.fachbereich_aliases,
        "negative_patterns": a4_cfg.negative_patterns,
    }

    data = {
        "config": cfg_data,
        "alias_headings": list(alias_headings),
        "answer_rules": rules_data,
        "a4_parser": a4_data,
    }

    content = json.dumps(data, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=anlage2_config.json"
    return resp


@login_required
@admin_required
def admin_anlage2_config_import(request):
    """Importiert SpaltenÃ¼berschriften aus JSON."""
    form = Anlage2ConfigImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(raw)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("admin_anlage2_config_import")

        cfg = Anlage2Config.get_instance()

        cfg_fields = items.get("config", {})
        updated_fields: list[str] = []
        base_fields = [
            "enforce_subquestion_override",
            "parser_mode",
            "parser_order",
        ]
        phrase_fields = [f"text_{key}" for key, _ in PHRASE_TYPE_CHOICES]
        for field in base_fields + phrase_fields:
            if field in cfg_fields:
                setattr(cfg, field, cfg_fields[field])
                updated_fields.append(field)
        if updated_fields:
            cfg.save(update_fields=updated_fields)

        alias_headings_data = items.get("alias_headings", [])
        for h in alias_headings_data:
            Anlage2ColumnHeading.objects.update_or_create(
                config=cfg,
                field_name=h.get("field_name"),
                defaults={"text": h.get("text", "")},
            )

        rules_data = items.get("answer_rules", [])
        for r in rules_data:
            AntwortErkennungsRegel.objects.update_or_create(
                regel_name=r.get("regel_name"),
                defaults={
                    "erkennungs_phrase": r.get("erkennungs_phrase", ""),
                    "regel_anwendungsbereich": r.get(
                        "regel_anwendungsbereich",
                        "Hauptfunktion",
                    ),
                    "actions_json": r.get("actions", []),
                    "prioritaet": r.get("prioritaet", 0),
                },
            )

        a4_data = items.get("a4_parser", {})
        if a4_data:
            a4_cfg = (
                Anlage4ParserConfig.objects.first()
                or Anlage4ParserConfig.objects.create()
            )
            updated_a4_fields: list[str] = []
            for field in [
                "table_columns",
                "delimiter_phrase",
                "gesellschaften_phrase",
                "fachbereiche_phrase",
                "name_aliases",
                "gesellschaft_aliases",
                "fachbereich_aliases",
                "negative_patterns",
            ]:
                if field in a4_data:
                    setattr(a4_cfg, field, a4_data[field])
                    updated_a4_fields.append(field)
            if updated_a4_fields:
                a4_cfg.save(update_fields=updated_a4_fields)

        messages.success(request, "Konfiguration importiert")
        return redirect("anlage2_config")
    breadcrumbs = build_breadcrumbs(
        ADMIN_ROOT, "Anlage 2 Konfiguration importieren"
    )
    return render(
        request,
        "admin_anlage2_config_import.html",
        {"form": form, "breadcrumbs": breadcrumbs},
    )


@login_required
@admin_required
def anlage2_config(request):
    """Konfiguriert Ãœberschriften und globale Phrasen fÃ¼r AnlageÂ 2."""
    cfg = Anlage2Config.get_instance()
    aliases = list(cfg.headers.all())
    rules_qs = AntwortErkennungsRegel.objects.all().order_by("prioritaet")
    raw_actions = {r.pk: r.actions_json for r in rules_qs}
    for r in rules_qs:
        detail_logger.debug("Lade Regel %s actions_json=%r", r.pk, r.actions_json)
    a4_parser_cfg = (
        Anlage4ParserConfig.objects.first() or Anlage4ParserConfig.objects.create()
    )
    RuleFormSet = modelformset_factory(
        AntwortErkennungsRegel,
        form=AntwortErkennungsRegelForm,
        can_delete=True,
        can_order=True,
        extra=0,
    )
    RuleFormSetFB = modelformset_factory(
        AntwortErkennungsRegel,
        form=AntwortErkennungsRegelForm,
        can_delete=True,
        can_order=True,
        extra=1,
    )
    ActionFormSet = formset_factory(ActionForm, can_delete=True, extra=1)
    active_tab = request.POST.get("active_tab") or request.GET.get("tab") or "table"

    if request.method == "POST":
        action = request.POST.get("action") or "save_general"
        admin_a2_logger.debug("Aktion %s ausgelÃ¶st", action)

        if action == "save_table":
            admin_a2_logger.debug("Speichere Tabellen-Parser Konfiguration")
            for h in aliases:
                if request.POST.get(f"delete{h.id}"):
                    admin_a2_logger.debug(
                        "LÃ¶sche Ãœberschrift %s -> %s", h.field_name, h.text
                    )
                    h.delete()
            new_field = request.POST.get("new_field")
            new_text = request.POST.get("new_text")
            if new_field and new_text:
                Anlage2ColumnHeading.objects.create(
                    config=cfg, field_name=new_field, text=new_text
                )
                admin_a2_logger.debug("Neue Ãœberschrift %s -> %s", new_field, new_text)
            return redirect(f"{reverse('anlage2_config')}?tab=table")

        if action == "save_rules":
            admin_a2_logger.debug("Speichere Antwortregeln")
            formset = RuleFormSet(request.POST, queryset=rules_qs, prefix="rules")
            if formset.is_valid():
                ordered = formset.ordered_forms
                for idx, form in enumerate(ordered):
                    if form.cleaned_data.get("DELETE"):
                        if form.instance.pk:
                            form.instance.delete()
                        continue
                    obj = form.save(commit=False)
                    obj.prioritaet = idx
                    obj.save()
                for form in formset.deleted_forms:
                    form.instance.delete()
                messages.success(request, "Antwortregeln gespeichert")
            else:
                messages.error(request, "UngÃ¼ltige Eingaben")

            if request.headers.get("HX-Request"):
                formset = RuleFormSet(queryset=rules_qs, prefix="rules")
                context = {"rule_formset": formset}
                return render(request, "partials/_response_rules_table.html", context)
            return redirect(f"{reverse('anlage2_config')}?tab=rules")

        if action in ["save_rules_fb", "add_action_row"]:
            admin_a2_logger.debug("Speichere/erweitere Antwortregeln (Fallback)")
            data = request.POST.copy()
            if action == "add_action_row":
                target_prefix = data.get("action_prefix")
                if target_prefix:
                    key = f"{target_prefix}-TOTAL_FORMS"
                    data[key] = str(int(data.get(key, 0)) + 1)
            formset = RuleFormSetFB(data, queryset=rules_qs, prefix="rules_fb")
            action_formsets = {}
            for f in formset.forms:
                a_prefix = f"{f.prefix}-actions"
                action_formsets[f.prefix] = ActionFormSet(data, prefix=a_prefix)

            if (
                action == "save_rules_fb"
                and formset.is_valid()
                and all(fs.is_valid() for fs in action_formsets.values())
            ):
                ordered = formset.ordered_forms
                for idx, form in enumerate(ordered):
                    if form.cleaned_data.get("DELETE"):
                        if form.instance.pk:
                            form.instance.delete()
                        continue
                    obj = form.save(commit=False)
                    obj.prioritaet = idx
                    afs = action_formsets[form.prefix]
                    actions = []
                    for ad in afs.cleaned_data:
                        if ad.get("DELETE"):
                            continue
                        actions.append(
                            {"field": ad.get("field"), "value": ad.get("value")}
                        )
                    obj.actions_json = actions
                    obj.save()
                for form in formset.deleted_forms:
                    form.instance.delete()
                messages.success(request, "Antwortregeln gespeichert")
                return redirect(f"{reverse('anlage2_config')}?tab=rules2")
            else:
                if action == "save_rules_fb":
                    messages.error(
                        request, "Bitte korrigieren Sie die markierten Felder."
                    )
                rule_formset_fb = formset
                rule_action_formsets = action_formsets
                active_tab = "rules2"

        if action == "save_general":
            admin_a2_logger.debug("Speichere Allgemeine Einstellungen")
            cfg_form = Anlage2ConfigForm(request.POST, instance=cfg)
            if cfg_form.is_valid():
                admin_a2_logger.debug(
                    "Ge\u00e4nderte Felder: %r",
                    {f: cfg_form.cleaned_data[f] for f in cfg_form.changed_data},
                )
                cfg_form.save()
                messages.success(request, "Einstellungen gespeichert")
                return redirect(f"{reverse('anlage2_config')}?tab=general")
            messages.error(request, "Bitte korrigieren Sie die markierten Felder.")
            active_tab = "general"

        if action == "save_a4":
            admin_a2_logger.debug("Speichere Anlage4 Parser Konfiguration")
            form = Anlage4ParserConfigForm(request.POST, instance=a4_parser_cfg)
            if form.is_valid():
                form.save()
                messages.success(request, "Anlage 4 gespeichert")
                return redirect(f"{reverse('anlage2_config')}?tab=a4")
            a4_parser_form = form
            active_tab = "a4"

    cfg_form = cfg_form if "cfg_form" in locals() else Anlage2ConfigForm(instance=cfg)
    rule_formset = RuleFormSet(queryset=rules_qs, prefix="rules")
    for f in rule_formset:
        detail_logger.debug(
            "Formset Rule PK=%s initial actions_json=%r",
            f.instance.pk,
            f.initial.get("actions_json"),
        )
    rule_formset_fb = (
        rule_formset_fb
        if "rule_formset_fb" in locals()
        else RuleFormSetFB(queryset=rules_qs, prefix="rules_fb")
    )
    for f in rule_formset_fb:
        detail_logger.debug(
            "Formset FB Rule PK=%s initial actions_json=%r",
            f.instance.pk,
            f.initial.get("actions_json"),
        )
    rule_action_formsets = (
        rule_action_formsets
        if "rule_action_formsets" in locals()
        else {
            f.prefix: ActionFormSet(
                prefix=f"{f.prefix}-actions",
                initial=raw_actions.get(f.instance.pk, []),
            )
            for f in rule_formset_fb.forms
        }
    )
    a4_parser_form = (
        a4_parser_form
        if "a4_parser_form" in locals()
        else Anlage4ParserConfigForm(instance=a4_parser_cfg)
    )
    context = {
        "config": cfg,
        "config_form": cfg_form,
        "aliases": aliases,
        "rule_formset": rule_formset,
        "rule_formset_fb": rule_formset_fb,
        "action_formsets": rule_action_formsets,
        "raw_actions": raw_actions,
        "choices": Anlage2ColumnHeading.FIELD_CHOICES,
        "parser_choices": get_parser_choices(),
        "active_tab": active_tab,
        "a4_parser_form": a4_parser_form,
    }
    return render(request, "admin_anlage2_config.html", context)


@login_required
@admin_required
@require_http_methods(["GET"])
def anlage2_rule_add(request):
    """Liefert eine leere Formularzeile fÃ¼r eine Antwortregel."""
    if not request.headers.get("HX-Request"):
        return redirect("anlage2_config")
    index = int(request.GET.get("index", 0))
    RuleFormSet = modelformset_factory(
        AntwortErkennungsRegel,
        form=AntwortErkennungsRegelForm,
        can_delete=True,
        can_order=True,
        extra=0,
    )
    formset = RuleFormSet(
        queryset=AntwortErkennungsRegel.objects.none(), prefix="rules"
    )
    form = formset.empty_form
    form.prefix = f"rules-{index}"
    context = {"form": form}
    return render(request, "partials/_response_rule_row.html", context)


@login_required
@admin_required
@require_http_methods(["DELETE"])
def anlage2_rule_delete(request, pk: int):
    """LÃ¶scht eine Antwortregel."""
    rule = get_object_or_404(AntwortErkennungsRegel, pk=pk)
    rule.delete()
    return HttpResponse(status=204)


@login_required
@admin_required
def anlage4_config(request):
    """Konfiguriert den Anlage-4-Parser."""
    cfg = Anlage4ParserConfig.objects.first() or Anlage4ParserConfig.objects.create()
    form = Anlage4ParserConfigForm(request.POST or None, instance=cfg)
    if request.method == "POST" and form.is_valid():
        neg_list = request.POST.getlist("negative_patterns")
        alias_lists = {
            "name_aliases": request.POST.getlist("name_aliases"),
            "gesellschaft_aliases": request.POST.getlist("gesellschaft_aliases"),
            "fachbereich_aliases": request.POST.getlist("fachbereich_aliases"),
        }
        columns = request.POST.getlist("table_columns")
        form.save(
            negative_patterns=neg_list,
            alias_lists=alias_lists,
            table_columns=columns,
        )
        messages.success(request, "Anlage 4 gespeichert")
        return redirect("anlage4_config")
    return render(request, "admin_anlage4_config.html", {"form": form})


@login_required
@admin_required
def admin_role_editor(request):
    """Bearbeitet die Sichtbarkeit von Tiles pro Rolle."""

    groups = list(Group.objects.all().order_by("name"))
    group_id = request.POST.get("group_id") or request.GET.get("group")
    selected_group = None
    tiles_by_area: dict[Area, list[dict[str, Any]]] = {}

    if group_id:
        selected_group = get_object_or_404(Group, pk=group_id)

    if request.method == "POST" and selected_group:
        selected_tiles = Tile.objects.filter(pk__in=request.POST.getlist("tiles"))
        selected_group.tile_set.set(selected_tiles)
        messages.success(request, "Kachel-Zuordnung gespeichert")
        return redirect(f"{reverse('admin_role_editor')}?group={selected_group.id}")

    if selected_group:
        group_tile_ids = set(selected_group.tile_set.values_list("id", flat=True))
        for area in Area.objects.all():
            tile_items = []
            for tile in Tile.objects.filter(areas=area):
                tile_items.append({"tile": tile, "checked": tile.id in group_tile_ids})
            tiles_by_area[area] = tile_items

    breadcrumbs = build_breadcrumbs(ADMIN_ROOT, "Rollen & Rechte")
    context = {
        "groups": groups,
        "selected_group": selected_group,
        "tiles_by_area": tiles_by_area,
        "breadcrumbs": breadcrumbs,
    }
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "partials/_role_tile_form.html", context)
    return render(request, "admin_roles.html", context)


@login_required
@admin_required
def anlage2_function_list(request):
    """Zeigt alle Anlage-2-Funktionen."""
    functions = list(Anlage2Function.objects.all().order_by("name"))
    context = {"functions": functions}
    return render(request, "anlage2/function_list.html", context)


@login_required
@admin_required
def anlage2_function_form(request, pk=None):
    """Erstellt oder bearbeitet eine Anlage-2-Funktion."""
    funktion = get_object_or_404(Anlage2Function, pk=pk) if pk else None
    form = Anlage2FunctionForm(request.POST or None, instance=funktion)

    if request.method == "POST" and form.is_valid():
        aliases = request.POST.getlist("name_aliases")
        funktion = form.save(name_aliases=aliases)
        return redirect("anlage2_function_edit", funktion.pk)

    subquestions = list(funktion.anlage2subquestion_set.all()) if funktion else []
    aliases = funktion.detection_phrases.get("name_aliases", []) if funktion else []
    context = {
        "form": form,
        "funktion": funktion,
        "subquestions": subquestions,
        "aliases": aliases,
    }
    return render(request, "anlage2/function_form.html", context)


@login_required
@admin_required
def anlage2_function_delete(request, pk):
    """LÃ¶scht eine Anlage-2-Funktion."""
    if request.method != "POST":
        return HttpResponseBadRequest()
    funktion = get_object_or_404(Anlage2Function, pk=pk)
    funktion.delete()
    return redirect("anlage2_function_list")


@login_required
@admin_required
def anlage2_function_import(request: HttpRequest) -> HttpResponse:
    """Importiert den Funktionskatalog aus einer JSON-Datei."""
    form = Anlage2FunctionImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(data)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("anlage2_function_import")
        if form.cleaned_data["clear_first"]:
            Anlage2SubQuestion.objects.all().delete()
            Anlage2Function.objects.all().delete()
        for entry in items:
            name = entry.get("name") or entry.get("funktion") or ""
            func, _ = Anlage2Function.objects.get_or_create(name=name)
            func.detection_phrases = func.detection_phrases or {}
            func.detection_phrases["name_aliases"] = entry.get("name_aliases", [])
            func.save()
            subs = entry.get("subquestions") or entry.get("unterfragen") or []
            for sub in subs:
                if isinstance(sub, dict):
                    text = sub.get("frage_text") or sub.get("frage") or ""
                    vals = sub
                else:
                    text = str(sub)
                    vals = {}
                sq = Anlage2SubQuestion.objects.create(
                    funktion=func,
                    frage_text=text,
                )
                sq.detection_phrases = sq.detection_phrases or {}
                sq.detection_phrases["name_aliases"] = vals.get("name_aliases", [])
                sq.save()
        messages.success(request, "Funktionskatalog importiert")
        return redirect("anlage2_function_list")
    return render(request, "anlage2/function_import.html", {"form": form})


@login_required
@admin_required
def anlage2_function_export(request: HttpRequest) -> HttpResponse:
    """Exportiert den aktuellen Funktionskatalog als JSON."""
    functions: list[dict[str, Any]] = []
    for f in Anlage2Function.objects.all().order_by("name"):
        item = {
            "name": f.name,
            "name_aliases": f.detection_phrases.get("name_aliases", []),
            "subquestions": [],
        }
        for q in f.anlage2subquestion_set.all().order_by("id"):
            item["subquestions"].append(
                {
                    "frage_text": q.frage_text,
                    "name_aliases": q.detection_phrases.get("name_aliases", []),
                }
            )
        functions.append(item)
    content = json.dumps(functions, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=anlage2_functions.json"
    return resp


@login_required
@admin_required
def anlage2_subquestion_form(request, function_pk=None, pk=None):
    """Erstellt oder bearbeitet eine Unterfrage."""
    if pk:
        subquestion = get_object_or_404(Anlage2SubQuestion, pk=pk)
        funktion = subquestion.funktion
    else:
        funktion = get_object_or_404(Anlage2Function, pk=function_pk)
        subquestion = Anlage2SubQuestion(funktion=funktion)
    form = Anlage2SubQuestionForm(request.POST or None, instance=subquestion)

    if request.method == "POST" and form.is_valid():
        aliases = request.POST.getlist("name_aliases")
        subquestion = form.save(name_aliases=aliases)
        return redirect("anlage2_function_edit", funktion.pk)

    aliases = subquestion.detection_phrases.get("name_aliases", []) if pk else []
    context = {
        "form": form,
        "funktion": funktion,
        "subquestion": subquestion if pk else None,
        "aliases": aliases,
    }
    return render(request, "anlage2/subquestion_form.html", context)


@login_required
@admin_required
def anlage2_subquestion_delete(request, pk):
    """LÃ¶scht eine Unterfrage."""
    if request.method != "POST":
        return HttpResponseBadRequest()
    sub = get_object_or_404(Anlage2SubQuestion, pk=pk)
    func_pk = sub.funktion_id
    sub.delete()
    return redirect("anlage2_function_edit", func_pk)


class AntwortErkennungsRegelListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    """Listet alle Regeln fÃ¼r den exakten Parser auf."""

    model = AntwortErkennungsRegel
    template_name = "parser_rules/rule_list.html"
    context_object_name = "rules"


class AntwortErkennungsRegelCreateView(
    LoginRequiredMixin, StaffRequiredMixin, CreateView
):
    """Erstellt eine neue Antwortregel."""

    model = AntwortErkennungsRegel
    form_class = AntwortErkennungsRegelForm
    template_name = "parser_rules/rule_form.html"
    success_url = reverse_lazy("parser_rule_list")

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)


class AntwortErkennungsRegelUpdateView(
    LoginRequiredMixin, StaffRequiredMixin, UpdateView
):
    """Bearbeitet eine bestehende Antwortregel."""

    model = AntwortErkennungsRegel
    form_class = AntwortErkennungsRegelForm
    template_name = "parser_rules/rule_form.html"
    success_url = reverse_lazy("parser_rule_list")

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)


class AntwortErkennungsRegelDeleteView(
    LoginRequiredMixin, StaffRequiredMixin, DeleteView
):
    """LÃ¶scht eine Antwortregel."""

    model = AntwortErkennungsRegel
    template_name = "parser_rules/rule_confirm_delete.html"
    success_url = reverse_lazy("parser_rule_list")


@login_required
@admin_required
def anlage2_parser_rule_export(request):
    """Exportiert alle Antwortregeln als JSON."""
    rules = [
        {
            "regel_name": r.regel_name,
            "erkennungs_phrase": r.erkennungs_phrase,
            "regel_anwendungsbereich": r.regel_anwendungsbereich,
            "actions": r.actions_json,
            "prioritaet": r.prioritaet,
        }
        for r in AntwortErkennungsRegel.objects.all().order_by("prioritaet")
    ]
    content = json.dumps(rules, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=parser_rules.json"
    return resp


@login_required
@admin_required
def anlage2_parser_rule_import(request):
    """Importiert Antwortregeln aus einer JSON-Datei."""
    form = Anlage2ParserRuleImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(raw)
        except Exception:  # noqa: BLE001
            messages.error(request, "UngÃ¼ltige JSON-Datei")
            return redirect("anlage2_parser_rule_import")
        for r in items:
            AntwortErkennungsRegel.objects.update_or_create(
                regel_name=r.get("regel_name"),
                defaults={
                    "erkennungs_phrase": r.get("erkennungs_phrase", ""),
                    "regel_anwendungsbereich": r.get(
                        "regel_anwendungsbereich", "Hauptfunktion"
                    ),
                    "actions_json": r.get("actions", []),
                    "prioritaet": r.get("prioritaet", 0),
                },
            )
        messages.success(request, "Antwortregeln importiert")
        return redirect("parser_rule_list")
    return render(request, "admin_anlage2_parser_rule_import.html", {"form": form})


@login_required
# @tile_required("projekt-verwaltung")
def projekt_list(request):
    projekte = BVProject.objects.all().order_by("-created_at")

    search_query = request.GET.get("q", "")
    if search_query:
        projekte = projekte.filter(title__icontains=search_query)

    software_filter = request.GET.get("software", "")
    if software_filter:
        projekte = projekte.filter(
            bvsoftware__name__icontains=software_filter
        ).distinct()

    status_filter = request.GET.get("status", "")
    if status_filter:
        projekte = projekte.filter(status__key=status_filter)

    context = {
        "projekte": projekte,
        "is_admin": request.user.groups.filter(name__iexact="admin").exists(),
        "search_query": search_query,
        "status_filter": status_filter,
        "software_filter": software_filter,
        "status_choices": ProjectStatus.objects.all(),
    }
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "partials/_project_list_rows.html", context)
    return render(request, "projekt_list.html", context)


@login_required
def projekt_detail(request, pk):
    projekt = get_object_or_404(BVProject, pk=pk)
    all_files = projekt.anlagen.all()
    reviewed = all_files.filter(manual_reviewed=True).count()
    is_admin = request.user.groups.filter(name__iexact="admin").exists()
    software_list = projekt.software_list
    knowledge_map = {k.software_name: k for k in projekt.softwareknowledge.all()}
    knowledge_rows = []
    checked = 0
    for name in software_list:
        entry = knowledge_map.get(name)
        if entry and entry.last_checked:
            checked += 1
        knowledge_rows.append({"name": name, "entry": entry})


    # Letzte AktivitÃ¤ten aus StatusÃ¤nderungen und Dateiuploads sammeln
    activities = []
    for h in projekt.status_history.order_by("-changed_at")[:5]:
        activities.append(
            {
                "time": h.changed_at,
                "text": f"Status geÃ¤ndert zu {h.status.name}",
            }
        )
    for f in projekt.anlagen.order_by("-created_at")[:5]:
        activities.append(
            {
                "time": f.created_at,
                "text": f"Anlage {f.anlage_nr} hochgeladen",
            }
        )
    activities.sort(key=lambda x: x["time"], reverse=True)
    activities = activities[:5]

    cockpit_ctx = get_cockpit_context(projekt)
    last_anlagen_files = {
        nr: projekt.anlagen.filter(anlage_nr=nr).last() for nr in range(1, 7)
    }

    can_gap_report = has_any_gap(projekt)

    breadcrumbs = [
        {"url": reverse("projekt_list"), "label": "Projekte"},
        {"label": projekt.title},
    ]

    context = {
        "projekt": projekt,
        "cockpit": cockpit_ctx,
        "status_choices": ProjectStatus.objects.all(),
        "history": projekt.status_history.all(),
        "num_attachments": all_files.count(),
        "num_reviewed": reviewed,
        "is_verhandlungsfaehig": projekt.is_verhandlungsfaehig,
        "is_admin": is_admin,
        "anlage_numbers": list(range(1, 7)),
        "last_anlagen_files": last_anlagen_files,
        "knowledge_rows": knowledge_rows,
        "knowledge_checked": checked,
        "total_software": len(software_list),
        "software_list": software_list,
        "activities": activities,
        "can_gap_report": can_gap_report,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "projekt_detail.html", context)


@login_required
def projekt_initial_pruefung(request, pk):
    projekt = get_object_or_404(BVProject, pk=pk)
    if not _user_can_edit_project(request.user, projekt):
        return HttpResponseForbidden("Nicht berechtigt")
    context = {"projekt": projekt}
    return render(request, "projekt_initial_pruefung.html", context)


@login_required
def anlage3_review(request, pk):
    """Zeigt alle Dateien der Anlage 3 mit Review-Option."""
    logger.info("anlage3_review gestartet fÃ¼r Projekt %s", pk)
    projekt = get_object_or_404(BVProject, pk=pk)
    anlagen = projekt.anlagen.filter(anlage_nr=3)
    context = {"projekt": projekt, "anlagen": anlagen}
    logger.info("anlage3_review beendet fÃ¼r Projekt %s", pk)
    return render(request, "anlage3_review.html", context)


@login_required
def anlage3_file_review(request, pk):
    """Zeigt erkannte Metadaten der Anlage 3 zur Best\u00e4tigung."""
    project_file = get_object_or_404(BVProjectFile, pk=pk)
    if project_file.anlage_nr != 3:
        raise Http404

    version = request.GET.get("version")
    if version and version.isdigit():
        alt = BVProjectFile.objects.filter(
            project=project_file.project,
            anlage_nr=project_file.anlage_nr,
            version=int(version),
        ).first()
        if alt:
            project_file = alt

    versions = list(
        BVProjectFile.objects.filter(
            project=project_file.project,
            anlage_nr=project_file.anlage_nr,
        ).order_by("version")
    )

    try:
        meta = project_file.anlage3meta
    except Anlage3Metadata.DoesNotExist:
        meta = Anlage3Metadata(project_file=project_file)

    if request.method == "POST":
        gap_form = BVGapNotesForm(request.POST, instance=project_file)
        if set(request.POST.keys()) <= {"csrfmiddlewaretoken", "gap_summary", "gap_notiz"}:
            if gap_form.is_valid():
                gap_form.save()
                return redirect("projekt_detail", pk=project_file.project.pk)
        form = Anlage3MetadataForm(request.POST, instance=meta)
        if form.is_valid() and gap_form.is_valid():
            form.save()
            gap_form.save()
            return redirect("projekt_detail", pk=project_file.project.pk)
    else:
        form = Anlage3MetadataForm(instance=meta)
        gap_form = BVGapNotesForm(instance=project_file)

    context = {
        "anlage": project_file,
        "form": form,
        "gap_form": gap_form,
        "versions": versions,
        "current_version": project_file.version,
    }
    return render(request, "projekt_file_anlage3_review.html", context)


@login_required
def anlage4_review(request, pk):
    """Zeigt die Auswertungen aus AnlageÂ 4 und ermÃ¶glicht die manuelle Bewertung."""
    project_file = get_object_or_404(BVProjectFile, pk=pk)
    if project_file.anlage_nr != 4:
        raise Http404

    version = request.GET.get("version")
    if version and version.isdigit():
        alt = BVProjectFile.objects.filter(
            project=project_file.project,
            anlage_nr=project_file.anlage_nr,
            version=int(version),
        ).first()
        if alt:
            project_file = alt

    versions = list(
        BVProjectFile.objects.filter(
            project=project_file.project,
            anlage_nr=project_file.anlage_nr,
        ).order_by("version")
    )

    anlage4_logger.info("Zugriff auf Anlage4 Review f\u00fcr Datei %s", pk)

    items = []
    if project_file.analysis_json:
        items = project_file.analysis_json.get("items") or []

    if request.method == "POST":
        gap_form = BVGapNotesForm(request.POST, instance=project_file)
        if set(request.POST.keys()) <= {"csrfmiddlewaretoken", "gap_summary", "gap_notiz"}:
            if gap_form.is_valid():
                gap_form.save()
                return redirect("projekt_detail", pk=project_file.project.pk)
        form = Anlage4ReviewForm(
            request.POST,
            items=items,
            initial=(project_file.analysis_json or {}).get("manual_review"),
        )
        if form.is_valid() and gap_form.is_valid():
            analysis = project_file.analysis_json or {}
            existing = analysis.get("manual_review", {})
            form_json = form.get_json()
            for idx in range(len(items)):
                key = str(idx)
                current = existing.get(key, {})
                if f"item{idx}_ok" in request.POST:
                    current["ok"] = form_json.get(key, {}).get("ok", False)
                if f"item{idx}_nego" in request.POST:
                    current["nego"] = form_json.get(key, {}).get("nego", False)
                if f"item{idx}_note" in request.POST:
                    current["note"] = form_json.get(key, {}).get("note", "")
                existing[key] = current
            analysis["manual_review"] = existing
            project_file.analysis_json = analysis
            gap_form.save()
            project_file.save(update_fields=["analysis_json"])
            anlage4_logger.info(
                "Anlage4 Review gespeichert: %s Eintr\u00e4ge", len(items)
            )
            return redirect("projekt_detail", pk=project_file.project.pk)
    else:
        form = Anlage4ReviewForm(
            initial=(project_file.analysis_json or {}).get("manual_review"),
            items=items,
        )
        gap_form = BVGapNotesForm(instance=project_file)

    rows = []
    for idx, item in enumerate(items):
        fields = item.get("structured", {})
        plaus = item.get("plausibility", {})
        rows.append(
            {
                "name": fields.get("name_der_auswertung"),
                "gesellschaften": fields.get("gesellschaften"),
                "fachbereiche": fields.get("fachbereiche"),
                "plaus": plaus.get("plausibilitaet"),
                "score": plaus.get("score"),
                "begruendung": plaus.get("begruendung"),
                "ok_field": form[f"item{idx}_ok"],
                "nego_field": form[f"item{idx}_nego"],
                "note_field": form[f"item{idx}_note"],
            }
        )

    anlage4_logger.debug("Tabellenzeilen f\u00fcr Anlage4 Review: %s", rows)

    context = {
        "anlage": project_file,
        "rows": rows,
        "gap_form": gap_form,
        "versions": versions,
        "current_version": project_file.version,
    }
    anlage4_logger.info("Anlage4 Review abgeschlossen fÃ¼r Datei %s", pk)
    return render(request, "projekt_file_anlage4_review.html", context)


@login_required
def anlage5_review(request, pk):
    """Zeigt die erkannten Zwecke aus Anlage 5 zur BestÃ¤tigung."""

    project_file = get_object_or_404(BVProjectFile, pk=pk)
    if project_file.anlage_nr != 5:
        raise Http404

    version = request.GET.get("version")
    if version and version.isdigit():
        alt = BVProjectFile.objects.filter(
            project=project_file.project,
            anlage_nr=project_file.anlage_nr,
            version=int(version),
        ).first()
        if alt:
            project_file = alt

    versions = list(
        BVProjectFile.objects.filter(
            project=project_file.project,
            anlage_nr=project_file.anlage_nr,
        ).order_by("version")
    )

    try:
        review = project_file.anlage5review
    except Anlage5Review.DoesNotExist:
        review = None

    initial = {}
    if review:
        initial["purposes"] = review.found_purposes.all()
        initial["sonstige"] = review.sonstige_zwecke

    if request.method == "POST":
        gap_form = BVGapNotesForm(request.POST, instance=project_file)
        if set(request.POST.keys()) <= {"csrfmiddlewaretoken", "gap_summary", "gap_notiz"}:
            if gap_form.is_valid():
                gap_form.save()
                return redirect("projekt_detail", pk=project_file.project.pk)
        form = Anlage5ReviewForm(request.POST)
        if form.is_valid() and gap_form.is_valid():
            if review is None:
                review = Anlage5Review.objects.create(project_file=project_file)
            review.sonstige_zwecke = form.cleaned_data["sonstige"]
            review.save(update_fields=["sonstige_zwecke"])
            review.found_purposes.set(form.cleaned_data["purposes"])
            project_file.verhandlungsfaehig = (
                review.found_purposes.count() == ZweckKategorieA.objects.count()
                and not review.sonstige_zwecke
            )
            gap_form.save()
            project_file.save(update_fields=["verhandlungsfaehig"])
            return redirect("projekt_detail", pk=project_file.project.pk)
    else:
        form = Anlage5ReviewForm(initial=initial)
        gap_form = BVGapNotesForm(instance=project_file)

    context = {
        "anlage": project_file,
        "form": form,
        "gap_form": gap_form,
        "versions": versions,
        "current_version": project_file.version,
    }
    return render(request, "projekt_file_anlage5_review.html", context)


@login_required
def projekt_upload(request):
    if request.method == "POST":
        form = BVProjectUploadForm(request.POST, request.FILES)
        if form.is_valid():
            docx_file = form.cleaned_data["docx_file"]
            from tempfile import NamedTemporaryFile

            tmp = NamedTemporaryFile(delete=False, suffix=".docx")
            for chunk in docx_file.chunks():
                tmp.write(chunk)
            tmp.close()
            text = extract_text(Path(tmp.name))
            Path(tmp.name).unlink(missing_ok=True)
            projekt = BVProject.objects.create(beschreibung=text)
            return redirect("projekt_edit", pk=projekt.pk)
    else:
        form = BVProjectUploadForm()
    return render(request, "projekt_upload.html", {"form": form})


@login_required
def projekt_create(request):
    software_list = request.POST.getlist("software_typen") if request.method == "POST" else []
    if request.method == "POST":
        form = BVProjectForm(request.POST)
        if form.is_valid():
            projekt = form.save(software_list=software_list)
            if hasattr(projekt, "user_id") and projekt.user_id is None:
                projekt.user = request.user
                projekt.save(update_fields=["user"])
            return redirect("projekt_detail", pk=projekt.pk)
    else:
        form = BVProjectForm()
    return render(request, "projekt_form.html", {"form": form, "software_list": software_list})


@login_required
def projekt_edit(request, pk):
    projekt = get_object_or_404(BVProject, pk=pk)
    software_list = (
        request.POST.getlist("software_typen")
        if request.method == "POST"
        else projekt.software_list
    )
    if request.method == "POST":
        form = BVProjectForm(request.POST, instance=projekt)
        if form.is_valid():
            projekt = form.save(software_list=software_list)
            return redirect("projekt_detail", pk=projekt.pk)
    else:
        form = BVProjectForm(instance=projekt)
    context = {
        "form": form,
        "projekt": projekt,
        "software_list": software_list,
        "categories": LLMConfig.get_categories(),
        "category": "default",
    }
    return render(request, "projekt_form.html", context)


def extract_anlage_nr(filename: str) -> int:
    """Extrahiert die Anlagen-Nummer aus dem Dateinamen.

    Erwartet Muster wie "Anlage_3_..." oder "anlage_3_...".
    """

    match = re.search(r"anlage[\s_-]?(\d)", filename, re.IGNORECASE)
    if match:
        nr = int(match.group(1))
        if 1 <= nr <= 6:
            return nr
    raise ValueError("Dateiname muss eine Anlagen-Nummer enthalten")


def _save_project_file(
    projekt: BVProject,
    form: BVProjectFileForm | None = None,
    *,
    upload=None,
    anlage_nr: int | None = None,
    copy_gap_fields: bool = False,
) -> BVProjectFile:
    """Speichert eine einzelne hochgeladene Datei.

    Kann entweder mit einem bereits validierten Formular oder direkt mit Datei
    und Anlagen-Nummer aufgerufen werden.
    ``copy_gap_fields`` steuert, ob GAP-Felder der Vorgängerversion
    übernommen werden.
    """

    if form is not None:
        uploaded = form.cleaned_data["upload"]
        anlage_nr = form.anlage_nr
    else:
        if upload is None or anlage_nr is None:
            raise ValueError("missing params")
        uploaded = upload

    obj = (
        form.save(commit=False) if form is not None else BVProjectFile(upload=uploaded)
    )

    ext = Path(uploaded.name).suffix.lower()
    if uploaded.size > settings.MAX_UPLOAD_SIZE:
        raise ValueError("Datei \u00fcberschreitet die maximale Gr\u00f6\u00dfe")
    if anlage_nr == 3:
        if ext not in [".docx", ".pdf"]:
            raise ValueError("Nur .docx oder .pdf erlaubt f\u00fcr Anlage 3")
    else:
        if ext != ".docx":
            raise ValueError("Nur .docx Dateien erlaubt")

    content = ""
    lower_name = uploaded.name.lower()
    if lower_name.endswith(".docx"):
        from tempfile import NamedTemporaryFile

        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        for chunk in uploaded.chunks():
            tmp.write(chunk)
        tmp.close()
        try:
            content = extract_text(Path(tmp.name))
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    elif lower_name.endswith(".pdf"):
        uploaded.read()
        uploaded.seek(0)
    else:
        try:
            content = uploaded.read().decode("utf-8")
        except UnicodeDecodeError as exc:
            logger.error("Datei konnte nicht als UTF-8 dekodiert werden: %s", exc)
            raise ValueError("invalid")

    obj.project = projekt
    obj.anlage_nr = anlage_nr
    obj.text_content = content
    obj.gap_summary = ""
    obj.gap_notiz = ""
    old_file = (
        BVProjectFile.objects.filter(
            project=projekt,
            anlage_nr=obj.anlage_nr,
            is_active=True,
        )
        .order_by("-version")
        .first()
    )
    if old_file:
        old_file.is_active = False
        old_file.save(update_fields=["is_active"])
        obj.version = old_file.version + 1
        obj.parent = old_file

    obj.save()
    if old_file:
        # Ãœbernahme vorhandener KI-PrÃ¼fergebnisse aus der VorgÃ¤ngerversion
        ai_results = FunktionsErgebnis.objects.filter(
            anlage_datei=old_file, quelle="ki"
        )
        if ai_results.exists():
            obj.processing_status = old_file.processing_status
            obj.save(update_fields=["processing_status"])

            meta_copies = [
                AnlagenFunktionsMetadaten(
                    anlage_datei=obj,
                    funktion=m.funktion,
                    subquestion=m.subquestion,
                    gap_summary=m.gap_summary if copy_gap_fields else "",
                    gap_notiz=m.gap_notiz if copy_gap_fields else "",
                    supervisor_notes=m.supervisor_notes,
                    is_negotiable=m.is_negotiable,
                    is_negotiable_manual_override=m.is_negotiable_manual_override,
                )
                for m in AnlagenFunktionsMetadaten.objects.filter(anlage_datei=old_file)
            ]
            if meta_copies:
                AnlagenFunktionsMetadaten.objects.bulk_create(meta_copies)

            fe_copies = [
                FunktionsErgebnis(
                    anlage_datei=obj,
                    funktion=r.funktion,
                    subquestion=r.subquestion,
                    quelle=r.quelle,
                    technisch_verfuegbar=r.technisch_verfuegbar,
                    einsatz_bei_telefonica=r.einsatz_bei_telefonica,
                    zur_lv_kontrolle=r.zur_lv_kontrolle,
                    ki_beteiligung=r.ki_beteiligung,
                    ki_beteiligt_begruendung=r.ki_beteiligt_begruendung,
                    begruendung=r.begruendung,
                )
                for r in ai_results
            ]
            if fe_copies:
                FunktionsErgebnis.objects.bulk_create(fe_copies)
    if obj.anlage_nr == 3 and obj.upload.name.lower().endswith(".docx"):
        try:
            from .anlage3_parser import parse_anlage3

            meta = parse_anlage3(obj)
            if meta:
                verhandlungsfaehig = meta.pop("verhandlungsfaehig", False)
                Anlage3Metadata.objects.update_or_create(
                    project_file=obj, defaults=meta
                )
                obj.verhandlungsfaehig = verhandlungsfaehig
                obj.save(update_fields=["verhandlungsfaehig"])
        except Exception:
            logger.exception("Fehler beim Anlage3 Parser")

    return obj


@login_required
def projekt_file_upload(request, pk):
    """
    LÃ¤dt eine oder mehrere Dateien zu einem Projekt hoch.
    Verarbeitet pro Anfrage genau eine Datei, wie vom Frontend gesendet.
    """
    projekt = get_object_or_404(BVProject, pk=pk)

    if request.method == "POST":
        if not _user_can_edit_project(request.user, projekt):
            return HttpResponseForbidden("Nicht berechtigt")

        temp_id = request.POST.get("temp_id")
        upload = request.FILES.get("upload")

        if temp_id and not upload:
            temp_map = request.session.get("pending_uploads", {})
            info = temp_map.get(temp_id)
            if not info:
                return HttpResponseBadRequest("invalid")
            path = info.get("path")
            name = info.get("name")
            try:
                with open(path, "rb") as fh:
                    upload = SimpleUploadedFile(name, fh.read())
            finally:
                Path(path).unlink(missing_ok=True)
                temp_map.pop(temp_id, None)
                request.session["pending_uploads"] = temp_map
                request.session.modified = True
            anlage_nr_raw = request.POST.get("anlage_nr")
            if not anlage_nr_raw or not anlage_nr_raw.isdigit():
                return HttpResponseBadRequest("invalid")
            anlage_nr = int(anlage_nr_raw)
        else:
            if not upload:
                return HttpResponseBadRequest("invalid")
            try:
                anlage_nr = extract_anlage_nr(upload.name)
            except ValueError:
                temp_id = uuid.uuid4().hex
                tmp = NamedTemporaryFile(delete=False)
                for chunk in upload.chunks():
                    tmp.write(chunk)
                tmp.close()
                temp_map = request.session.get("pending_uploads", {})
                temp_map[temp_id] = {"path": tmp.name, "name": upload.name}
                request.session["pending_uploads"] = temp_map
                request.session.modified = True
                context = {
                    "projekt": projekt,
                    "filename": upload.name,
                    "temp_id": temp_id,
                    "numbers": list(range(1, 7)),
                    "show_nr": False,
                }
                resp = render(request, "partials/anlagen_assign_row.html", context)
                resp["X-Upload-Status"] = "manual"
                return resp

        if not 1 <= anlage_nr <= 6:
            return HttpResponseBadRequest("invalid")

        try:
            _save_project_file(projekt, upload=upload, anlage_nr=anlage_nr)
        except ValueError as e:
            return HttpResponseBadRequest(str(e))

        files_qs = projekt.anlagen.filter(anlage_nr=anlage_nr).order_by("-version")
        page_obj = None
        if anlage_nr == 3:
            page_obj = Paginator(files_qs, 10).get_page(1)
        context = {
            "projekt": projekt,
            "anlagen": page_obj or files_qs,
            "page_obj": page_obj,
            "anlage_nr": anlage_nr,
            "show_nr": False,
            "active_file": get_project_file(projekt, anlage_nr),
        }
        resp = render(request, "partials/anlagen_tab.html", context)
        resp["X-Upload-Status"] = "assigned"
        resp["X-Anlage-Nr"] = str(anlage_nr)
        return resp

    # Logik fÃ¼r den initialen GET-Request (Anzeige des leeren Formulars)
    anlage_param = request.GET.get("anlage_nr")
    nr_val = None
    if anlage_param and anlage_param.isdigit():
        val = int(anlage_param)
        if 1 <= val <= 6:
            nr_val = val

    form = BVProjectFileForm(initial={"anlage_nr": nr_val})

    return render(
        request,
        "projekt_file_form.html",
        {"form": form, "projekt": projekt, "max_size": settings.MAX_UPLOAD_SIZE},
    )


@login_required
@require_http_methods(["POST"])
def projekt_file_check(request, pk, nr):
    """PrÃ¼ft eine einzelne Anlage per LLM."""
    try:
        nr_int = int(nr)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid"}, status=400)

    use_llm = request.POST.get("llm") or request.GET.get("llm")

    def parse_only(pid: int):
        pf = BVProjectFile.objects.filter(project_id=pid, anlage_nr=2).first()
        if pf:
            run_anlage2_analysis(pf)

    funcs = {1: check_anlage1, 2: check_anlage2 if use_llm else parse_only, 3: analyse_anlage3, 4: analyse_anlage4, 5: check_anlage5}
    func = funcs.get(nr_int)
    if not func:
        return JsonResponse({"error": "invalid"}, status=404)
    try:
        anlage = BVProjectFile.objects.filter(project_id=pk, anlage_nr=nr_int).first()
        if not anlage:
            return JsonResponse({"error": "not found"}, status=404)
        func(anlage.pk)
        anlage.refresh_from_db()
        analysis = anlage.analysis_json
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=404)
    except RuntimeError:
        return JsonResponse(
            {"error": "Missing LLM credentials from environment."}, status=500
        )
    except Exception:
        logger.exception("LLM Fehler")
        return JsonResponse({"status": "error"}, status=502)
    return JsonResponse({"status": "ok", "analysis": analysis})


@login_required
@require_http_methods(["POST"])
def projekt_file_check_pk(request, pk):
    """PrÃ¼ft eine Anlage anhand der Datenbank-ID."""
    try:
        anlage = BVProjectFile.objects.get(pk=pk)
    except BVProjectFile.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)

    use_llm = request.POST.get("llm") or request.GET.get("llm")

    def parse_only(_pid: int):
        run_anlage2_analysis(anlage)

    funcs = {1: check_anlage1, 2: check_anlage2 if use_llm else parse_only, 3: analyse_anlage3, 4: analyse_anlage4, 5: check_anlage5}
    func = funcs.get(anlage.anlage_nr)
    if not func:
        return JsonResponse({"error": "invalid"}, status=404)
    try:
        func(anlage.pk)
        anlage.refresh_from_db()
        analysis = anlage.analysis_json
    except RuntimeError:
        return JsonResponse(
            {"error": "Missing LLM credentials from environment."}, status=500
        )
    except Exception:
        logger.exception("LLM Fehler")
        return JsonResponse({"status": "error"}, status=502)
    return JsonResponse({"status": "ok", "analysis": analysis})


@login_required
def projekt_file_check_view(request, pk):
    """Pr\xfcft eine Anlage und leitet zur Analyse-Bearbeitung weiter."""
    try:
        anlage = BVProjectFile.objects.get(pk=pk)
    except BVProjectFile.DoesNotExist:
        raise Http404

    version_param = request.GET.get("version")
    if version_param and version_param.isdigit():
        alt = BVProjectFile.objects.filter(
            project=anlage.project,
            anlage_nr=anlage.anlage_nr,
            version=int(version_param),
        ).first()
        if alt:
            anlage = alt

    versions = list(
        BVProjectFile.objects.filter(
            project=anlage.project,
            anlage_nr=anlage.anlage_nr,
        ).order_by("version")
    )

    use_llm = request.POST.get("llm") or request.GET.get("llm")

    def parse_only(_pid: int):
        run_anlage2_analysis(anlage)

    funcs = {1: check_anlage1, 2: check_anlage2 if use_llm else parse_only, 3: analyse_anlage3, 4: analyse_anlage4, 5: check_anlage5}
    func = funcs.get(anlage.anlage_nr)
    if not func:
        raise Http404
    try:
        func(anlage.pk)
    except RuntimeError:
        messages.error(request, "Missing LLM credentials from environment.")
    except Exception:
        logger.exception("LLM Fehler")
        messages.error(request, "Fehler bei der Anlagenpr\xfcfung")

    if anlage.anlage_nr == 3:
        return redirect("anlage3_review", pk=anlage.project_id)
    if anlage.anlage_nr == 5:
        return redirect("anlage5_review", pk=anlage.pk)

    return redirect("projekt_file_edit_json", pk=pk)


@login_required
def projekt_file_parse_anlage2(request, pk):
    """Parst Anlage 2 ohne LLM-Aufrufe."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)
    if anlage.anlage_nr != 2:
        raise Http404
    table_data = parser_manager._run_single("table", anlage)
    funcs = [
        {"name": k, **v}
        for k, v in table_data.items()
        if isinstance(v, dict)
    ]
    anlage.analysis_json = {"functions": funcs}
    anlage.save(update_fields=["analysis_json"])
    return redirect("projekt_file_edit_json", pk=pk)


@login_required
def projekt_file_analyse_anlage4(request, pk):
    """Analysiert Anlage 4 und leitet zum Review."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)
    if anlage.anlage_nr != 4:
        raise Http404
    if connection.vendor == "sqlite":
        analyse_anlage4_async(anlage.pk)
    else:
        async_task("core.llm_tasks.analyse_anlage4_async", anlage.pk)
    return redirect("anlage4_review", pk=pk)


@login_required
def projekt_file_edit_json(request, pk):
    """ErmÃ¶glicht das Bearbeiten der JSON-Daten einer Anlage."""
    logger.info("projekt_file_edit_json gestartet fÃ¼r Anlage %s", pk)
    try:
        anlage = BVProjectFile.objects.get(pk=pk)
    except BVProjectFile.DoesNotExist:
        raise Http404
    gap_form = BVGapNotesForm(
        request.POST if request.method == "POST" else None, instance=anlage
    )
    versions = list(
        BVProjectFile.objects.filter(
            project=anlage.project,
            anlage_nr=anlage.anlage_nr,
        ).order_by("version")
    )

    if (
        request.method == "POST"
        and set(request.POST.keys())
        <= {"csrfmiddlewaretoken", "gap_summary", "gap_notiz"}
        and gap_form.is_valid()
    ):
        gap_form.save()
        return redirect("projekt_detail", pk=anlage.project.pk)

    if request.method == "GET" and anlage.anlage_nr == 2:
        results = AnlagenFunktionsMetadaten.objects.filter(
            anlage_datei=anlage
        ).select_related("funktion", "subquestion")
        for res in results:
            name = res.get_lookup_key()
            parser_res = (
                FunktionsErgebnis.objects.filter(
                    anlage_datei=anlage,
                    funktion=res.funktion,
                    subquestion=res.subquestion,
                    quelle="parser",
                )
                .order_by("-created_at")
                .first()
            )
            ki_res = (
                FunktionsErgebnis.objects.filter(
                    anlage_datei=anlage,
                    funktion=res.funktion,
                    subquestion=res.subquestion,
                    quelle="ki",
                )
                .order_by("-created_at")
                .first()
            )
            doc_str = json.dumps(
                parser_res.technisch_verfuegbar if parser_res else None,
                ensure_ascii=False,
            )
            ai_str = json.dumps(
                ki_res.technisch_verfuegbar if ki_res else None, ensure_ascii=False
            )
            ergebnis_logger.info("%s\nDOC: %s\nAI: %s", name, doc_str, ai_str)

    if anlage.anlage_nr == 1:
        template = "projekt_file_anlage1_review.html"
        data = anlage.question_review or _analysis1_to_initial(anlage)
        numbers = get_anlage1_numbers()
        q_data = (
            anlage.analysis_json.get("questions", {}) if anlage.analysis_json else {}
        )
        answers = {str(i): q_data.get(str(i), {}).get("answer", "") for i in numbers}
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
        questions = {q.num: q.text for q in question_objs}
        qa = []
        for i in numbers:
            entry = data.get(str(i), {})
            qa.append(
                {
                    "num": i,
                    "question": questions.get(i, ""),
                    "answer": answers.get(str(i), ""),
                    "hinweis": entry.get("hinweis", ""),
                    "vorschlag": entry.get("vorschlag", ""),
                    "ok": entry.get("ok", False),
                }
            )
        # GAP-Bericht der Vorgängerversion laden oder berechnen
        if anlage.parent:
            gap_text = (
                anlage.parent.gap_summary
                or summarize_anlage1_gaps(anlage.project, pf=anlage.parent)
            )
            has_parent = True
        else:
            gap_text = ""
            has_parent = False
        form = None
    elif anlage.anlage_nr == 2:
        analysis_init = _analysis_to_initial(anlage)
        parser_form = ParserSettingsForm(
            request.POST
            if request.method == "POST" and "save_parser_settings" in request.POST
            else None,
            instance=anlage,
        )
        if request.method == "POST":
            if "save_parser_settings" in request.POST:
                form = Anlage2ReviewForm(initial=analysis_init)
                if parser_form.is_valid() and gap_form.is_valid():
                    parser_form.save()
                    gap_form.save()
                    messages.success(request, "Parser-Einstellungen gespeichert")
                    return redirect("projekt_file_edit_json", pk=pk)
            elif "run_parser" in request.POST:
                run_anlage2_analysis(anlage)
                anlage.refresh_from_db()
                if gap_form.is_valid():
                    gap_form.save()
                return redirect("projekt_file_edit_json", pk=pk)
            else:
                form = Anlage2ReviewForm(request.POST)
                if form.is_valid() and gap_form.is_valid():
                    cfg_rule = Anlage2Config.get_instance()
                    functions_to_override: set[int] = set()
                    if cfg_rule.enforce_subquestion_override:
                        for func in Anlage2Function.objects.order_by("name"):
                            for sub in func.anlage2subquestion_set.all().order_by("id"):
                                field_name = f"sub{sub.id}_technisch_vorhanden"
                                if form.cleaned_data.get(field_name):
                                    functions_to_override.add(func.id)

                data = form.get_json()
                gap_form.save()
                field_map = {
                    "technisch_vorhanden": "technisch_verfuegbar",
                    "ki_beteiligung": "ki_beteiligung",
                    "einsatz_bei_telefonica": "einsatz_bei_telefonica",
                    "zur_lv_kontrolle": "zur_lv_kontrolle",
                }
                for fid, fdata in data.get("functions", {}).items():
                    func = get_object_or_404(Anlage2Function, pk=int(fid))
                    res, _ = AnlagenFunktionsMetadaten.objects.get_or_create(
                        anlage_datei=anlage,
                        funktion=func,
                        subquestion=None,
                    )
                    meta_fields = []
                    if fdata.get("gap_notiz") is not None:
                        res.gap_notiz = fdata.get("gap_notiz")
                        meta_fields.append("gap_notiz")
                    if fdata.get("gap_summary") is not None:
                        res.gap_summary = fdata.get("gap_summary")
                        meta_fields.append("gap_summary")
                    if meta_fields:
                        res.save(update_fields=meta_fields)
                    for fname, attr in field_map.items():
                        val = fdata.get(fname)
                        if val is not None:
                            FunktionsErgebnis.objects.create(
                                anlage_datei=anlage,
                                funktion=func,
                                quelle="manuell",
                                **{attr: val},
                            )
                    qs = FunktionsErgebnis.objects.filter(
                        anlage_datei=anlage,
                        funktion=func,
                        subquestion__isnull=True,
                    )
                    tv_res = (
                        qs.exclude(technisch_verfuegbar__isnull=True)
                        .order_by("-created_at")
                        .first()
                    )
                    kb_res = (
                        qs.exclude(ki_beteiligung__isnull=True)
                        .order_by("-created_at")
                        .first()
                    )
                    auto_val = _calc_auto_negotiable(
                        tv_res.technisch_verfuegbar if tv_res else None,
                        kb_res.ki_beteiligung if kb_res else None,
                    )
                    if res.is_negotiable_manual_override is None:
                        res.is_negotiable = auto_val
                        res.save(update_fields=["is_negotiable"])
                    for sid, sdata in fdata.get("subquestions", {}).items():
                        sub = get_object_or_404(Anlage2SubQuestion, pk=int(sid))
                        sres, _ = AnlagenFunktionsMetadaten.objects.get_or_create(
                            anlage_datei=anlage,
                            funktion=func,
                            subquestion=sub,
                        )
                        meta_fields = []
                        if sdata.get("gap_notiz") is not None:
                            sres.gap_notiz = sdata.get("gap_notiz")
                            meta_fields.append("gap_notiz")
                        if sdata.get("gap_summary") is not None:
                            sres.gap_summary = sdata.get("gap_summary")
                            meta_fields.append("gap_summary")
                        if meta_fields:
                            sres.save(update_fields=meta_fields)
                        for fname, attr in field_map.items():
                            val = sdata.get(fname)
                            if val is not None:
                                FunktionsErgebnis.objects.create(
                                    anlage_datei=anlage,
                                    funktion=func,
                                    subquestion=sub,
                                    quelle="manuell",
                                    **{attr: val},
                                )
                        qs = FunktionsErgebnis.objects.filter(
                            anlage_datei=anlage,
                            funktion=func,
                            subquestion=sub,
                        )
                        tv_res = (
                            qs.exclude(technisch_verfuegbar__isnull=True)
                            .order_by("-created_at")
                            .first()
                        )
                        kb_res = (
                            qs.exclude(ki_beteiligung__isnull=True)
                            .order_by("-created_at")
                            .first()
                        )
                        auto_val = _calc_auto_negotiable(
                            tv_res.technisch_verfuegbar if tv_res else None,
                            kb_res.ki_beteiligung if kb_res else None,
                        )
                        if sres.is_negotiable_manual_override is None:
                            sres.is_negotiable = auto_val
                            sres.save(update_fields=["is_negotiable"])

                logger.info(
                    "Anlage2 Review gespeichert: %s Funktionen",
                    len(data.get("functions", {})),
                )

                if cfg_rule.enforce_subquestion_override:
                    for fid in functions_to_override:
                        AnlagenFunktionsMetadaten.objects.update_or_create(
                            anlage_datei=anlage,
                            funktion_id=fid,
                        )

                return redirect("projekt_detail", pk=anlage.project.pk)
        else:
            verif_init = _verification_to_initial(anlage)
            ki_map: dict[tuple[str, str | None], str] = {}
            beteilig_map: dict[tuple[str, str | None], tuple[bool | None, str]] = {}
            for res in FunktionsErgebnis.objects.filter(
                anlage_datei=anlage,
                quelle="ki",
            ):
                fid = str(res.funktion_id)
                sid = str(res.subquestion_id) if res.subquestion_id else None
                beteiligt = res.ki_beteiligung
                begr = res.ki_beteiligt_begruendung
                if beteiligt is not None or begr:
                    beteilig_map[(fid, sid)] = (beteiligt, begr or "")
                if res.begruendung:
                    ki_map[(fid, sid)] = res.begruendung

            manual_results_map = {}
            for r in FunktionsErgebnis.objects.filter(
                anlage_datei=anlage, quelle="manuell"
            ):
                key = (
                    f"{r.funktion.name}: {r.subquestion.frage_text}"
                    if r.subquestion
                    else r.funktion.name
                )
                entry = {}
                if r.technisch_verfuegbar is not None:
                    entry["technisch_vorhanden"] = r.technisch_verfuegbar
                if r.ki_beteiligung is not None:
                    entry["ki_beteiligung"] = r.ki_beteiligung
                if r.einsatz_bei_telefonica is not None:
                    entry["einsatz_bei_telefonica"] = r.einsatz_bei_telefonica
                if r.zur_lv_kontrolle is not None:
                    entry["zur_lv_kontrolle"] = r.zur_lv_kontrolle
                if entry:
                    manual_results_map[key] = entry

            result_map = {
                r.get_lookup_key(): r
                for r in AnlagenFunktionsMetadaten.objects.filter(anlage_datei=anlage)
            }

            # Sicherstellen, dass f\u00fcr jede Funktion und Unterfrage ein Metadatensatz existiert
            for func in Anlage2Function.objects.order_by("name"):
                # Stelle sicher, dass der Metadatensatz fÃ¼r die Hauptfunktion (ohne Unterfrage)
                # eindeutig Ã¼ber subquestion=None adressiert wird, um Mehrfachtreffer zu vermeiden.
                res, _ = AnlagenFunktionsMetadaten.objects.get_or_create(
                    anlage_datei=anlage, funktion=func, subquestion=None
                )
                result_map[res.get_lookup_key()] = res
                for sub in func.anlage2subquestion_set.all().order_by("id"):
                    res, _ = AnlagenFunktionsMetadaten.objects.get_or_create(
                        anlage_datei=anlage, funktion=func, subquestion=sub
                    )
                    key = res.get_lookup_key()
                    result_map[key] = res


            fields_def = get_anlage2_fields()

            analysis_lookup = _initial_to_lookup(analysis_init)
            verification_lookup = _initial_to_lookup(verif_init)
            manual_lookup: dict[str, dict] = {}

            for key, res in manual_results_map.items():
                entry = manual_lookup.setdefault(key, {})
                for f, val in res.items():
                    if val is not None or f in entry:
                        entry[f] = val

            sample_funcs = list(Anlage2Function.objects.order_by("name")[:2])
            for sf in sample_funcs:
                lk = sf.name
                workflow_logger.info(
                    "[%s] - UI RENDER - Daten f\u00fcr Funktion '%s': doc_result: %s, ai_result: %s, manual_result: %s",
                    anlage.project_id,
                    sf.name,
                    analysis_lookup.get(lk),
                    verification_lookup.get(lk),
                    manual_lookup.get(lk),
                )
                disp_sample = _get_display_data(
                    lk, analysis_lookup, verification_lookup, manual_lookup
                )
                workflow_logger.info(
                    "[%s] - UI RENDER - Finaler Anzeigewert f\u00fcr '%s': Wert=%s, Quelle='%s'",
                    anlage.project_id,
                    sf.name,
                    disp_sample["values"].get("technisch_vorhanden"),
                    disp_sample["sources"].get("technisch_vorhanden"),
                )

            init = {"functions": {}}

            for func in Anlage2Function.objects.order_by("name"):
                fid = str(func.id)
                disp = _get_display_data(
                    func.name, analysis_lookup, verification_lookup, manual_lookup
                )
                func_entry = disp["values"].copy()
                sub_map_init: dict[str, dict] = {}
                for sub in func.anlage2subquestion_set.all().order_by("id"):
                    sid = str(sub.id)
                    lookup = f"{func.name}: {sub.frage_text}"
                    s_disp = _get_display_data(
                        lookup, analysis_lookup, verification_lookup, manual_lookup
                    )
                    sub_map_init[sid] = s_disp["values"].copy()
                if sub_map_init:
                    func_entry["subquestions"] = sub_map_init
                init["functions"][fid] = func_entry

            form = Anlage2ReviewForm(initial=init)

        template = "projekt_file_anlage2_review.html"
        answers: dict[str, dict] = {}
        funcs = []
        if isinstance(anlage.analysis_json, dict):
            funcs = anlage.analysis_json.get("functions")
        if not isinstance(funcs, list):
            funcs = []
        for item in funcs:
            name = item.get("funktion") or item.get("name")
            if name:
                answers[name] = item
                for sub in item.get("subquestions", []):
                    s_text = sub.get("frage_text")
                    if s_text:
                        answers[f"{name}: {s_text}"] = sub
        rows = []
        fields_def = get_anlage2_fields()

        for func in Anlage2Function.objects.order_by("name"):
            lookup_key = func.name
            func_status = analysis_lookup.get(lookup_key, {}).get("technisch_vorhanden")
            if func.name == "AnwesenheitsÃ¼berwachung":
                detail_logger.info(
                    "--- Starte detaillierte PrÃ¼fung fÃ¼r Funktion: '%s' ---",
                    func.name,
                )
                if func_status is True:
                    detail_logger.info("-> Status: Als 'Technisch verfÃ¼gbar' erkannt.")
                elif func_status is False:
                    detail_logger.info(
                        "-> Status: Als 'Technisch NICHT verfÃ¼gbar' erkannt."
                    )
                note = None
                tv_entry = answers.get(lookup_key, {}).get("technisch_vorhanden")
                if isinstance(tv_entry, dict):
                    note = tv_entry.get("note") or tv_entry.get("text")
                if note:
                    detail_logger.info("-> Entscheidungsgrundlage im Text: '%s'", note)
            else:
                detail_logger.info(
                    "--- Starte PrÃ¼fung fÃ¼r Funktion: '%s' ---", func.name
                )
                if answers.get(lookup_key):
                    detail_logger.info("-> Ergebnis: Im Dokument gefunden.")
                else:
                    detail_logger.info("-> Ergebnis: Nicht im Dokument gefunden.")
            rows.append(
                _build_row_data(
                    func.name,
                    lookup_key,
                    func.id,
                    f"func{func.id}_",
                    form,
                    answers,
                    ki_map,
                    beteilig_map,
                    manual_lookup,
                    result_map,
                )
            )
            for sub in func.anlage2subquestion_set.all().order_by("id"):
                lookup_key = f"{func.name}: {sub.frage_text}"
                if not (
                    func.name == "AnwesenheitsÃ¼berwachung" and func_status is not True
                ):
                    detail_logger.info(
                        "--- Starte PrÃ¼fung fÃ¼r Unterfrage: '%s' ---", sub.frage_text
                    )
                    if answers.get(lookup_key):
                        detail_logger.info("-> Ergebnis: Im Dokument gefunden.")
                    else:
                        detail_logger.info("-> Ergebnis: Nicht im Dokument gefunden.")
                rows.append(
                    _build_row_data(
                        sub.frage_text,
                        lookup_key,
                        func.id,
                        f"sub{sub.id}_",
                        form,
                        answers,
                        ki_map,
                        beteilig_map,
                        manual_lookup,
                    result_map,
                    sub_id=sub.id,
                )
            )
        has_ai_results = FunktionsErgebnis.objects.filter(
            anlage_datei__project=anlage.project,
            anlage_datei__anlage_nr=2,
            quelle="ki",
        ).exists()
    elif anlage.anlage_nr == 4:
        items = []
        if anlage.analysis_json:
            items = anlage.analysis_json.get("items")
        if isinstance(items, dict):
            items = items.get("value", [])
        if not items:
            items = []
        if request.method == "POST":
            if "analysis_json" in request.POST:
                json_form = BVProjectFileJSONForm(request.POST, instance=anlage)
                if json_form.is_valid():
                    json_form.save()
                    return redirect("projekt_detail", pk=anlage.project.pk)
                form = json_form
            else:
                form = Anlage4ReviewForm(request.POST, items=items)
                if form.is_valid():
                    analysis = anlage.analysis_json or {}
                    analysis["manual_review"] = form.get_json()
                    anlage.analysis_json = analysis
                    anlage.save(update_fields=["analysis_json"])
                    return redirect("projekt_detail", pk=anlage.project.pk)
        else:
            form = Anlage4ReviewForm(
                initial=(anlage.analysis_json or {}).get("manual_review"),
                items=items,
            )
        template = "projekt_file_anlage4_review.html"
        rows = [
            (text, form[f"item{idx}_ok"], form[f"item{idx}_note"])
            for idx, text in enumerate(items)
        ]
    else:
        if request.method == "POST":
            form = BVProjectFileJSONForm(request.POST, instance=anlage)
            if form.is_valid():
                obj = form.save()
                if obj.anlage_nr == 3 and not obj.manual_reviewed:
                    obj.manual_reviewed = True
                    obj.save(update_fields=["manual_reviewed"])
                return redirect("projekt_detail", pk=anlage.project.pk)
        else:
            form = BVProjectFileJSONForm(instance=anlage)
        template = "projekt_file_json_form.html"

    context = {
        "form": form,
        "anlage": anlage,
        "gap_form": gap_form,
        "versions": versions,
        "current_version": anlage.version,
    }
    # Explizite Breadcrumbs für die Review-Ansichten der Anlagen
    try:
        bc = [
            {"url": reverse("work"), "label": "Work"},
            {
                "url": reverse("projekt_detail", args=[anlage.project.pk]),
                "label": getattr(anlage.project, "title", None)
                or getattr(anlage.project, "software_string", None)
                or f"Projekt {anlage.project.pk}",
            },
            {"url": None, "label": f"Anlage {anlage.anlage_nr} v{anlage.version}"},
            {"url": None, "label": "Review"},
        ]
        context["breadcrumbs"] = bc
    except Exception:
        # Fallback, falls URLs nicht auflösbar sind – Kontextprozessor greift dann
        pass
    if anlage.anlage_nr == 1:
        context["qa"] = qa
        context["gap_text"] = gap_text
        context["has_parent"] = has_parent
    elif anlage.anlage_nr == 2:
        context.update(
            {
                "rows": rows,
                "fields": [f[0] for f in fields_def],
                "labels": [f[1] for f in fields_def],
                "field_pairs": fields_def,
                "no_ai_fields": ["einsatz_bei_telefonica", "zur_lv_kontrolle"],
                "parser_form": parser_form,
                "allow_ai_check": not has_ai_results,
            }
        )
    elif anlage.anlage_nr == 4:
        context["rows"] = rows
    logger.info("projekt_file_edit_json beendet fÃ¼r Anlage %s", pk)
    return render(request, template, context)


def _validate_llm_output(text: str) -> tuple[bool, str]:
    """PrÃ¼fe, ob die LLM-Antwort technisch brauchbar ist."""
    if not text:
        return False, "Antwort leer"
    if len(text.split()) < 5:
        return False, "Antwort zu kurz"
    return True, ""


def _run_llm_check(
    name: str, additional: str | None = None, project_prompt: str | None = None
) -> tuple[str, bool]:
    """FÃ¼hrt die LLM-Abfrage fÃ¼r eine einzelne Software durch."""
    base = get_prompt(
        "initial_llm_check",
        (
            "Do you know software {name}? Provide a short, technically correct "
            "description of what it does and how it is typically used."
        ),
    )
    prompt_text = base.format(name=name)
    if additional:
        prompt_text += " " + additional
    base_obj = Prompt.objects.filter(name__iexact="initial_llm_check").first()
    prompt_obj = Prompt(
        name="tmp", text=prompt_text, role=base_obj.role if base_obj else None
    )

    logger.debug("Starte LLM-Check fÃ¼r %s", name)
    ctx = build_prompt_context()
    reply = query_llm(prompt_obj, ctx, project_prompt=project_prompt)
    valid, _ = _validate_llm_output(reply)
    logger.debug("LLM-Antwort fÃ¼r %s: %s", name, reply[:100])
    return reply, valid


@login_required
@require_http_methods(["GET"])
def project_detail_api(request, pk):
    projekt = get_object_or_404(BVProject, pk=pk)
    software_list = projekt.software_list
    knowledge_map = {k.software_name: k for k in projekt.softwareknowledge.all()}
    knowledge = []
    checked = 0
    for name in software_list:
        entry = knowledge_map.get(name)
        item = {
            "software_name": name,
            "id": entry.pk if entry else None,
            "is_known_by_llm": entry.is_known_by_llm if entry else False,
            "description": entry.description if entry else "",
            "last_checked": bool(entry and entry.last_checked),
        }
        if item["last_checked"]:
            checked += 1
        knowledge.append(item)

    data = {
        "id": projekt.pk,
        "title": projekt.title,
        "beschreibung": projekt.beschreibung,
        "software_typen": projekt.software_string,
        "software_list": software_list,
        "knowledge": knowledge,
        "checked": checked,
        "total": len(software_list),
    }
    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def projekt_status_update(request, pk):
    """Aktualisiert den Projektstatus."""
    projekt = get_object_or_404(BVProject, pk=pk)
    status = request.POST.get("status")
    try:
        set_project_status(projekt, status)
    except ValueError:
        pass
    return redirect("projekt_detail", pk=projekt.pk)


@login_required
@require_http_methods(["POST"])
def projekt_functions_check(request, pk):
    """LÃ¶st die EinzelprÃ¼fung der Anlage-2-Funktionen aus."""
    model = request.POST.get("model")
    projekt = get_object_or_404(BVProject, pk=pk)
    if FunktionsErgebnis.objects.filter(
        anlage_datei__project=projekt, anlage_datei__anlage_nr=2, quelle="ki"
    ).exists():
        return JsonResponse({"error": "results_exist"}, status=400)
    pf = BVProjectFile.objects.filter(project=projekt, anlage_nr=2).first()
    if pf:
        # Status sofort auf PROCESSING setzen, damit die Analyse gesperrt bleibt
        pf.processing_status = BVProjectFile.PROCESSING
        pf.save(update_fields=["processing_status"])

        def _start_task() -> None:
            """Startet den Hintergrundtask und speichert die Task-ID."""
            task_id = async_task(
                "core.llm_tasks.run_conditional_anlage2_check",
                pf.pk,
                model,
            )
            BVProjectFile.objects.filter(pk=pf.pk).update(
                verification_task_id=task_id
            )

        transaction.on_commit(_start_task)
    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["POST"])
def anlage2_feature_verify(request, pk):
    """Startet die Pr\u00fcfung einer Einzelfunktion im Hintergrund."""
    logger.debug(
        f"--- KI-Pr\u00fcfung f\u00fcr Anlage 2 gestartet (project_file pk={pk}) ---"
    )
    logger.debug(f"Empfangene POST-Daten: {request.POST.dict()}")
    try:
        anlage = BVProjectFile.objects.get(pk=pk)
    except BVProjectFile.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)
    if anlage.anlage_nr != 2:
        return JsonResponse({"error": "invalid"}, status=400)
    if FunktionsErgebnis.objects.filter(
        anlage_datei__project=anlage.project,
        anlage_datei__anlage_nr=2,
        quelle="ki",
    ).exists():
        return JsonResponse({"error": "results_exist"}, status=400)

    function_id = request.POST.get("function_id", None)
    subquestion_id = request.POST.get("subquestion_id", None)
    model = request.POST.get("model")
    logger.debug(f"Extrahierte function_id: '{function_id}'")
    logger.debug(f"Extrahierte subquestion_id: '{subquestion_id}'")
    if function_id:
        object_type = "function"
        obj_id = int(function_id)
        get_object_or_404(Anlage2Function, pk=obj_id)  # nur Validierung
    elif subquestion_id:
        object_type = "subquestion"
        obj_id = int(subquestion_id)
        sub_obj = get_object_or_404(Anlage2SubQuestion, pk=obj_id)
        parent_res = (
            AnlagenFunktionsMetadaten.objects.filter(
                anlage_datei=anlage, funktion=sub_obj.funktion
            )
            .order_by("-id")
            .first()
        )
    else:
        logger.error(
            "FEHLER: Weder function_id noch subquestion_id im POST-Request gefunden. Sende 400 Bad Request."
        )
        return JsonResponse({"error": "invalid"}, status=400)

    task_id = async_task(
        "core.llm_tasks.worker_verify_feature",
        anlage.id,
        object_type,
        obj_id,
        model,
    )

    return JsonResponse({"status": "queued", "task_id": task_id})


@login_required
def anlage2_supervision(request, projekt_id):
    """Zeigt die neue Supervisions-Ansicht f\u00fcr AnlageÂ 2."""

    projekt = get_object_or_404(BVProject, pk=projekt_id)
    version_param = request.GET.get("version")
    if version_param and version_param.isdigit():
        pf = get_project_file(projekt, 2, version=int(version_param))
    else:
        pf = get_project_file(projekt, 2)
    if pf is None:
        raise Http404

    versions = list(
        BVProjectFile.objects.filter(project=projekt, anlage_nr=2).order_by("version")
    )

    rows = _build_supervision_groups(pf)
    notes = list(
        SupervisionStandardNote.objects.filter(is_active=True).order_by("display_order")
    )

    context = {
        "projekt": projekt,
        "rows": rows,
        "standard_notes": notes,
        "versions": versions,
        "current_version": pf.version,
        "pf": pf,
    }
    return render(request, "supervision_review.html", context)


@login_required
@require_POST
def hx_supervision_confirm(request, result_id: int):
    """Speichert das KI-Ergebnis als manuellen Wert."""

    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    pf = get_project_file(result.anlage_datei.project, 2)
    ai_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion=result.subquestion,
            quelle="ki",
        )
        .order_by("-created_at")
        .first()
    )
    if ai_entry:
        FunktionsErgebnis.objects.create(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion=result.subquestion,
            quelle="manuell",
            technisch_verfuegbar=ai_entry.technisch_verfuegbar,
        )

    if result.subquestion is None:
        groups = _build_supervision_groups(pf)
        group = next(g for g in groups if g["function"]["result_id"] == result.id)
        return render(request, "partials/supervision_group.html", {"group": group})
    row = _build_supervision_row(result, pf)
    return render(request, "partials/supervision_row.html", {"row": row})


@login_required
@require_POST
def hx_supervision_save_notes(request, result_id: int):
    """Speichert die Notizen des Supervisors."""

    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    result.supervisor_notes = request.POST.get("notes", "")
    result.save(update_fields=["supervisor_notes"])

    pf = get_project_file(result.anlage_datei.project, 2)
    if result.subquestion is None:
        groups = _build_supervision_groups(pf)
        group = next(g for g in groups if g["function"]["result_id"] == result.id)
        return render(request, "partials/supervision_group.html", {"group": group})
    row = _build_supervision_row(result, pf)
    return render(request, "partials/supervision_row.html", {"row": row})


@login_required
@require_POST
def hx_supervision_add_standard_note(request, result_id: int):
    """FÃ¼gt eine Standardnotiz zu den Supervisor-Notizen hinzu."""

    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    note_text = request.POST.get("note_text", "")
    if note_text:
        if result.supervisor_notes:
            result.supervisor_notes += "\n" + note_text
        else:
            result.supervisor_notes = note_text
        result.save(update_fields=["supervisor_notes"])

    pf = get_project_file(result.anlage_datei.project, 2)
    if result.subquestion is None:
        groups = _build_supervision_groups(pf)
        group = next(g for g in groups if g["function"]["result_id"] == result.id)
        return render(request, "partials/supervision_group.html", {"group": group})
    row = _build_supervision_row(result, pf)
    return render(request, "partials/supervision_row.html", {"row": row})


@login_required
@require_POST
def hx_supervision_revert_to_document(request, result_id: int):
    """Setzt manuelle Bewertungen auf Dokumentenwerte zurÃ¼ck."""

    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    pf = get_project_file(result.anlage_datei.project, 2)

    FunktionsErgebnis.objects.filter(
        anlage_datei=pf,
        funktion=result.funktion,
        subquestion=result.subquestion,
        quelle="manuell",
    ).delete()

    main_result = AnlagenFunktionsMetadaten.objects.filter(
        anlage_datei=pf,
        funktion=result.funktion,
        subquestion__isnull=True,
    ).first()

    groups = _build_supervision_groups(pf)
    if main_result:
        group = next(g for g in groups if g["function"]["result_id"] == main_result.id)
        return render(request, "partials/supervision_group.html", {"group": group})
    return HttpResponse("Not found", status=404)


@login_required
def ajax_check_task_status(request, task_id: str) -> JsonResponse:
    """PrÃ¼ft den Status eines Django-Q-Tasks und gibt ihn als JSON zurÃ¼ck."""
    task = fetch(task_id)
    if not task:
        return JsonResponse({"status": "UNKNOWN", "result": None})

    task_status_str = "SUCCESS" if task.success else "FAIL"
    task_result = result(task_id) if task.success else None

    return JsonResponse({"status": task_status_str, "result": task_result})


@login_required
@require_http_methods(["POST"])
def ajax_save_manual_review_item(request) -> JsonResponse:
    """Speichert eine einzelne manuelle Bewertung."""

    pf_id = request.POST.get("project_file_id")
    func_id = request.POST.get("function_id")
    sub_id = request.POST.get("subquestion_id")
    status_val = request.POST.get("status")
    if status_val in (True, "True", "true", "1", 1):
        status = True
    elif status_val in (False, "False", "false", "0", 0):
        status = False
    else:
        status = None
    notes = request.POST.get("notes")

    if pf_id is None or func_id is None:
        return JsonResponse({"error": "invalid"}, status=400)

    anlage = get_object_or_404(BVProjectFile, pk=pf_id)
    if anlage.anlage_nr != 2:
        return JsonResponse({"error": "invalid"}, status=400)

    funktion = get_object_or_404(Anlage2Function, pk=func_id)

    AnlagenFunktionsMetadaten.objects.update_or_create(
        anlage_datei=anlage,
        funktion=funktion,
        subquestion_id=sub_id,
    )
    FunktionsErgebnis.objects.create(
        anlage_datei=anlage,
        funktion=funktion,
        subquestion_id=sub_id,
        quelle="manuell",
        technisch_verfuegbar=status,
    )

    return JsonResponse({"status": "success"})


@login_required
@require_POST
def ajax_save_anlage2_review(request) -> JsonResponse:
    """Speichert eine einzelne Bewertung f\u00fcr Anlage 2 per AJAX."""

    try:
        data = json.loads(request.body)
        pf_id = data.get("project_file_id")
        func_id = data.get("function_id")
        sub_id = data.get("subquestion_id")
        field_name = data.get("field_name")
        status_provided = "status" in data
        gap_notiz = data.get("gap_notiz")
        gap_summary = data.get("gap_summary")
        set_neg = data.get("set_negotiable", "__missing__")

        status = None
        if status_provided:
            status_val = data.get("status")
            if status_val in (True, "True", "true", "1", 1):
                status = True
            elif status_val in (False, "False", "false", "0", 0):
                status = False

        notes = data.get("notes", "")

        if pf_id is None or func_id is None:
            return JsonResponse({"error": "invalid"}, status=400)

        anlage = get_object_or_404(BVProjectFile, pk=pf_id)
        if anlage.anlage_nr != 2:
            return JsonResponse({"error": "invalid"}, status=400)

        funktion = get_object_or_404(Anlage2Function, pk=func_id)
        if sub_id:
            get_object_or_404(Anlage2SubQuestion, pk=sub_id)

        field_map = {
            "technisch_vorhanden": "technisch_verfuegbar",
            "ki_beteiligung": "ki_beteiligung",
            "einsatz_bei_telefonica": "einsatz_bei_telefonica",
            "zur_lv_kontrolle": "zur_lv_kontrolle",
        }

        prev_manual = None
        if field_name == "technisch_vorhanden" and sub_id is None and status_provided:
            prev = (
                FunktionsErgebnis.objects.filter(
                    anlage_datei=anlage,
                    funktion=funktion,
                    subquestion__isnull=True,
                    quelle="manuell",
                )
                .order_by("-created_at")
                .first()
            )
            if prev:
                prev_manual = prev.technisch_verfuegbar

        anlage2_logger.debug(
            "Review gespeichert: pf=%s func=%s sub=%s field=%s status=%s notes=%r",
            pf_id,
            func_id,
            sub_id,
            field_name,
            status,
            notes,
        )

        res, _created = AnlagenFunktionsMetadaten.objects.get_or_create(
            anlage_datei=anlage,
            funktion=funktion,
            subquestion_id=sub_id,
        )

        update_fields = []

        if gap_notiz is not None:
            res.gap_notiz = gap_notiz
            update_fields.append("gap_notiz")
        if gap_summary is not None:
            res.gap_summary = gap_summary
            update_fields.append("gap_summary")

        if field_name is not None and status_provided:
            attr = field_map.get(field_name, "technisch_verfuegbar")
            FunktionsErgebnis.objects.create(
                anlage_datei=anlage,
                funktion=funktion,
                subquestion_id=sub_id,
                quelle="manuell",
                **{attr: status},
            )

        qs = FunktionsErgebnis.objects.filter(
            anlage_datei=anlage,
            funktion=funktion,
            subquestion_id=sub_id,
        )
        tv_res = (
            qs.exclude(technisch_verfuegbar__isnull=True)
            .order_by("-created_at")
            .first()
        )
        kb_res = qs.exclude(ki_beteiligung__isnull=True).order_by("-created_at").first()
        auto_val = _calc_auto_negotiable(
            tv_res.technisch_verfuegbar if tv_res else None,
            kb_res.ki_beteiligung if kb_res else None,
        )

        if set_neg != "__missing__":
            if set_neg in (True, "True", "true", "1", 1):
                override_val = True
            elif set_neg in (False, "False", "false", "0", 0):
                override_val = False
            else:
                override_val = None
            res.is_negotiable_manual_override = override_val
            if override_val is not None:
                res.is_negotiable = override_val
            else:
                res.is_negotiable = auto_val
            update_fields.extend(["is_negotiable_manual_override", "is_negotiable"])
        elif field_name == "technisch_vorhanden" and status_provided and sub_id is None:
            if res.is_negotiable_manual_override is None:
                res.is_negotiable = auto_val
            update_fields.append("is_negotiable")

        res.save(update_fields=update_fields)

        gap_text = res.gap_summary or ""
        ai_val = None
        # Die Generierung der Gap-Zusammenfassung erfolgt nun manuell Ã¼ber ein
        # separates Endpoint und wird hier nicht mehr automatisch ausgelÃ¶st.

        if field_name is not None and status_provided:
            if (
                field_name == "technisch_vorhanden"
                and sub_id is None
                and status is True
                and prev_manual in (False, None)
            ):
                func_exists = (
                    FunktionsErgebnis.objects.filter(
                        anlage_datei=anlage,
                        funktion=funktion,
                        subquestion__isnull=True,
                    )
                    .exclude(quelle="manuell")
                    .exists()
                )
                if not func_exists:
                    async_task(
                        "core.llm_tasks.worker_verify_feature",
                        anlage.id,
                        "function",
                        funktion.id,
                    )
                for sub in funktion.anlage2subquestion_set.all():
                    sub_exists = (
                        FunktionsErgebnis.objects.filter(
                            anlage_datei=anlage,
                            funktion=funktion,
                            subquestion=sub,
                        )
                        .exclude(quelle="manuell")
                        .exists()
                    )
                    if not sub_exists:
                        async_task(
                            "core.llm_tasks.worker_verify_feature",
                            anlage.id,
                            "subquestion",
                            sub.id,
                        )

        return JsonResponse(
            {
                "status": "success",
                "gap_summary": gap_text,
                "is_negotiable": res.negotiable,
                "is_negotiable_override": res.is_negotiable_manual_override,
            }
        )
    except Exception as exc:  # pragma: no cover - Schutz vor unerwarteten Fehlern
        logger.error(
            "Fehler beim Speichern des manuellen Reviews: %s",
            exc,
            exc_info=True,
        )
        return JsonResponse({"status": "error", "message": str(exc)}, status=500)


@login_required
@require_POST
def hx_update_review_cell(request, result_id: int, field_name: str):
    """Schaltet einen Review-Wert um und rendert die komplette Tabellenzeile."""
    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    sub_id = request.POST.get("sub_id")

    field_map = {
        "technisch_vorhanden": "technisch_verfuegbar",
        "ki_beteiligung": "ki_beteiligung",
        "einsatz_bei_telefonica": "einsatz_bei_telefonica",
        "zur_lv_kontrolle": "zur_lv_kontrolle",
    }
    attr = field_map.get(field_name, "technisch_verfuegbar")

    pf = get_project_file(result.anlage_datei.project, 2)

    manual_qs = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion_id=sub_id,
            quelle="manuell",
        )
        .exclude(**{attr: None})
        .order_by("-created_at")
    )

    manual_entry = manual_qs.first()

    if manual_entry:
        manual_entry.delete()
    else:
        parser_entry = (
            FunktionsErgebnis.objects.filter(
                anlage_datei=pf,
                funktion=result.funktion,
                subquestion_id=sub_id,
                quelle="parser",
            )
            .exclude(**{attr: None})
            .order_by("-created_at")
            .first()
        )
        ai_entry = (
            FunktionsErgebnis.objects.filter(
                anlage_datei=pf,
                funktion=result.funktion,
                subquestion_id=sub_id,
                quelle="ki",
            )
            .exclude(**{attr: None})
            .order_by("-created_at")
            .first()
        )
        doc_val = getattr(parser_entry, attr) if parser_entry else None
        ai_val = getattr(ai_entry, attr) if ai_entry else None
        cur_val, _ = _resolve_value(None, ai_val, doc_val, field_name, False, parser_entry is not None)
        new_state = not cur_val if cur_val is not None else True
        FunktionsErgebnis.objects.create(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion_id=sub_id,
            quelle="manuell",
            **{attr: new_state},
        )

    lookup_key = result.get_lookup_key()
    display_name = (
        result.subquestion.frage_text if result.subquestion else result.funktion.name
    )

    # Reload latest parser/AI entries for rendering after toggle
    parser_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion_id=sub_id,
            quelle="parser",
        )
        .order_by("-created_at")
        .first()
    )
    ai_entry = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=pf,
            funktion=result.funktion,
            subquestion_id=sub_id,
            quelle="ki",
        )
        .order_by("-created_at")
        .first()
    )

    doc_data = {
        "technisch_vorhanden": parser_entry.technisch_verfuegbar
        if parser_entry
        else None,
        "einsatz_bei_telefonica": parser_entry.einsatz_bei_telefonica
        if parser_entry
        else None,
        "zur_lv_kontrolle": parser_entry.zur_lv_kontrolle if parser_entry else None,
        "ki_beteiligung": parser_entry.ki_beteiligung if parser_entry else None,
    }
    ai_data = {
        "technisch_vorhanden": ai_entry.technisch_verfuegbar if ai_entry else None,
        "ki_beteiligung": ai_entry.ki_beteiligung if ai_entry else None,
    }

    manual_data: dict[str, bool] = {}
    for f_key, db_key in field_map.items():
        m_entry = (
            FunktionsErgebnis.objects.filter(
                anlage_datei=pf,
                funktion=result.funktion,
                subquestion_id=sub_id,
                quelle="manuell",
            )
            .exclude(**{db_key: None})
            .order_by("-created_at")
            .first()
        )
        if m_entry is not None:
            manual_data[f_key] = getattr(m_entry, db_key)

    auto_val = _calc_auto_negotiable(
        doc_data.get("technisch_vorhanden"), ai_data.get("technisch_vorhanden")
    )
    manual_gap = _has_manual_gap(doc_data, manual_data)
    if manual_gap:
        result.is_negotiable_manual_override = False
        result.is_negotiable = False
        result.save(update_fields=["is_negotiable_manual_override", "is_negotiable"])
    else:
        if result.is_negotiable_manual_override is not None:
            result.is_negotiable_manual_override = None
            result.is_negotiable = auto_val
            result.save(
                update_fields=["is_negotiable_manual_override", "is_negotiable"]
            )
        elif result.is_negotiable != auto_val:
            result.is_negotiable = auto_val
            result.save(update_fields=["is_negotiable"])

    manual_lookup = {lookup_key: manual_data}
    analysis_lookup = {lookup_key: doc_data}
    verification_lookup = {lookup_key: ai_data}
    result_map = {lookup_key: result}
    form = Anlage2ReviewForm()

    row = _build_row_data(
        display_name,
        lookup_key,
        result.funktion_id,
        f"{'func' if sub_id is None else 'sub'}{result.funktion_id if sub_id is None else sub_id}_",
        form,
        analysis_lookup,
        {},
        {},
        manual_lookup,
        result_map,
        sub_id=sub_id,
    )

    fields_def = get_anlage2_fields()
    context = {
        "row": row,
        "fields": [f[0] for f in fields_def],
        "field_pairs": fields_def,
        "anlage": result.anlage_datei,
    }

    return render(request, "partials/review_row.html", context)


@login_required
@require_POST
def hx_toggle_anlage1_ok(request, pk: int, num: int):
    """Schaltet die VerhandlungsfÃ¤higkeit einer Frage um."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)

    if not _user_can_edit_project(request.user, anlage.project):
        return HttpResponseForbidden("Nicht berechtigt")

    data = anlage.question_review or {}
    entry = data.get(str(num), {})
    entry["ok"] = not entry.get("ok", False)
    data[str(num)] = entry
    anlage.question_review = data
    anlage.save(update_fields=["question_review"])

    context = {"anlage": anlage, "num": num, "is_ok": entry["ok"]}
    if request.headers.get("HX-Request", "").lower() == "true":
        return render(request, "partials/anlage1_negotiable.html", context)
    return redirect("projekt_detail", pk=anlage.project.pk)


@login_required
def hx_anlage1_note(request, pk: int, num: int, field: str):
    """Zeigt oder speichert eine Notiz zu einer Frage aus AnlageÂ 1."""
    if field not in {"hinweis", "vorschlag"}:
        raise Http404

    anlage = get_object_or_404(BVProjectFile, pk=pk)

    if not _user_can_edit_project(request.user, anlage.project):
        return HttpResponseForbidden("Nicht berechtigt")

    data = anlage.question_review or {}
    entry = data.get(str(num), {})
    if request.method == "POST":
        entry[field] = request.POST.get("text", "")
        data[str(num)] = entry
        anlage.question_review = data
        anlage.save(update_fields=["question_review"])
        editing = False
    else:
        editing = request.GET.get("edit") == "1"

    context = {
        "anlage": anlage,
        "num": num,
        "field": field,
        "text": entry.get(field, ""),
        "editing": editing,
    }
    return render(request, "partials/anlage1_note.html", context)


@login_required
@require_POST
def hx_toggle_negotiable(request, result_id: int):
    """Schaltet den Verhandlungsstatus um."""
    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    current = result.is_negotiable_manual_override
    if current is True:
        new_override = False
    elif current is False:
        new_override = None
    else:
        new_override = True

    result.is_negotiable_manual_override = new_override
    if new_override is not None:
        result.is_negotiable = new_override
    else:
        result.is_negotiable = False
    result.save(update_fields=["is_negotiable", "is_negotiable_manual_override"])

    context = {
        "is_negotiable": result.negotiable,
        "override": result.is_negotiable_manual_override,
        "row": {"result_id": result.id},
    }
    return render(request, "partials/negotiable_cell.html", context)


@login_required
def hx_anlage_status(request, pk: int):
    """Gibt den Bearbeitungsstatus einer Anlage 2 zurÃ¼ck."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)

    if not _user_can_edit_project(request.user, anlage.project):
        return HttpResponseForbidden("Nicht berechtigt")

    context = {"anlage": anlage}
    response = render(request, "partials/anlage_status.html", context)
    response.headers["HX-Trigger"] = "refresh-cockpit"
    return response


@login_required
def hx_anlage_row(request, pk: int):
    """Rendert eine einzelne Zeile der Anlagenliste."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)

    if not _user_can_edit_project(request.user, anlage.project):
        return HttpResponseForbidden("Nicht berechtigt")

    context = {"anlage": anlage, "show_nr": False}
    return render(request, "partials/anlagen_row.html", context)


@login_required
def hx_project_anlage_tab(request, pk: int, nr: int):
    """Rendert die Dateiliste fÃ¼r eine Anlage als Tab-Inhalt."""

    projekt = get_object_or_404(BVProject, pk=pk)

    if not _user_can_edit_project(request.user, projekt):
        return HttpResponseForbidden("Nicht berechtigt")

    files_qs = projekt.anlagen.filter(anlage_nr=nr).order_by("-version")
    page = request.GET.get("page") if nr == 3 else None
    page_obj = Paginator(files_qs, 10).get_page(page) if nr == 3 else None
    context = {
        "projekt": projekt,
        "anlagen": page_obj or files_qs,
        "page_obj": page_obj,
        "anlage_nr": nr,
        "show_nr": False,
        "active_file": get_project_file(projekt, nr),
    }
    return render(request, "partials/anlagen_tab.html", context)


@login_required
def hx_project_software_tab(request, pk: int, tab: str):
    """Rendert die Software-Tab-Inhalte per HTMX."""

    projekt = get_object_or_404(BVProject, pk=pk)

    is_admin = request.user.groups.filter(name__iexact="admin").exists()
    has_project_access = _user_can_edit_project(request.user, projekt)
    if not (is_admin or has_project_access):
        return HttpResponseForbidden("Nicht berechtigt")

    software_list = projekt.software_list
    knowledge_map = {k.software_name: k for k in projekt.softwareknowledge.all()}
    knowledge_rows = []
    checked = 0
    for name in software_list:
        entry = knowledge_map.get(name)
        if entry and entry.last_checked:
            checked += 1
        knowledge_rows.append({"name": name, "entry": entry})

    template = (
        "partials/software_tab_basic.html"
        if tab == "tech"
        else "partials/software_tab_gutachten.html"
    )

    context = {
        "projekt": projekt,
        "knowledge_rows": knowledge_rows,
        "knowledge_checked": checked,
        "total_software": len(software_list),
        "has_project_access": has_project_access,
    }
    return render(request, template, context)


@login_required
def hx_project_cockpit(request, pk: int):
    """LÃ¤dt die Cockpit-Ansicht eines Projekts per HTMX."""

    projekt = get_object_or_404(BVProject, pk=pk)
    context = get_cockpit_context(projekt)
    return render(request, "projekt_cockpit.html", context)


@login_required
@require_POST
def hx_project_file_upload(request, pk: int):
    """LÃ¤dt eine einzelne Datei per HTMX hoch."""

    projekt = get_object_or_404(BVProject, pk=pk)

    if not _user_can_edit_project(request.user, projekt):
        return HttpResponseForbidden("Nicht berechtigt")

    upload = request.FILES.get("upload")
    anlage_nr_raw = request.POST.get("anlage_nr")

    if not upload:
        return HttpResponseBadRequest("invalid")

    anlage_nr: int | None = None
    if anlage_nr_raw:
        try:
            anlage_nr = int(anlage_nr_raw)
        except (TypeError, ValueError):
            anlage_nr = None
    if anlage_nr is None:
        try:
            anlage_nr = extract_anlage_nr(upload.name)
        except ValueError:
            anlage_nr = None

    data = request.POST.copy()
    if anlage_nr is not None and not data.get("anlage_nr"):
        data["anlage_nr"] = str(anlage_nr)

    # ``request.FILES`` kann bei ``multiple``-Uploads eine Liste enthalten.
    # Das Formular erwartet jedoch genau eine Datei.
    form = BVProjectFileForm(data, {"upload": upload}, anlage_nr=anlage_nr)

    if form.is_valid() and anlage_nr:
        saved_file = _save_project_file(projekt, form=form)
        context = {
            "projekt": projekt,
            "anlage": saved_file,
            "show_nr": False,
        }
        response = render(request, "partials/anlagen_row.html", context)
        response.headers["HX-Trigger"] = "refresh-cockpit"
        return response

    context = {
        "projekt": projekt,
        "form": form,
        "show_nr": False,
    }
    response = render(request, "partials/anlagen_row.html", context, status=400)
    response.headers["HX-Trigger"] = "refresh-cockpit"
    return response


@login_required
@require_POST
def trigger_file_analysis(request, pk: int) -> JsonResponse:
    """L\u00f6st die Analyse f\u00fcr eine bestehende Datei erneut aus."""
    file_obj = get_object_or_404(BVProjectFile, pk=pk)

    if not _user_can_edit_project(request.user, file_obj.project):
        return HttpResponseForbidden("Nicht berechtigt")

    task_id = start_analysis_for_file(file_obj.pk)
    return JsonResponse({"task_id": task_id})


@login_required
def edit_gap_notes(request, result_id: int):
    """Zeigt einen Hinweis fÃ¼r automatisch erzeugte Gap-Notizen."""

    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    pf = get_project_file(result.anlage_datei.project, 2)
    context = {"result": result, "project_file": pf}
    return render(request, "gap_notes_form.html", context)


@login_required
@require_POST
def ajax_generate_gap_summary(request, result_id: int) -> JsonResponse:
    """Startet die Generierung einer Gap-Zusammenfassung."""

    result = get_object_or_404(AnlagenFunktionsMetadaten, pk=result_id)

    if not _user_can_edit_project(request.user, result.anlage_datei.project):
        return HttpResponseForbidden("Nicht berechtigt")

    task_id = async_task(
        "core.llm_tasks.worker_generate_gap_summary",
        result.id,
    )
    return JsonResponse({"status": "queued", "task_id": task_id})


@login_required
@require_POST
def ajax_reset_all_reviews(request, pk: int) -> JsonResponse:
    """Setzt alle manuellen Bewertungen fÃ¼r Anlage 2 zurÃ¼ck."""

    project_file = get_object_or_404(BVProjectFile, pk=pk)
    if project_file.anlage_nr != 2:
        return JsonResponse({"error": "invalid"}, status=400)

    # Nur manuelle Ã„nderungen entfernen, automatische Ergebnisse beibehalten
    AnlagenFunktionsMetadaten.objects.filter(anlage_datei=project_file).update(
        is_negotiable_manual_override=None
    )
    FunktionsErgebnis.objects.filter(
        anlage_datei=project_file, quelle="manuell"
    ).delete()

    return JsonResponse({"status": "success"})


@login_required
@require_http_methods(["POST"])
def project_file_toggle_flag(request, pk: int, field: str):
    """Setzt ein Bool-Feld bei einer Anlage."""
    if field not in {"manual_reviewed", "verhandlungsfaehig"}:
        return HttpResponseBadRequest("invalid")
    project_file = get_object_or_404(BVProjectFile, pk=pk)
    value = request.POST.get("value")
    new_val = value in ("1", "true", "True", "on")
    setattr(project_file, field, new_val)
    project_file.save(update_fields=[field])
    if (
        field == "verhandlungsfaehig"
        and project_file.project.is_verhandlungsfaehig
    ):
        try:
            set_project_status(project_file.project, "DONE")
        except ValueError:
            pass
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "ok", field: new_val})
    if "HTTP_REFERER" in request.META:
        return redirect(request.META["HTTP_REFERER"])
    return redirect("projekt_detail", pk=project_file.project.pk)


@login_required
@require_POST
def hx_toggle_project_file_flag(request, pk: int, field: str):
    """Wie :func:`project_file_toggle_flag`, gibt aber die Zeile als Partial zurÃ¼ck."""
    if field not in {"manual_reviewed", "verhandlungsfaehig"}:
        return HttpResponseBadRequest("invalid")

    project_file = get_object_or_404(BVProjectFile, pk=pk)
    value = request.POST.get("value")
    new_val = value in ("1", "true", "True", "on")
    setattr(project_file, field, new_val)
    project_file.save(update_fields=[field])

    if (
        field == "verhandlungsfaehig"
        and project_file.project.is_verhandlungsfaehig
    ):
        try:
            set_project_status(project_file.project, "DONE")
        except ValueError:
            pass

    response = hx_anlage_row(request, pk)
    response.headers["HX-Trigger"] = "refresh-cockpit"
    return response


@login_required
@require_http_methods(["POST"])
def projekt_file_delete_result(request, pk: int):
    """LÃ¶scht Analyse- und Review-Ergebnisse einer Anlage."""
    project_file = get_object_or_404(BVProjectFile, pk=pk)

    if project_file.anlage_nr == 2:
        AnlagenFunktionsMetadaten.objects.filter(anlage_datei=project_file).delete()
        AnlagenFunktionsMetadaten.objects.filter(anlage_datei=project_file).update(
            is_negotiable=False, is_negotiable_manual_override=None
        )

    project_file.analysis_json = None
    project_file.manual_reviewed = False
    project_file.verhandlungsfaehig = False
    project_file.save(
        update_fields=[
            "analysis_json",
            "manual_reviewed",
            "verhandlungsfaehig",
        ]
    )

    if project_file.anlage_nr == 3:
        return redirect("anlage3_review", pk=project_file.project.pk)
    return redirect("projekt_detail", pk=project_file.project.pk)


@login_required
@require_http_methods(["POST"])
def delete_project_file_version(request, pk: int):
    """LÃ¶scht eine Anlagenversion."""

    project_file = get_object_or_404(BVProjectFile, pk=pk)

    if not _user_can_edit_project(request.user, project_file.project):
        return HttpResponseForbidden("Nicht berechtigt")

    with transaction.atomic():
        is_active = project_file.is_active
        parent = project_file.parent
        successor = BVProjectFile.objects.filter(parent=project_file).first()

        if project_file.upload:
            (Path(settings.MEDIA_ROOT) / project_file.upload.name).unlink(
                missing_ok=True
            )

        project_file.delete()

        if is_active and parent:
            parent.is_active = True
            parent.save(update_fields=["is_active"])
        elif not is_active and successor:
            successor.parent = parent
            successor.save(update_fields=["parent"])

    messages.success(request, "Die Version wurde erfolgreich gelöscht.")
    return redirect("projekt_detail", pk=project_file.project.pk)


@login_required
def projekt_gap_analysis(request, pk):
    """Stellt die Gap-Analyse als Download bereit."""
    projekt = get_object_or_404(BVProject, pk=pk)
    path = generate_gap_analysis(projekt)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@login_required
def projekt_management_summary(request, pk):
    """Stellt die Management-Zusammenfassung als Download bereit."""
    projekt = get_object_or_404(BVProject, pk=pk)
    path = generate_management_summary(projekt)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@login_required
def projekt_gap_report(request, pk):
    """Erzeugt einen GAP-Bericht f\u00fcr den Fachbereich (gesamt)."""
    projekt = get_object_or_404(BVProject, pk=pk)
    if not _user_can_edit_project(request.user, projekt):
        return HttpResponseForbidden("Nicht berechtigt")

    pf1 = get_project_file(projekt, 1)
    pf2 = get_project_file(projekt, 2)

    if request.method == "POST":
        if pf1:
            pf1.gap_summary = request.POST.get("text1", "")
            pf1.save(update_fields=["gap_summary"])
        if pf2:
            pf2.gap_summary = request.POST.get("text2", "")
            pf2.save(update_fields=["gap_summary"])
        messages.success(request, "Bericht gespeichert")
        return redirect("projekt_detail", pk=projekt.pk)

    text1 = summarize_anlage1_gaps(projekt, pf1)
    text2 = summarize_anlage2_gaps(projekt, pf2)

    if pf1 and pf1.gap_summary:
        text1 = pf1.gap_summary
    if pf2 and pf2.gap_summary:
        text2 = pf2.gap_summary

    context = {"projekt": projekt, "text1": text1, "text2": text2}
    return render(request, "gap_report.html", context)


@login_required
def anlage_gap_report(request, pk, nr):
    """Erzeugt einen GAP-Bericht f\u00fcr eine einzelne Anlage."""
    projekt = get_object_or_404(BVProject, pk=pk)
    if not _user_can_edit_project(request.user, projekt):
        return HttpResponseForbidden("Nicht berechtigt")

    pf = get_project_file(projekt, nr)
    if not pf:
        raise Http404("Anlage nicht gefunden")

    if request.method == "POST":
        pf.gap_summary = request.POST.get("text", "")
        pf.save(update_fields=["gap_summary"])
        messages.success(request, "Bericht gespeichert")
        return redirect("projekt_detail", pk=projekt.pk)

    if nr == 1:
        text = summarize_anlage1_gaps(projekt, pf)
    elif nr == 2:
        text = summarize_anlage2_gaps(projekt, pf)
    else:
        raise Http404("Unbekannte Anlage")

    if pf.gap_summary:
        text = pf.gap_summary

    context = {
        "projekt": projekt,
        "text": text,
        "nr": nr,
        "label": f"Anlage {nr}",
    }
    return render(request, "gap_report_single.html", context)


@login_required
@require_http_methods(["POST"])
def delete_gap_report(request, pk):
    """Verwirft vorhandene GAP-Berichte."""
    projekt = get_object_or_404(BVProject, pk=pk)
    if not _user_can_edit_project(request.user, projekt):
        return HttpResponseForbidden("Nicht berechtigt")

    pf1 = get_project_file(projekt, 1)
    pf2 = get_project_file(projekt, 2)

    if pf1:
        pf1.gap_summary = ""
        pf1.save(update_fields=["gap_summary"])
    if pf2:
        pf2.gap_summary = ""
        pf2.save(update_fields=["gap_summary"])

    messages.success(request, "GAP-Bericht verworfen")
    return redirect("projekt_detail", pk=projekt.pk)


@login_required
@require_POST
def ajax_start_gutachten_generation(request, project_id):
    """Startet die Gutachten-Erstellung als Hintergrund-Task."""
    knowledge_id = request.POST.get("knowledge_id")
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid"}, status=400)

    if not SoftwareKnowledge.objects.filter(
        pk=knowledge_id, project_id=project_id
    ).exists():
        return JsonResponse({"error": "invalid"}, status=400)

    task_id = async_task(
        "core.llm_tasks.worker_generate_gutachten",
        project_id,
        knowledge_id,
        timeout=600,
    )
    return JsonResponse({"status": "queued", "task_id": task_id})


@login_required
def gutachten_download(request, pk):
    """Stellt das Gutachten als formatiertes DOCX bereit."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.project

    markdown_text = gutachten.text
    temp_file_path = os.path.join(tempfile.gettempdir(), f"gutachten_{pk}.docx")

    try:
        extensions = ["extra", "admonition", "toc"]
        html_content = markdown.markdown(markdown_text, extensions=extensions)

        pypandoc.convert_text(
            html_content,
            "docx",
            format="html",
            outputfile=temp_file_path,
        )

        with open(temp_file_path, "rb") as docx_file:
            response = HttpResponse(
                docx_file.read(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            response["Content-Disposition"] = (
                f'attachment; filename="Gutachten_{projekt.title}.docx"'
            )
            return response

    except (IOError, OSError) as e:
        logger.error(
            f"Pandoc-Fehler beim Erstellen des Gutachtens f\u00fcr Projekt {projekt.id}: {e}"
        )
        messages.error(
            request,
            "Fehler beim Erstellen des Word-Dokuments. Ist Pandoc auf dem Server korrekt installiert?",
        )
        return redirect("projekt_detail", pk=projekt.pk)

    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


class ZweckKategorieAListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    """Liste aller Zwecke der Kategorie A."""

    model = ZweckKategorieA
    template_name = "core/zweckkategoriea_list.html"


class ZweckKategorieACreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    """Erstellt einen neuen Zweck."""

    model = ZweckKategorieA
    form_class = ZweckKategorieAForm
    template_name = "core/zweckkategoriea_form.html"
    success_url = reverse_lazy("zweckkategoriea_list")


class ZweckKategorieAUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    """Bearbeitet einen vorhandenen Zweck."""

    model = ZweckKategorieA
    form_class = ZweckKategorieAForm
    template_name = "core/zweckkategoriea_form.html"
    success_url = reverse_lazy("zweckkategoriea_list")


class ZweckKategorieADeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    """LÃ¶scht einen Zweck nach BestÃ¤tigung."""

    model = ZweckKategorieA
    template_name = "core/zweckkategoriea_confirm_delete.html"
    success_url = reverse_lazy("zweckkategoriea_list")


class SupervisionNoteListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    """Listet alle Standardnotizen fÃ¼r die Supervision auf."""

    model = SupervisionStandardNote
    template_name = "core/supervisionnote_list.html"


class SupervisionNoteCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    """Erstellt eine neue Standardnotiz."""

    model = SupervisionStandardNote
    form_class = SupervisionStandardNoteForm
    template_name = "core/supervisionnote_form.html"
    success_url = reverse_lazy("supervisionnote_list")


class SupervisionNoteUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    """Bearbeitet eine vorhandene Standardnotiz."""

    model = SupervisionStandardNote
    form_class = SupervisionStandardNoteForm
    template_name = "core/supervisionnote_form.html"
    success_url = reverse_lazy("supervisionnote_list")


class SupervisionNoteDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    """LÃ¶scht eine Standardnotiz nach BestÃ¤tigung."""

    model = SupervisionStandardNote
    template_name = "core/supervisionnote_confirm_delete.html"
    success_url = reverse_lazy("supervisionnote_list")


class Anlage3ParserRuleListView(LoginRequiredMixin, StaffRequiredMixin, ListView):
    """Listet alle Parser-Regeln fÃ¼r AnlageÂ 3 auf."""

    model = Anlage3ParserRule
    template_name = "core/anlage3_rule_list.html"


class Anlage3ParserRuleCreateView(LoginRequiredMixin, StaffRequiredMixin, CreateView):
    """Erstellt eine neue Parser-Regel fÃ¼r AnlageÂ 3."""

    model = Anlage3ParserRule
    form_class = Anlage3ParserRuleForm
    template_name = "core/anlage3_rule_form.html"
    success_url = reverse_lazy("anlage3_rule_list")


class Anlage3ParserRuleUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    """Bearbeitet eine vorhandene Parser-Regel fÃ¼r AnlageÂ 3."""

    model = Anlage3ParserRule
    form_class = Anlage3ParserRuleForm
    template_name = "core/anlage3_rule_form.html"
    success_url = reverse_lazy("anlage3_rule_list")


class Anlage3ParserRuleDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    """LÃ¶scht eine Parser-Regel fÃ¼r AnlageÂ 3 nach BestÃ¤tigung."""

    model = Anlage3ParserRule
    template_name = "core/anlage3_rule_confirm_delete.html"
    success_url = reverse_lazy("anlage3_rule_list")


@login_required
def gutachten_edit(request, pk):
    """ErmÃ¶glicht das Bearbeiten und erneute Speichern des Gutachtens."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.project
    if request.method == "POST":
        text = request.POST.get("text", "")
        gutachten.text = text
        gutachten.save(update_fields=["text"])
        messages.success(request, "Gutachten gespeichert")
        return redirect("projekt_initial_pruefung", pk=projekt.pk)
    return render(
        request, "gutachten_edit.html", {"projekt": projekt, "text": gutachten.text}
    )


@login_required
@require_http_methods(["POST"])
def gutachten_delete(request, pk):
    """LÃ¶scht das Gutachten und entfernt den Verweis im Projekt."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.project
    gutachten.delete()
    return redirect("projekt_detail", pk=projekt.pk)


@login_required
@require_http_methods(["POST"])
def gutachten_llm_check(request, pk):
    """LÃ¶st den LLM-Funktionscheck fÃ¼r das Gutachten aus."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.project
    messages.info(request, "Der LLM-Funktionscheck ist deaktiviert.")
    return redirect("projekt_initial_pruefung", pk=projekt.pk)


@login_required
def edit_ki_justification(request, pk):
    """Erlaubt das Bearbeiten der KI-BegrÃ¼ndung."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)
    if anlage.anlage_nr != 2:
        raise Http404

    func_id = request.GET.get("function") or request.POST.get("function")
    sub_id = request.GET.get("subquestion") or request.POST.get("subquestion")
    if func_id:
        obj = get_object_or_404(Anlage2Function, pk=func_id)
        key = obj.name
        obj_type = "function"
    elif sub_id:
        obj = get_object_or_404(Anlage2SubQuestion, pk=sub_id)
        key = f"{obj.funktion.name}: {obj.frage_text}"
        obj_type = "subquestion"
    else:
        return HttpResponseBadRequest("invalid")

    res_qs = AnlagenFunktionsMetadaten.objects.filter(
        anlage_datei=anlage,
        funktion=obj if obj_type == "function" else obj.funktion,
        subquestion=obj if obj_type == "subquestion" else None,
    )
    res = res_qs.first()

    fe = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=anlage,
            funktion=obj if obj_type == "function" else obj.funktion,
            subquestion=obj if obj_type == "subquestion" else None,
            quelle="ki",
        )
        .order_by("-created_at")
        .first()
    )

    if request.method == "POST":
        new_text = request.POST.get("ki_begruendung", "")
        field = request.GET.get("field") or request.POST.get("field") or "begruendung"
        if fe:
            if field == "ki_beteiligt_begruendung":
                fe.ki_beteiligt_begruendung = new_text
                fe.save(update_fields=["ki_beteiligt_begruendung"])
            else:
                fe.begruendung = new_text
                fe.save(update_fields=["begruendung"])
        else:
            create_kwargs = {
                "anlage_datei": anlage,
                "funktion": obj if obj_type == "function" else obj.funktion,
                "subquestion": obj if obj_type == "subquestion" else None,
                "quelle": "ki",
            }
            if field == "ki_beteiligt_begruendung":
                create_kwargs["ki_beteiligt_begruendung"] = new_text
            else:
                create_kwargs["begruendung"] = new_text
            FunktionsErgebnis.objects.create(**create_kwargs)
        messages.success(request, "BegrÃ¼ndung gespeichert")
        return redirect("projekt_file_edit_json", pk=anlage.pk)

    field = request.GET.get("field") or "begruendung"
    initial_text = ""
    if fe:
        initial_text = (
            fe.ki_beteiligt_begruendung
            if field == "ki_beteiligt_begruendung"
            else fe.begruendung
        ) or ""

    context = {
        "anlage": anlage,
        "object": obj,
        "object_type": obj_type,
        "ki_begruendung": initial_text,
    }
    return render(request, "edit_ki_justification.html", context)


@login_required
def justification_detail_edit(request, file_id, function_key):
    """Zeigt und bearbeitet die KI-BegrÃ¼ndung zu einer Funktion."""

    anlage = get_object_or_404(BVProjectFile, pk=file_id)
    if anlage.anlage_nr != 2:
        raise Http404

    func_name = function_key
    sub_text = None
    if ":" in function_key:
        func_name, sub_text = [p.strip() for p in function_key.split(":", 1)]

    funktion = get_object_or_404(Anlage2Function, name=func_name)
    subquestion = None
    if sub_text:
        subquestion = get_object_or_404(
            Anlage2SubQuestion, funktion=funktion, frage_text=sub_text
        )

    fe = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=anlage,
            funktion=funktion,
            subquestion=subquestion,
            quelle="ki",
        )
        .order_by("-created_at")
        .first()
    )

    initial_text = fe.begruendung if fe and fe.begruendung else ""

    if request.method == "POST":
        form = JustificationForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["justification"]
            if fe:
                fe.begruendung = text
                fe.save(update_fields=["begruendung"])
            else:
                FunktionsErgebnis.objects.create(
                    anlage_datei=anlage,
                    funktion=funktion,
                    subquestion=subquestion,
                    quelle="ki",
                    begruendung=text,
                )
            messages.success(request, "BegrÃ¼ndung gespeichert")
            return redirect("projekt_file_edit_json", pk=anlage.pk)
    else:
        form = JustificationForm(initial={"justification": initial_text})

    justification_html = markdownify(initial_text)
    breadcrumbs = [
        {"url": reverse("projekt_list"), "label": "Projekte"},
        {
            "url": reverse("projekt_detail", args=[anlage.project.pk]),
            "label": anlage.project.title,
        },
        {
            "url": reverse("projekt_file_edit_json", args=[anlage.pk]),
            "label": f"Anlage {anlage.anlage_nr}",
        },
        {"label": function_key},
    ]

    context = {
        "project_file": anlage,
        "function_name": function_key,
        "form": form,
        "justification_html": justification_html,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "justification_detail.html", context)


@login_required
def ki_involvement_detail_edit(request, file_id, function_key):
    """Zeigt und bearbeitet die BegrÃ¼ndung zur KI-Beteiligung."""

    anlage = get_object_or_404(BVProjectFile, pk=file_id)
    if anlage.anlage_nr != 2:
        raise Http404

    func_name = function_key
    sub_text = None
    if ":" in function_key:
        func_name, sub_text = [p.strip() for p in function_key.split(":", 1)]

    funktion = get_object_or_404(Anlage2Function, name=func_name)
    subquestion = None
    if sub_text:
        subquestion = get_object_or_404(
            Anlage2SubQuestion,
            funktion=funktion,
            frage_text=sub_text,
        )

    fe = (
        FunktionsErgebnis.objects.filter(
            anlage_datei=anlage,
            funktion=funktion,
            subquestion=subquestion,
            quelle="ki",
        )
        .order_by("-created_at")
        .first()
    )

    initial_text = (
        fe.ki_beteiligt_begruendung if fe and fe.ki_beteiligt_begruendung else ""
    )

    if request.method == "POST":
        form = JustificationForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["justification"]
            if fe:
                fe.ki_beteiligt_begruendung = text
                fe.save(update_fields=["ki_beteiligt_begruendung"])
            else:
                FunktionsErgebnis.objects.create(
                    anlage_datei=anlage,
                    funktion=funktion,
                    subquestion=subquestion,
                    quelle="ki",
                    ki_beteiligt_begruendung=text,
                )
            messages.success(request, "BegrÃ¼ndung gespeichert")
            return redirect("projekt_file_edit_json", pk=anlage.pk)
    else:
        form = JustificationForm(initial={"justification": initial_text})

    involvement_html = markdownify(initial_text)
    breadcrumbs = [
        {"url": reverse("projekt_list"), "label": "Projekte"},
        {
            "url": reverse("projekt_detail", args=[anlage.project.pk]),
            "label": anlage.project.title,
        },
        {
            "url": reverse("projekt_file_edit_json", args=[anlage.pk]),
            "label": f"Anlage {anlage.anlage_nr}",
        },
        {"label": function_key},
    ]

    context = {
        "project_file": anlage,
        "function_name": function_key,
        "form": form,
        "involvement_html": involvement_html,
        "breadcrumbs": breadcrumbs,
    }
    return render(request, "involvement_detail.html", context)


@login_required
def justification_delete(request, file_id, function_key):
    """LÃ¶scht die KI-BegrÃ¼ndung fÃ¼r einen FunktionsschlÃ¼ssel."""

    anlage = get_object_or_404(BVProjectFile, pk=file_id)
    if anlage.anlage_nr != 2:
        raise Http404

    res = AnlagenFunktionsMetadaten.objects.filter(
        anlage_datei=anlage,
        funktion__name=function_key,
        subquestion__isnull=True,
    ).first()
    messages.success(request, "Begründung gelöscht")

    return redirect("projekt_file_edit_json", pk=anlage.pk)


@login_required
@require_POST
def ajax_start_initial_checks(request, project_id):
    """Startet den Initialcheck fÃ¼r alle Software-Typen eines Projekts."""
    projekt = get_object_or_404(BVProject, pk=project_id)
    names = projekt.software_list
    tasks = []
    for name in names:
        sk, _ = SoftwareKnowledge.objects.get_or_create(
            project=projekt,
            software_name=name,
        )
        tid = async_task(
            "core.llm_tasks.worker_run_initial_check",
            sk.pk,
        )
        tasks.append({"software": name, "task_id": tid})
    return JsonResponse({"status": "queued", "tasks": tasks})


@login_required
@require_POST
def ajax_rerun_initial_check(request) -> JsonResponse:
    """Startet den Initial-Check erneut."""

    knowledge_id = request.POST.get("knowledge_id")
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid"}, status=400)

    if not SoftwareKnowledge.objects.filter(pk=knowledge_id).exists():
        return JsonResponse({"error": "invalid"}, status=400)

    task_id = async_task(
        "core.llm_tasks.worker_run_initial_check",
        knowledge_id,
    )
    return JsonResponse({"status": "queued", "task_id": task_id})


@login_required
@require_POST
async def ajax_docx_preview(request) -> JsonResponse:
    """Konvertiert eine DOCX-Datei in HTML fÃ¼r die Vorschau."""

    upload = request.FILES.get("docx")
    if not upload:
        return JsonResponse({"error": "no file"}, status=400)

    def _convert() -> str:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            for chunk in upload.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            return pypandoc.convert_file(tmp_path, "html")
        finally:
            os.unlink(tmp_path)

    try:
        html = await asyncio.to_thread(_convert)
    except Exception as exc:  # pragma: no cover - Conversion kann fehlschlagen
        logger.exception("Fehler bei der DOCX-Vorschau: %s", exc)
        return JsonResponse({"error": "conversion failed"}, status=500)

    return JsonResponse({"html": html})


@login_required
def edit_project_context(request, pk):
    """Bearbeitet den Projekt-Kontext."""
    projekt = get_object_or_404(BVProject, pk=pk)
    if request.method == "POST":
        form = ProjectContextForm(request.POST, instance=projekt)
        if form.is_valid():
            form.save()
            messages.success(request, "Projekt-Kontext gespeichert")
            return redirect("projekt_detail", pk=projekt.pk)
    else:
        form = ProjectContextForm(instance=projekt)
    return render(
        request,
        "edit_project_context.html",
        {"form": form, "projekt": projekt},
    )


@login_required
def edit_knowledge_description(request, knowledge_id):
    """Bearbeitet die Beschreibung eines Knowledge-Eintrags."""
    knowledge = get_object_or_404(SoftwareKnowledge, pk=knowledge_id)
    if request.method == "POST":
        form = KnowledgeDescriptionForm(request.POST, instance=knowledge)
        if form.is_valid():
            form.save()
            messages.success(request, "Beschreibung gespeichert")
            return redirect("projekt_detail", pk=knowledge.project.pk)
    else:
        form = KnowledgeDescriptionForm(instance=knowledge)
    return render(
        request,
        "edit_knowledge_description.html",
        {"form": form, "knowledge": knowledge},
    )


@login_required
@require_POST
def delete_knowledge_entry(request, knowledge_id):
    """LÃ¶scht einen Knowledge-Eintrag."""
    knowledge = get_object_or_404(SoftwareKnowledge, pk=knowledge_id)
    projekt = knowledge.project
    # Strikte Löschberechtigung: Admin/Staff/Superuser, Owner oder Team
    is_admin_group = request.user.groups.filter(name__iexact="admin").exists()
    is_staff_or_super = request.user.is_staff or request.user.is_superuser
    is_owner = hasattr(projekt, "user_id") and projekt.user_id == request.user.id
    in_team = hasattr(projekt, "team_members") and projekt.team_members.filter(pk=request.user.pk).exists()
    if not (is_admin_group or is_staff_or_super or is_owner or in_team):
        raise PermissionDenied
    project_pk = projekt.pk
    knowledge.delete()
    return redirect("projekt_detail", pk=project_pk)


@login_required
def download_knowledge_as_word(request, knowledge_id):
    """Stellt die Beschreibung als Word-Datei bereit."""
    knowledge = get_object_or_404(SoftwareKnowledge, pk=knowledge_id)
    if not knowledge.description:
        raise Http404
    temp_file_path = os.path.join(
        tempfile.gettempdir(), f"knowledge_{knowledge_id}.docx"
    )
    try:
        extensions = ["extra", "admonition", "toc"]
        html_content = markdown.markdown(knowledge.description, extensions=extensions)
        pypandoc.convert_text(
            html_content,
            "docx",
            format="html",
            outputfile=temp_file_path,
        )
        with open(temp_file_path, "rb") as fh:
            response = HttpResponse(
                fh.read(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{knowledge.software_name}.docx"'
            )
            return response
    except (IOError, OSError) as e:
        logger.error("Pandoc-Fehler beim Knowledge-Export %s", e)
        messages.error(
            request,
            "Fehler beim Erstellen des Word-Dokuments. Ist Pandoc auf dem Server korrekt installiert?",
        )
        return redirect("projekt_detail", pk=knowledge.project.pk)
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


def _compare_versions_anlage1(
    request: HttpRequest,
    project_file: BVProjectFile,
    parent: BVProjectFile,
) -> HttpResponse:
    """Spezielle Vergleichslogik fÃ¼r Anlage 1."""

    if request.method == "POST":
        action = request.POST.get("action")
        if not _user_can_edit_project(request.user, project_file.project):
            return HttpResponseForbidden("Nicht berechtigt")
        if action == "negotiate":
            project_file.verhandlungsfaehig = True
            project_file.save(update_fields=["verhandlungsfaehig"])
        return redirect("compare_versions", pk=project_file.pk)

    questions_map = {str(q.num): q.text for q in Anlage1Question.objects.all()}
    parent_review = parent.question_review or {}
    parent_analysis = parent.analysis_json.get("questions", {}) if parent.analysis_json else {}
    current_analysis = (
        project_file.analysis_json.get("questions", {})
        if project_file.analysis_json
        else {}
    )

    gap_rows = []
    for num, pdata in parent_review.items():
        if isinstance(pdata, dict) and (pdata.get("hinweis") or pdata.get("vorschlag")):
            gap_rows.append(
                {
                    "num": num,
                    "text": questions_map.get(num, f"Frage {num}"),
                    "parent": {**parent_analysis.get(num, {}), **pdata},
                    "current": current_analysis.get(num, {}),
                }
            )

    all_nums = sorted(
        set(parent_analysis.keys()) | set(current_analysis.keys()), key=lambda x: int(x)
    )
    all_rows = []
    for num in all_nums:
        pdata = parent_analysis.get(num, {})
        cdata = current_analysis.get(num, {})
        all_rows.append(
            {
                "num": num,
                "text": questions_map.get(num, f"Frage {num}"),
                "parent": pdata,
                "current": cdata,
                "changed": pdata != cdata,
            }
        )

    context = {
        "file": project_file,
        "parent": parent,
        "gap_rows": gap_rows,
        "all_rows": all_rows,
    }
    return render(request, "version_compare_anlage1.html", context)


@login_required
def compare_versions(request: HttpRequest, pk: int) -> HttpResponse:
    """Vergleicht eine Datei mit ihrer VorgÃ¤ngerversion."""

    project_file = get_object_or_404(BVProjectFile, pk=pk)
    parent = project_file.parent
    if not parent:
        raise Http404

    if project_file.anlage_nr == 1:
        return _compare_versions_anlage1(request, project_file, parent)

    if request.method == "POST":
        result_id = int(request.POST.get("result_id", 0))
        action = request.POST.get("action")
        result = get_object_or_404(
            AnlagenFunktionsMetadaten, pk=result_id, anlage_datei=parent
        )
        if not _user_can_edit_project(request.user, project_file.project):
            return HttpResponseForbidden("Nicht berechtigt")
        if action == "fix":
            result.gap_summary = ""
            result.gap_notiz = ""
            result.save(update_fields=["gap_summary", "gap_notiz"])
        elif action == "carry":
            AnlagenFunktionsMetadaten.objects.update_or_create(
                anlage_datei=project_file,
                funktion=result.funktion,
                subquestion=result.subquestion,
                defaults={
                    "gap_summary": result.gap_summary,
                    "gap_notiz": result.gap_notiz,
                    "is_negotiable": result.is_negotiable,
                },
            )
        return HttpResponse("", status=204)

    parent_gaps = (
        AnlagenFunktionsMetadaten.objects.filter(anlage_datei=parent)
        .filter(
            Q(gap_summary__isnull=False) & ~Q(gap_summary="")
            | Q(gap_notiz__isnull=False) & ~Q(gap_notiz="")
        )
        .select_related("funktion", "subquestion")
    )

    context = {
        "file": project_file,
        "parent": parent,
        "parent_gaps": parent_gaps,
    }
    return render(request, "version_compare.html", context)


@login_required
def anlage5_dummy(request):
    """Zeigt einen Platzhalter f\xfcr Anlage 5."""
    return render(request, "anlage5_dummy.html")


@login_required
def anlage6_review(request, pk):
    """Erm\u00f6glicht die manuelle Sichtpr\u00fcfung von Anlage 6."""

    project_file = get_object_or_404(BVProjectFile, pk=pk)
    if project_file.anlage_nr != 6:
        raise Http404

    if request.method == "POST":
        gap_form = BVGapNotesForm(request.POST, instance=project_file)
        if set(request.POST.keys()) <= {"csrfmiddlewaretoken", "gap_summary", "gap_notiz"}:
            if gap_form.is_valid():
                gap_form.save()
                return redirect("projekt_detail", pk=project_file.project.pk)
        form = Anlage6ReviewForm(request.POST, instance=project_file)
        if form.is_valid() and gap_form.is_valid():
            form.save()
            gap_form.save()
            return redirect("projekt_detail", pk=project_file.project.pk)
    else:
        form = Anlage6ReviewForm(instance=project_file)
        gap_form = BVGapNotesForm(instance=project_file)

    context = {"anlage": project_file, "form": form, "gap_form": gap_form}
    return render(request, "projekt_file_anlage6_review.html", context)
