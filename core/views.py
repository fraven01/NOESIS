from pathlib import Path
import tempfile
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Group, Permission
from django.http import (
    HttpResponseBadRequest,
    Http404,
    HttpResponse,
)
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.contrib import messages
from django.http import JsonResponse, FileResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.urls import reverse
from typing import Any
import io
import zipfile
from django.db import transaction
import subprocess
import whisper
import torch
import json
from django_q.tasks import async_task, fetch, result, Task

from .forms import (
    RecordingForm,
    BVProjectForm,
    BVProjectUploadForm,
    BVProjectFileForm,
    BVProjectFileJSONForm,
    Anlage1ReviewForm,
    Anlage2ReviewForm,
    Anlage4ReviewForm,
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

    ProjectStatusForm,
    ProjectStatusImportForm,
    LLMRoleForm,
    LLMRoleImportForm,
    UserPermissionsForm,
    UserImportForm,
    Anlage2ConfigImportForm,
    ProjectImportForm,
    AntwortErkennungsRegelForm,
    Anlage4ParserConfigForm,

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
    Anlage2FunctionResult,
    SoftwareKnowledge,
    Gutachten,
    Tile,
    Area,
    ProjectStatus,
    LLMRole,
    FormatBParserRule,
    AntwortErkennungsRegel,
    Anlage4Config,
    Anlage4ParserConfig,
)
from .docx_utils import extract_text
from .llm_utils import query_llm
from .workflow import set_project_status
from .reporting import generate_gap_analysis, generate_management_summary
from .llm_tasks import (
    check_anlage1,
    analyse_anlage3,
    check_anlage2,
    check_anlage3_vision,
    analyse_anlage4,
    analyse_anlage4_async,
    check_anlage2_functions,
    run_anlage2_analysis,
    check_gutachten_functions,
    generate_gutachten,
    get_prompt,
    ANLAGE1_QUESTIONS,
)

from .decorators import admin_required, tile_required
from .obs_utils import start_recording, stop_recording, is_recording
from django.forms import formset_factory, modelformset_factory

import logging
import sys
import copy

import time

import markdown
import pypandoc
from django.conf import settings
from .templatetags.recording_extras import markdownify

logger = logging.getLogger(__name__)
debug_logger = logging.getLogger("parser_debug")
admin_a2_logger = logging.getLogger("anlage2_admin_debug")
anlage2_logger = logging.getLogger("anlage2_debug")
anlage4_logger = logging.getLogger("anlage4_debug")


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


def get_user_tiles(user, bereich: str) -> list[Tile]:
    """Gibt alle Tiles zurueck, auf die ``user`` in ``bereich`` Zugriff hat."""
    return list(Tile.objects.filter(areas__slug=bereich, users=user))


FIELD_RENAME = {
    "technisch_verfuegbar": "technisch_vorhanden",
    "einsatz_telefonica": "einsatz_bei_telefonica",
}


def _deep_update(base: dict, extra: dict) -> dict:
    """Aktualisiert ``base`` rekursiv mit ``extra``."""
    for key, val in extra.items():
        if isinstance(val, dict):
            node = base.setdefault(key, {})
            _deep_update(node, val)
        else:
            base[key] = val
    return base


def _analysis1_to_initial(anlage: BVProjectFile) -> dict:
    """Wandelt ``analysis_json`` in das Initialformat für ``Anlage1ReviewForm``."""

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
            "status": q.get("status", ""),
            "hinweis": q.get("hinweis", ""),
            "vorschlag": q.get("vorschlag", ""),
        }

    return out


def _analysis_to_initial(anlage: BVProjectFile) -> dict:
    """Wandelt ``analysis_json`` in das Initialformat für ``Anlage2ReviewForm``."""
    data = anlage.analysis_json or {}
    debug_logger.debug("Eingabe analysis_json: %r", data)
    initial = {"functions": {}}
    if not isinstance(data, dict):
        debug_logger.debug("analysis_json ist kein Dict: %r", type(data))
        return initial

    name_map = {f.name: str(f.id) for f in Anlage2Function.objects.all()}
    sub_name_map = {
        (s.funktion.name, s.frage_text): str(s.id)
        for s in Anlage2SubQuestion.objects.select_related("funktion")
    }
    rev_map = {v: k for k, v in FIELD_RENAME.items()}

    items = data.get("functions")
    if isinstance(items, dict) and "value" in items:
        items = items["value"]
    if items is None:
        table_funcs = data.get("table_functions")
        if isinstance(table_funcs, dict):
            items = []
            for k, v in table_funcs.items():
                if isinstance(v, dict):
                    items.append({"name": k, **v})
                else:
                    logger.warning(
                        "Unerwarteter Typ in table_functions f\xc3\xbcr %s: %s",
                        k,
                        type(v),
                    )
        else:
            items = []
    for item in items:
        name = item.get("funktion") or item.get("name")
        if not name:
            continue

        # Unterfrage im Format "Funktion: Frage"?
        if ": " in name:
            func_name, sub_text = name.split(": ", 1)
            func_id = name_map.get(func_name)
            sub_id = sub_name_map.get((func_name, sub_text))
            if not func_id or not sub_id:
                continue

            s_entry: dict[str, object] = {}
            for field, _ in get_anlage2_fields():
                val = item.get(field)
                debug_logger.debug("Subfrage %s Feld %s: %r", sub_text, field, val)
                if isinstance(val, dict) and "value" in val:
                    val = val["value"]
                    debug_logger.debug("Subfeld %s normalisiert: %r", field, val)
                if val is None:
                    alt = rev_map.get(field)
                    if alt:
                        alt_val = item.get(alt)
                        debug_logger.debug("Nutze Alternativfeld %s: %r", alt, alt_val)
                        if isinstance(alt_val, dict) and "value" in alt_val:
                            alt_val = alt_val["value"]
                            debug_logger.debug(
                                "Alternativfeld %s normalisiert: %r", alt, alt_val
                            )
                        val = alt_val
                if isinstance(val, bool):
                    s_entry[field] = val
                    debug_logger.debug("Gesetzter Subwert f\u00fcr %s: %r", field, val)

            if s_entry:
                (
                    initial["functions"]
                    .setdefault(func_id, {})
                    .setdefault("subquestions", {})
                )[sub_id] = s_entry
            continue

        func_id = name_map.get(name)
        if not func_id:
            continue
        entry: dict[str, object] = {}
        for field, _ in get_anlage2_fields():
            val = item.get(field)
            debug_logger.debug("Funktion %s Feld %s: %r", name, field, val)
            if isinstance(val, dict) and "value" in val:
                val = val["value"]
                debug_logger.debug("Feld %s normalisiert: %r", field, val)
            if val is None:
                alt = rev_map.get(field)
                if alt:
                    alt_val = item.get(alt)
                    debug_logger.debug("Nutze Alternativfeld %s: %r", alt, alt_val)
                    if isinstance(alt_val, dict) and "value" in alt_val:
                        alt_val = alt_val["value"]
                        debug_logger.debug(
                            "Alternativfeld %s normalisiert: %r", alt, alt_val
                        )
                    val = alt_val
            if isinstance(val, bool):
                entry[field] = val
                debug_logger.debug("Gesetzter Wert f\u00fcr %s: %r", field, val)
        sub_map: dict[str, dict] = {}
        for sub in Anlage2SubQuestion.objects.filter(funktion_id=func_id).order_by(
            "id"
        ):
            match = next(
                (
                    s
                    for s in item.get("subquestions", [])
                    if s.get("frage_text") == sub.frage_text
                ),
                None,
            )
            if not match:
                continue
            s_entry: dict[str, object] = {}
            for field, _ in get_anlage2_fields():
                s_val = match.get(field)
                debug_logger.debug(
                    "Subfrage %s Feld %s: %r", sub.frage_text, field, s_val
                )
                if isinstance(s_val, dict) and "value" in s_val:
                    s_val = s_val["value"]
                    debug_logger.debug("Subfeld %s normalisiert: %r", field, s_val)
                if s_val is None:
                    alt = rev_map.get(field)
                    if alt:
                        alt_val = match.get(alt)
                        debug_logger.debug("Nutze Alternativfeld %s: %r", alt, alt_val)
                        if isinstance(alt_val, dict) and "value" in alt_val:
                            alt_val = alt_val["value"]
                            debug_logger.debug(
                                "Alternativfeld %s normalisiert: %r", alt, alt_val
                            )
                        s_val = alt_val
                if isinstance(s_val, bool):
                    s_entry[field] = s_val
                    debug_logger.debug(
                        "Gesetzter Subwert f\u00fcr %s: %r", field, s_val
                    )
            if s_entry:
                sub_map[str(sub.id)] = s_entry
        if sub_map:
            entry["subquestions"] = sub_map
        initial["functions"][func_id] = entry
    debug_logger.debug("Ergebnis initial: %r", initial)
    return initial


def _verification_to_initial(data: dict | None) -> dict:
    """Wandelt ``verification_json`` in das Initialformat."""
    initial = {"functions": {}}
    if not isinstance(data, dict):
        return initial

    name_map = {f.name: str(f.id) for f in Anlage2Function.objects.all()}
    sub_map = {}
    for sub in Anlage2SubQuestion.objects.select_related("funktion"):  # type: ignore[misc]
        sub_map[(sub.funktion.name, sub.frage_text)] = str(sub.id)

    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if ": " in key:
            func_name, sub_text = key.split(": ", 1)
            func_id = name_map.get(func_name)
            sub_id = sub_map.get((func_name, sub_text))
            if not func_id or not sub_id:
                continue
            entry = (
                initial["functions"]
                .setdefault(func_id, {})
                .setdefault(
                    "subquestions",
                    {},
                )
                .setdefault(sub_id, {})
            )
        else:
            func_id = name_map.get(key)
            if not func_id:
                continue
            entry = initial["functions"].setdefault(func_id, {})
        if "technisch_verfuegbar" in val:
            entry["technisch_vorhanden"] = val["technisch_verfuegbar"]
        if "ki_beteiligt" in val:
            entry["ki_beteiligt"] = val["ki_beteiligt"]
        if "ki_beteiligt_begruendung" in val:
            entry["ki_beteiligt_begruendung"] = val["ki_beteiligt_begruendung"]
    return initial


def _initial_to_lookup(data: dict) -> dict[str, dict]:
    """Wandelt das Initialformat in ein Lookup nach Namen um."""
    lookup: dict[str, dict] = {}
    fields = get_anlage2_fields()
    for func in Anlage2Function.objects.prefetch_related("anlage2subquestion_set").order_by("name"):
        fid = str(func.id)
        func_data = data.get("functions", {}).get(fid, {})
        lookup[func.name] = {field: func_data.get(field) for field, _ in fields}
        for sub in func.anlage2subquestion_set.all():
            sid = str(sub.id)
            sub_data = func_data.get("subquestions", {}).get(sid, {})
            lookup[f"{func.name}: {sub.frage_text}"] = {
                field: sub_data.get(field) for field, _ in fields
            }
    return lookup


def _resolve_value(
    manual_val: bool | None,
    ai_val: bool | None,
    doc_val: bool | None,
    field: str,
) -> tuple[bool | None, str]:
    """Ermittelt Wert und Quelle je nach Feld."""

    if field == "technisch_vorhanden":
        if manual_val is not None:
            return manual_val, "Manuell"
        if ai_val is not None:
            return ai_val, "KI-Prüfung"
        if doc_val is not None:
            return doc_val, "Dokumenten-Analyse"
        return None, "N/A"

    if field in {"einsatz_bei_telefonica", "zur_lv_kontrolle"}:
        if manual_val is not None:
            return manual_val, "Manuell"
        if doc_val is not None:
            return doc_val, "Dokumenten-Analyse"
        return None, "N/A"

    val = False
    src = "N/A"
    if doc_val is not None:
        val = doc_val
        src = "Dokumenten-Analyse"
    if ai_val is not None:
        val = ai_val
        src = "KI-Prüfung"
    if manual_val is not None:
        val = manual_val
        src = "Manuell"
    return val, src


def _get_display_data(
    lookup_key: str,
    analysis_data: dict[str, dict],
    verification_data: dict[str, dict],
    manual_results_map: dict[str, dict],
) -> dict[str, object]:
    """Ermittelt finale Werte und Quellen für eine Funktion oder Unterfrage."""

    fields = get_anlage2_fields()
    a_data = analysis_data.get(lookup_key, {})
    v_data = verification_data.get(lookup_key, {})
    m_data = manual_results_map.get(lookup_key, {})

    values: dict[str, bool] = {}
    sources: dict[str, str] = {}

    for field, _ in fields:
        man_val = m_data.get(field)
        ai_val = v_data.get(field)
        doc_val = a_data.get(field)
        val, src = _resolve_value(man_val, ai_val, doc_val, field)
        values[field] = val
        sources[field] = src

    return {
        "values": values,
        "sources": sources,
        "status": values.get("technisch_vorhanden"),
        "source": sources.get("technisch_vorhanden"),
    }


def _build_row_data(
    display_name: str,
    lookup_key: str,
    func_id: int,
    form_prefix: str,
    form,
    answers: dict[str, dict],
    ki_map: dict[tuple[str, str | None], str],
    beteilig_map: dict[tuple[str, str | None], tuple[bool | None, str]],
    analysis_lookup: dict[str, dict],
    verification_lookup: dict[str, dict],
    manual_lookup: dict[str, dict],
    result_map: dict[str, Anlage2FunctionResult],
    sub_id: int | None = None,
) -> dict:
    """Erzeugt die Darstellungsdaten für eine Funktion oder Unterfrage."""

    disp = _get_display_data(
        lookup_key, analysis_lookup, verification_lookup, manual_lookup
    )
    fields_def = get_anlage2_fields()
    widgets = []
    rev_origin = {}
    for field, _ in fields_def:
        bf = form[f"{form_prefix}{field}"]
        if field == "technisch_vorhanden" and sub_id is None:
            initial_value = disp["values"].get(field)
            state = (
                "true"
                if initial_value is True
                else "false" if initial_value is False else "unknown"
            )
            bf.field.widget.attrs.update(
                {
                    "data-tristate": "true",
                    "data-initial-state": state,
                    "style": "display: none;",
                }
            )
        if field == "technisch_vorhanden":
            man_val = manual_lookup.get(lookup_key, {}).get(field)
            ai_val = verification_lookup.get(lookup_key, {}).get(field)
            if man_val is not None:
                rev_origin[field] = "manual"
            elif ai_val is not None:
                rev_origin[field] = "ai"
            else:
                rev_origin[field] = "none"
        widgets.append({"widget": bf, "source": disp["sources"][field], "origin": rev_origin.get(field)})

    result_obj = result_map.get(lookup_key)
    is_negotiable = result_obj.is_negotiable if result_obj else False
    gap_widget = form[f"{form_prefix}gap_summary"]
    begr_md = ki_map.get((str(func_id), str(sub_id) if sub_id else None))
    bet_val, bet_reason = beteilig_map.get(
        (str(func_id), str(sub_id) if sub_id else None), (None, "")
    )
    has_gap = False
    # Manuelle Nachprüfung erforderlich, wenn Dokument und KI sich unterscheiden
    # und kein manueller Wert hinterlegt ist
    manual_review_required = False
    for field, _ in fields_def:
        doc_val = analysis_lookup.get(lookup_key, {}).get(field)
        ai_val = verification_lookup.get(lookup_key, {}).get(field)
        manual_val = manual_lookup.get(lookup_key, {}).get(field)
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
        "doc_result": answers.get(lookup_key, {}),
        "ai_result": verification_lookup.get(lookup_key, {}),
        "initial": disp["values"],
        "form_fields": widgets,
        "is_negotiable": is_negotiable,
        "gap_summary_widget": gap_widget,
        "sub": sub_id is not None,
        "func_id": func_id,
        "sub_id": sub_id,
        "verif_key": lookup_key,
        "source_text": disp["source"],
        "ki_begruendung": begr_md,
        "ki_begruendung_md": begr_md,
        "ki_begruendung_html": markdownify(begr_md) if begr_md else "",
        "ki_beteiligt": bet_val,
        "ki_beteiligt_begruendung": bet_reason,
        "has_preliminary_gap": has_gap,
        "requires_manual_review": manual_review_required,
    }


@login_required
def home(request):
    # Logic from codex/prüfen-und-weiterleiten-basierend-auf-tile-typ
    # Assuming get_user_tiles is defined elsewhere and correctly retrieves tiles
    tiles_personal = get_user_tiles(request.user, Tile.PERSONAL)
    tiles_work = get_user_tiles(request.user, Tile.WORK)

    if tiles_personal and not tiles_work:
        return redirect("personal")
    if tiles_work and not tiles_personal:
        return redirect("work")

    # Logic from main
    work_area = Area.objects.filter(slug="work").first()
    personal_area = Area.objects.filter(slug="personal").first()
    context = {
        "work_area": work_area,
        "personal_area": personal_area,
    }
    return render(request, "home.html", context)


@login_required
def work(request):
    is_admin = request.user.groups.filter(name="admin").exists()
    tiles = get_user_tiles(request.user, Tile.WORK)
    context = {
        "is_admin": is_admin,
        "tiles": tiles,
    }
    return render(request, "work.html", context)


@login_required
def personal(request):
    is_admin = request.user.groups.filter(name="admin").exists()
    tiles = get_user_tiles(request.user, Tile.PERSONAL)
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
    """Ermöglicht das manuelle Hochladen eines Transkript-Files."""
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

    # Pfad zu ffmpeg dem System-PATH hinzufügen, falls notwendig
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
        "is_admin": request.user.groups.filter(name="admin").exists(),
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

    context = {
        "recording": rec,
        "transcript_text": md_text,
    }
    return render(request, "talkdiary_detail.html", context)


@login_required
def transcribe_recording(request, pk):
    """Startet die Transkription für eine einzelne Aufnahme."""
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
    """Löscht eine Aufnahme des angemeldeten Benutzers."""
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

    context = {
        "recordings": filtered,
        "active_filter": active_filter or "",
    }
    return render(request, "admin_talkdiary.html", context)


@login_required
@admin_required
def admin_projects(request):
    """Verwaltet die Projektliste mit Such- und Filterfunktionen."""
    projects = BVProject.objects.all().order_by("-created_at")

    if request.method == "POST":
        # Fall 1: Der globale Knopf zum Löschen markierter Projekte wurde gedrückt
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

        # Fall 2: Ein individueller Löschknopf wurde gedrückt
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
        projects = projects.filter(bvsoftware__name__icontains=software_filter).distinct()

    context = {
        "projects": projects,
        "projekte": projects,
        "form": BVProjectForm(),
        "search_query": search_query,
        "status_filter": status_filter,
        "software_filter": software_filter,
        "status_choices": ProjectStatus.objects.all(),
    }
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "partials/_admin_project_rows.html", context)
    return render(request, "admin_projects.html", context)


@login_required
@admin_required
@require_http_methods(["POST"])
def admin_project_delete(request, pk):
    """Löscht ein einzelnes Projekt."""
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
    """Bietet Löschfunktionen für Projektdaten."""
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
                path = Path(settings.MEDIA_ROOT) / projekt.gutachten_file.name
                path.unlink(missing_ok=True)
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

    context = {"projekt": projekt, "files": projekt.anlagen.all()}
    return render(request, "admin_project_cleanup.html", context)


@login_required
@admin_required
@require_http_methods(["POST"])
def admin_project_export(request):
    """Exportiert ausgewählte Projekte als ZIP-Archiv."""
    ids = request.POST.getlist("selected_projects")
    if not ids:
        messages.error(request, "Keine Projekte zum Export ausgewählt.")
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
                    "manual_analysis_json": f.manual_analysis_json,
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
        messages.error(request, "Keine gültige Datei hochgeladen.")
        return redirect("admin_projects")

    uploaded = form.cleaned_data["json_file"]
    try:
        with zipfile.ZipFile(uploaded) as zf:
            raw = zf.read("projects.json").decode("utf-8")
            items = json.loads(raw)
            with transaction.atomic():
                for entry in items:
                    status = ProjectStatus.objects.filter(key=entry.get("status")).first()
                    proj = BVProject.objects.create(
                        title=entry.get("title", ""),
                        beschreibung=entry.get("beschreibung", ""),
                        status=status,
                        classification_json=entry.get("classification_json"),
                        gutachten_function_note=entry.get("gutachten_function_note", ""),
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
                        BVSoftware.objects.create(projekt=proj, name=name)
                    for fentry in entry.get("files", []):
                        upload_name = ""
                        if fentry.get("filename"):
                            content = zf.read(fentry["filename"])
                            upload_name = default_storage.save(
                                f"bv_files/{Path(fentry['filename']).name}",
                                ContentFile(content),
                            )
                        BVProjectFile.objects.create(
                            projekt=proj,
                            anlage_nr=fentry.get("anlage_nr"),
                            upload=upload_name,
                            manual_comment=fentry.get("manual_comment", ""),
                            manual_analysis_json=fentry.get("manual_analysis_json"),
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
    a4_cfg = Anlage4Config.objects.first() or Anlage4Config.objects.create()
    a4_parser = (
        Anlage4ParserConfig.objects.first() or Anlage4ParserConfig.objects.create()
    )
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
        if action == "save_a4_config":
            a4_cfg.prompt_template = request.POST.get("prompt_template", "")
            a4_cfg.save(update_fields=["prompt_template"])
            return redirect("admin_prompts")
        if action == "save_a4_parser_prompts":
            text = request.POST.get("prompt_text", "")
            a4_parser.prompt_plausibility = text
            a4_parser.save(update_fields=["prompt_plausibility"])
            return redirect("admin_prompts")
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
                prompt.role = LLMRole.objects.filter(pk=role_id).first() if role_id else None
                prompt.use_system_role = bool(request.POST.get("use_system_role"))
                prompt.save(update_fields=["text", "role", "use_system_role"])
        return redirect("admin_prompts")

    labels = [
        ("general", "Allgemeine Projektprompts"),
        ("anlage1", "Anlage 1 Prompts"),
        ("anlage2", "Anlage 2 Prompts"),
        ("anlage3", "Anlage 3 Prompts"),
        ("anlage4", "Anlage 4 Prompts"),
    ]

    grouped = [(key, label, groups[key]) for key, label in labels]

    context = {
        "grouped": grouped,
        "roles": roles,
        "a4_config": a4_cfg,
        "a4_parser": a4_parser,
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
            messages.error(request, "Ungültige JSON-Datei")
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
                },
            )
        messages.success(request, "Prompts importiert")
        return redirect("admin_prompts")
    return render(request, "admin_prompt_import.html", {"form": form})


@login_required
@admin_required
def admin_models(request):
    """Ermöglicht die Auswahl der Standard-LLM-Modelle."""
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
    context = {"config": cfg, "models": LLMConfig.get_available()}
    return render(request, "admin_models.html", context)


@login_required
@admin_required
def admin_anlage1(request):
    """Konfiguriert Fragen für Anlage 1."""
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
    context = {"questions": questions}
    return render(request, "admin_anlage1.html", context)


@login_required
@admin_required
def admin_anlage1_export(request):
    """Exportiert alle Anlage-1-Fragen als JSON-Datei."""
    questions = (
        Anlage1Question.objects.all()
        .prefetch_related("variants")
        .order_by("num")
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
            messages.error(request, "Ungültige JSON-Datei")
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
    return render(request, "admin_anlage1_import.html", {"form": form})


@login_required
@admin_required
def admin_project_statuses(request):
    """Zeigt alle vorhandenen Projektstatus an."""
    statuses = list(ProjectStatus.objects.all().order_by("ordering", "name"))
    context = {"statuses": statuses}
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
            messages.error(request, "Ungültige JSON-Datei")
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
    return render(request, "admin_project_status_import.html", {"form": form})


@login_required
@admin_required
def admin_project_status_form(request, pk=None):
    """Erstellt oder bearbeitet einen Projektstatus."""
    status = get_object_or_404(ProjectStatus, pk=pk) if pk else None
    form = ProjectStatusForm(request.POST or None, instance=status)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("admin_project_statuses")
    context = {"form": form, "status": status}
    return render(request, "admin_project_status_form.html", context)


@login_required
@admin_required
@require_POST
def admin_project_status_delete(request, pk):
    """Löscht einen Projektstatus."""
    status = get_object_or_404(ProjectStatus, pk=pk)
    status.delete()
    return redirect("admin_project_statuses")


@login_required
@admin_required
def admin_llm_roles(request):
    """Liste aller vorhandenen LLM-Rollen."""
    roles = list(LLMRole.objects.all().order_by("name"))
    context = {"roles": roles}
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
    context = {"form": form, "role": role}
    return render(request, "admin_llm_role_form.html", context)


@login_required
@admin_required
@require_POST
def admin_llm_role_delete(request, pk):
    """Löscht eine LLM-Rolle."""
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
            messages.error(request, "Ungültige JSON-Datei")
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
    context = {"form": form}
    return render(request, "admin_llm_role_import.html", context)


@login_required
@admin_required
def admin_user_list(request):
    """Listet alle Benutzer mit zugehörigen Gruppen und Tiles auf."""
    users = list(User.objects.all().prefetch_related("groups", "tiles", "areas"))
    context = {"users": users}
    return render(request, "admin_user_list.html", context)


@login_required
@admin_required
def admin_edit_user_permissions(request, user_id):
    """Bearbeitet Gruppen- und Tile-Zuordnungen für einen Benutzer."""
    user_obj = get_object_or_404(User, pk=user_id)
    form = UserPermissionsForm(request.POST or None, user=user_obj)
    if request.method == "POST" and form.is_valid():
        user_obj.groups.set(form.cleaned_data.get("groups"))
        user_obj.tiles.set(form.cleaned_data.get("tiles"))
        user_obj.areas.set(form.cleaned_data.get("areas"))
        messages.success(request, "Berechtigungen gespeichert")
        return redirect("admin_user_list")
    context = {"form": form, "user_obj": user_obj}
    return render(request, "admin_user_permissions_form.html", context)


@login_required
@admin_required
def admin_export_users_permissions(request):
    """Exportiert Benutzer, Gruppen und Tile-Zuordnungen als JSON."""
    users = (
        User.objects.all()
        .prefetch_related("groups", "tiles", "areas")
        .order_by("username")
    )
    data = []
    for user in users:
        data.append(
            {
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "groups": [g.name for g in user.groups.all()],
                "areas": [a.slug for a in user.areas.all()],
                "tiles": [t.url_name for t in user.tiles.all()],
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
            messages.error(request, "Ungültige JSON-Datei")
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
            area_qs = Area.objects.filter(slug__in=item.get("areas", []))
            user_obj.groups.set(group_qs)
            user_obj.tiles.set(tile_qs)
            user_obj.areas.set(area_qs)
        messages.success(request, "Benutzerdaten importiert")
        return redirect("admin_user_list")
    return render(request, "admin_user_import.html", {"form": form})


@login_required
@admin_required
def admin_anlage2_config_export(request):
    """Exportiert die komplette Anlage-2-Konfiguration als JSON."""
    cfg = Anlage2Config.get_instance()
    alias_headings = cfg.headers.all().values("field_name", "text")

    cfg_data = {
        "enforce_subquestion_override": cfg.enforce_subquestion_override,
        "parser_mode": cfg.parser_mode,
        "parser_order": cfg.parser_order,
    }
    for key, _ in PHRASE_TYPE_CHOICES:
        cfg_data[f"text_{key}"] = getattr(cfg, f"text_{key}")

    data = {
        "config": cfg_data,
        "alias_headings": list(alias_headings),
    }

    content = json.dumps(data, ensure_ascii=False, indent=2)
    resp = HttpResponse(content, content_type="application/json")
    resp["Content-Disposition"] = "attachment; filename=anlage2_config.json"
    return resp


@login_required
@admin_required
def admin_anlage2_config_import(request):
    """Importiert Spaltenüberschriften aus JSON."""
    form = Anlage2ConfigImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(raw)
        except Exception:  # noqa: BLE001
            messages.error(request, "Ungültige JSON-Datei")
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

        messages.success(request, "Konfiguration importiert")
        return redirect("anlage2_config")
    return render(request, "admin_anlage2_config_import.html", {"form": form})


@login_required
@admin_required
def anlage2_config(request):
    """Konfiguriert Überschriften und globale Phrasen für Anlage 2."""
    cfg = Anlage2Config.get_instance()
    aliases = list(cfg.headers.all())
    rules_qs = AntwortErkennungsRegel.objects.all().order_by("prioritaet")
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
    active_tab = request.POST.get("active_tab") or request.GET.get("tab") or "table"

    if request.method == "POST":
        action = request.POST.get("action") or "save_general"
        admin_a2_logger.debug("Aktion %s ausgelöst", action)

        if action == "save_table":
            admin_a2_logger.debug("Speichere Tabellen-Parser Konfiguration")
            for h in aliases:
                if request.POST.get(f"delete{h.id}"):
                    admin_a2_logger.debug("Lösche Überschrift %s -> %s", h.field_name, h.text)
                    h.delete()
            new_field = request.POST.get("new_field")
            new_text = request.POST.get("new_text")
            if new_field and new_text:
                Anlage2ColumnHeading.objects.create(
                    config=cfg, field_name=new_field, text=new_text
                )
                admin_a2_logger.debug("Neue Überschrift %s -> %s", new_field, new_text)
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
                messages.error(request, "Ungültige Eingaben")

            if request.headers.get("HX-Request"):
                formset = RuleFormSet(queryset=rules_qs, prefix="rules")
                context = {"rule_formset": formset, "rule_choices": FormatBParserRule.FIELD_CHOICES}
                return render(request, "partials/_response_rules_table.html", context)
            return redirect(f"{reverse('anlage2_config')}?tab=rules")

        if action == "save_rules_fb":
            admin_a2_logger.debug("Speichere Antwortregeln (Fallback)")
            formset = RuleFormSetFB(request.POST, queryset=rules_qs, prefix="rules_fb")
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
                return redirect(f"{reverse('anlage2_config')}?tab=rules2")
            messages.error(request, "Bitte korrigieren Sie die markierten Felder.")
            rule_formset_fb = formset
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


    cfg_form = cfg_form if 'cfg_form' in locals() else Anlage2ConfigForm(instance=cfg)
    rule_formset = RuleFormSet(queryset=rules_qs, prefix="rules")
    rule_formset_fb = (
        rule_formset_fb
        if "rule_formset_fb" in locals()
        else RuleFormSetFB(queryset=rules_qs, prefix="rules_fb")
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
        "choices": Anlage2ColumnHeading.FIELD_CHOICES,
        "rule_choices": FormatBParserRule.FIELD_CHOICES,
        "parser_choices": get_parser_choices(),
        "active_tab": active_tab,
        "a4_parser_form": a4_parser_form,
    }
    return render(request, "admin_anlage2_config.html", context)


@login_required
@admin_required
@require_http_methods(["GET"])
def anlage2_rule_add(request):
    """Liefert eine leere Formularzeile für eine Antwortregel."""
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
    formset = RuleFormSet(queryset=AntwortErkennungsRegel.objects.none(), prefix="rules")
    form = formset.empty_form
    form.prefix = f"rules-{index}"
    context = {"form": form, "rule_choices": FormatBParserRule.FIELD_CHOICES}
    return render(request, "partials/_response_rule_row.html", context)


@login_required
@admin_required
@require_http_methods(["DELETE"])
def anlage2_rule_delete(request, pk: int):
    """Löscht eine Antwortregel."""
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
        tile_perms = Permission.objects.filter(tile__isnull=False)
        selected_group.permissions.remove(*tile_perms)
        perms = Permission.objects.filter(tile__in=selected_tiles)
        selected_group.permissions.add(*perms)
        messages.success(request, "Berechtigungen gespeichert")
        return redirect(f"{reverse('admin_role_editor')}?group={selected_group.id}")

    if selected_group:
        group_perms = set(selected_group.permissions.values_list("id", flat=True))
        for area in Area.objects.all():
            tile_items = []
            for tile in Tile.objects.filter(areas=area).select_related("permission"):
                tile_items.append(
                    {
                        "tile": tile,
                        "checked": tile.permission_id in group_perms,
                    }
                )
            tiles_by_area[area] = tile_items

    context = {
        "groups": groups,
        "selected_group": selected_group,
        "tiles_by_area": tiles_by_area,
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
        funktion = form.save()
        return redirect("anlage2_function_edit", funktion.pk)

    subquestions = list(funktion.anlage2subquestion_set.all()) if funktion else []
    context = {
        "form": form,
        "funktion": funktion,
        "subquestions": subquestions,
    }
    return render(request, "anlage2/function_form.html", context)


@login_required
@admin_required
def anlage2_function_delete(request, pk):
    """Löscht eine Anlage-2-Funktion."""
    if request.method != "POST":
        return HttpResponseBadRequest()
    funktion = get_object_or_404(Anlage2Function, pk=pk)
    funktion.delete()
    return redirect("anlage2_function_list")


@login_required
@admin_required
def anlage2_function_import(request):
    """Importiert den Funktionskatalog aus einer JSON-Datei."""
    form = Anlage2FunctionImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data["json_file"].read().decode("utf-8")
        try:
            items = json.loads(data)
        except Exception:  # noqa: BLE001
            messages.error(request, "Ungültige JSON-Datei")
            return redirect("anlage2_function_import")
        if form.cleaned_data["clear_first"]:
            Anlage2SubQuestion.objects.all().delete()
            Anlage2Function.objects.all().delete()
        for entry in items:
            name = entry.get("name") or entry.get("funktion") or ""
            func, _ = Anlage2Function.objects.get_or_create(name=name)
            func.save()
            subs = entry.get("subquestions") or entry.get("unterfragen") or []
            for sub in subs:
                if isinstance(sub, dict):
                    text = sub.get("frage_text") or sub.get("frage") or ""
                    vals = sub
                else:
                    text = str(sub)
                    vals = {}
                Anlage2SubQuestion.objects.create(
                    funktion=func,
                    frage_text=text,
                )
        messages.success(request, "Funktionskatalog importiert")
        return redirect("anlage2_function_list")
    return render(request, "anlage2/function_import.html", {"form": form})


@login_required
@admin_required
def anlage2_function_export(request):
    """Exportiert den aktuellen Funktionskatalog als JSON."""
    functions = []
    for f in Anlage2Function.objects.all().order_by("name"):
        item = {
            "name": f.name,
            "subquestions": [],
        }
        for q in f.anlage2subquestion_set.all().order_by("id"):
            item["subquestions"].append({"frage_text": q.frage_text})
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
        subquestion = form.save()
        return redirect("anlage2_function_edit", funktion.pk)

    context = {
        "form": form,
        "funktion": funktion,
        "subquestion": subquestion if pk else None,
    }
    return render(request, "anlage2/subquestion_form.html", context)


@login_required
@admin_required
def anlage2_subquestion_delete(request, pk):
    """Löscht eine Unterfrage."""
    if request.method != "POST":
        return HttpResponseBadRequest()
    sub = get_object_or_404(Anlage2SubQuestion, pk=pk)
    func_pk = sub.funktion_id
    sub.delete()
    return redirect("anlage2_function_edit", func_pk)


@login_required
@tile_required("projektverwaltung")
def projekt_list(request):
    projekte = BVProject.objects.all().order_by("-created_at")

    search_query = request.GET.get("q", "")
    if search_query:
        projekte = projekte.filter(title__icontains=search_query)

    software_filter = request.GET.get("software", "")
    if software_filter:
        projekte = projekte.filter(bvsoftware__name__icontains=software_filter).distinct()

    status_filter = request.GET.get("status", "")
    if status_filter:
        projekte = projekte.filter(status__key=status_filter)

    context = {
        "projekte": projekte,
        "is_admin": request.user.groups.filter(name="admin").exists(),
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
    if request.method == "POST" and "project_prompt" in request.POST:
        new_prompt = request.POST.get("project_prompt", "")
        changed = projekt.project_prompt != new_prompt
        projekt.project_prompt = new_prompt
        projekt.save(update_fields=["project_prompt"])

        async_task("core.llm_tasks.check_anlage2_functions", projekt.pk)

        messages.success(request, "Projekt-Prompt gespeichert")
        return redirect("projekt_detail", pk=projekt.pk)
    anh = projekt.anlagen.all()
    reviewed = anh.filter(manual_reviewed=True).count()
    is_admin = request.user.groups.filter(name="admin").exists()
    software_list = projekt.software_list
    knowledge_map = {k.software_name: k for k in projekt.softwareknowledge.all()}
    knowledge_rows = []
    checked = 0
    for name in software_list:
        entry = knowledge_map.get(name)
        if entry and entry.last_checked:
            checked += 1
        knowledge_rows.append({"name": name, "entry": entry})
    context = {
        "projekt": projekt,
        "status_choices": ProjectStatus.objects.all(),
        "history": projekt.status_history.all(),
        "num_attachments": anh.count(),
        "num_reviewed": reviewed,
        "is_admin": is_admin,

        "knowledge_rows": knowledge_rows,
        "knowledge_checked": checked,
        "total_software": len(software_list),
        "software_list": software_list,

    }
    return render(request, "projekt_detail.html", context)


@login_required
def anlage3_review(request, pk):
    """Zeigt alle Dateien der Anlage 3 mit Review-Option."""
    logger.info("anlage3_review gestartet für Projekt %s", pk)
    projekt = get_object_or_404(BVProject, pk=pk)
    anlagen = projekt.anlagen.filter(anlage_nr=3)
    context = {"projekt": projekt, "anlagen": anlagen}
    logger.info("anlage3_review beendet für Projekt %s", pk)
    return render(request, "anlage3_review.html", context)


@login_required
def anlage4_review(request, pk):
    """Zeigt die Auswertungen aus Anlage 4 und ermöglicht die manuelle Bewertung."""
    project_file = get_object_or_404(BVProjectFile, pk=pk)
    if project_file.anlage_nr != 4:
        raise Http404

    anlage4_logger.info("Zugriff auf Anlage4 Review f\u00fcr Datei %s", pk)

    items = []
    if project_file.analysis_json:
        items = project_file.analysis_json.get("items") or []

    if request.method == "POST":
        form = Anlage4ReviewForm(request.POST, items=items)
        if form.is_valid():
            project_file.manual_analysis_json = form.get_json()
            project_file.save(update_fields=["manual_analysis_json"])
            anlage4_logger.info("Anlage4 Review gespeichert: %s Eintr\u00e4ge", len(items))
            return redirect("projekt_detail", pk=project_file.projekt.pk)
    else:
        form = Anlage4ReviewForm(initial=project_file.manual_analysis_json, items=items)

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
    }
    anlage4_logger.info("Anlage4 Review abgeschlossen für Datei %s", pk)
    return render(request, "projekt_file_anlage4_review.html", context)


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
    if request.method == "POST":
        form = BVProjectForm(request.POST)
        if form.is_valid():
            software_typen_list = request.POST.getlist("software_typen")
            projekt = form.save(software_list=software_typen_list)
            return redirect("projekt_detail", pk=projekt.pk)
    else:
        form = BVProjectForm()
    return render(request, "projekt_form.html", {"form": form})


@login_required
def projekt_edit(request, pk):
    projekt = get_object_or_404(BVProject, pk=pk)
    if request.method == "POST":
        form = BVProjectForm(request.POST, instance=projekt)
        if form.is_valid():
            software_typen_list = request.POST.getlist("software_typen")
            projekt = form.save(software_list=software_typen_list)
            return redirect("projekt_detail", pk=projekt.pk)
    else:
        form = BVProjectForm(instance=projekt)
    context = {
        "form": form,
        "projekt": projekt,
        "categories": LLMConfig.get_categories(),
        "category": "default",
    }
    return render(request, "projekt_form.html", context)


@login_required
def projekt_file_upload(request, pk):
    projekt = get_object_or_404(BVProject, pk=pk)
    if request.method == "POST":
        form = BVProjectFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["upload"]
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
                uploaded.read()  # Bytes einlesen, aber nicht dekodieren
                uploaded.seek(0)
            else:
                try:
                    content = uploaded.read().decode("utf-8")
                except UnicodeDecodeError as exc:
                    logger.error(
                        "Datei konnte nicht als UTF-8 dekodiert werden: %s", exc
                    )
                    return HttpResponseBadRequest("Ungültiges Dateiformat")
            obj = form.save(commit=False)
            obj.projekt = projekt
            obj.text_content = content
            obj.save()
            return redirect("projekt_detail", pk=projekt.pk)
    else:
        form = BVProjectFileForm()
    return render(request, "projekt_file_form.html", {"form": form, "projekt": projekt})


@login_required
@require_http_methods(["POST"])
def projekt_file_check(request, pk, nr):
    """Prüft eine einzelne Anlage per LLM."""
    try:
        nr_int = int(nr)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid"}, status=400)

    use_llm = request.POST.get("llm") or request.GET.get("llm")
    def parse_only(pid: int, model_name: str | None = None):
        pf = BVProjectFile.objects.filter(projekt_id=pid, anlage_nr=2).first()
        if pf:
            run_anlage2_analysis(pf)
    funcs = {
        1: check_anlage1,
        2: check_anlage2 if use_llm else parse_only,
        3: check_anlage3_vision if use_llm else analyse_anlage3,
        4: analyse_anlage4,
    }
    func = funcs.get(nr_int)
    if not func:
        return JsonResponse({"error": "invalid"}, status=404)
    category = request.POST.get("model_category")
    model = LLMConfig.get_default(category) if category else None
    try:
        func(pk, model_name=model)
        anlage = BVProjectFile.objects.filter(
            projekt_id=pk, anlage_nr=nr_int
        ).first()
        analysis = anlage.analysis_json if anlage else None
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
    """Prüft eine Anlage anhand der Datenbank-ID."""
    try:
        anlage = BVProjectFile.objects.get(pk=pk)
    except BVProjectFile.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)

    use_llm = request.POST.get("llm") or request.GET.get("llm")
    def parse_only(_pid: int, model_name: str | None = None):
        run_anlage2_analysis(anlage)
    funcs = {
        1: check_anlage1,
        2: check_anlage2 if use_llm else parse_only,
        3: check_anlage3_vision if use_llm else analyse_anlage3,
        4: analyse_anlage4,
    }
    func = funcs.get(anlage.anlage_nr)
    if not func:
        return JsonResponse({"error": "invalid"}, status=404)
    category = request.POST.get("model_category")
    model = LLMConfig.get_default(category) if category else None
    try:
        func(anlage.projekt_id, model_name=model)
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

    use_llm = request.POST.get("llm") or request.GET.get("llm")
    def parse_only(_pid: int, model_name: str | None = None):
        run_anlage2_analysis(anlage)
    funcs = {
        1: check_anlage1,
        2: check_anlage2 if use_llm else parse_only,
        3: check_anlage3_vision if use_llm else analyse_anlage3,
        4: analyse_anlage4,
    }
    func = funcs.get(anlage.anlage_nr)
    if not func:
        raise Http404

    category = request.GET.get("model_category")
    model = LLMConfig.get_default(category) if category else None
    try:
        func(anlage.projekt_id, model_name=model)
    except RuntimeError:
        messages.error(request, "Missing LLM credentials from environment.")
    except Exception:
        logger.exception("LLM Fehler")
        messages.error(request, "Fehler bei der Anlagenpr\xfcfung")

    if anlage.anlage_nr == 3:
        return redirect("anlage3_review", pk=anlage.projekt_id)

    return redirect("projekt_file_edit_json", pk=pk)


@login_required
def projekt_file_parse_anlage2(request, pk):
    """Parst Anlage 2 ohne LLM-Aufrufe."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)
    if anlage.anlage_nr != 2:
        raise Http404
    run_anlage2_analysis(anlage)
    return redirect("projekt_file_edit_json", pk=pk)


@login_required
def projekt_file_analyse_anlage4(request, pk):
    """Analysiert Anlage 4 und leitet zum Review."""
    anlage = get_object_or_404(BVProjectFile, pk=pk)
    if anlage.anlage_nr != 4:
        raise Http404
    analyse_anlage4_async(anlage.projekt_id)
    return redirect("anlage4_review", pk=pk)


@login_required
def projekt_file_edit_json(request, pk):
    """Ermöglicht das Bearbeiten der JSON-Daten einer Anlage."""
    logger.info("projekt_file_edit_json gestartet für Anlage %s", pk)
    try:
        anlage = BVProjectFile.objects.get(pk=pk)
    except BVProjectFile.DoesNotExist:
        raise Http404

    if anlage.anlage_nr == 2 and not anlage.analysis_json:
        run_anlage2_analysis(anlage)
        anlage.refresh_from_db()

    if anlage.anlage_nr == 1:
        if request.method == "POST":
            form = Anlage1ReviewForm(request.POST)
            if form.is_valid():
                data = form.get_json()
                anlage.question_review = data
                anlage.save(update_fields=["question_review"])
                logger.info(
                    "Anlage1 Review gespeichert: %s Einträge",
                    len(data),
                )
                return redirect("projekt_detail", pk=anlage.projekt.pk)
        else:
            init = anlage.question_review
            if not init:
                init = _analysis1_to_initial(anlage)
            form = Anlage1ReviewForm(initial=init)
        template = "projekt_file_anlage1_review.html"
        answers: dict[str, str] = {}
        numbers = get_anlage1_numbers()
        q_data = (
            anlage.analysis_json.get("questions", {}) if anlage.analysis_json else {}
        )
        for i in numbers:
            answers[str(i)] = q_data.get(str(i), {}).get("answer", "")

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

        qa = [
            (
                i,
                questions.get(i, ""),
                answers.get(str(i), ""),
                form[f"q{i}_status"],
                form[f"q{i}_hinweis"],
                form[f"q{i}_vorschlag"],
                form[f"q{i}_ok"],
                form[f"q{i}_note"],
            )
            for i in numbers
        ]
    elif anlage.anlage_nr == 2:
        analysis_init = _analysis_to_initial(anlage)
        if request.method == "POST":
            form = Anlage2ReviewForm(request.POST)
            if form.is_valid():
                cfg_rule = Anlage2Config.get_instance()
                functions_to_override: set[int] = set()
                if cfg_rule.enforce_subquestion_override:
                    for func in Anlage2Function.objects.order_by("name"):
                        for sub in func.anlage2subquestion_set.all().order_by("id"):
                            field_name = f"sub{sub.id}_technisch_vorhanden"
                            if form.cleaned_data.get(field_name):
                                functions_to_override.add(func.id)

                data = form.get_json()
                anlage.manual_analysis_json = data
                anlage.save(update_fields=["manual_analysis_json"])
                logger.info(
                    "Anlage2 Review gespeichert: %s Funktionen",
                    len(data.get("functions", {})),
                )

                if cfg_rule.enforce_subquestion_override:
                    for fid in functions_to_override:
                        Anlage2FunctionResult.objects.update_or_create(
                            projekt=anlage.projekt,
                            funktion_id=fid,
                            defaults={
                                "technisch_verfuegbar": True,
                                "source": "manual",
                            },
                        )

                return redirect("projekt_detail", pk=anlage.projekt.pk)
        else:
            verif_init = _verification_to_initial(anlage.verification_json)
            verif_raw = anlage.verification_json or {}

            name_map = {f.name: str(f.id) for f in Anlage2Function.objects.all()}
            sub_map = {
                (s.funktion.name, s.frage_text): str(s.id)
                for s in Anlage2SubQuestion.objects.select_related("funktion")
            }
            ki_map: dict[tuple[str, str | None], str] = {}
            beteilig_map: dict[tuple[str, str | None], tuple[bool | None, str]] = {}
            if isinstance(verif_raw, dict):
                for key, val in verif_raw.items():
                    if not isinstance(val, dict):
                        continue
                    begr = val.get("ki_begruendung")
                    beteiligt = val.get("ki_beteiligt")
                    beteiligt_begr = val.get("ki_beteiligt_begruendung", "")
                    if ": " in key:
                        func_name, sub_text = key.split(": ", 1)
                        fid = name_map.get(func_name)
                        sid = sub_map.get((func_name, sub_text))
                        if fid:
                            if begr:
                                ki_map[(fid, sid)] = begr
                            beteilig_map[(fid, sid)] = (beteiligt, beteiligt_begr)
                    else:
                        fid = name_map.get(key)
                        if fid:
                            if begr:
                                ki_map[(fid, None)] = begr
                            beteilig_map[(fid, None)] = (beteiligt, beteiligt_begr)

            manual_results_map = {
                r.get_lookup_key(): {
                    "technisch_vorhanden": r.technisch_verfuegbar,
                    "ki_beteiligung": r.ki_beteiligung,
                }
                for r in Anlage2FunctionResult.objects.filter(
                    projekt=anlage.projekt,
                    source="manual",
                )
            }

            result_map = {
                r.get_lookup_key(): r
                for r in Anlage2FunctionResult.objects.filter(projekt=anlage.projekt)
            }

            manual_init = (
                anlage.manual_analysis_json if isinstance(anlage.manual_analysis_json, dict) else {}
            )

            fields_def = get_anlage2_fields()

            analysis_lookup = _initial_to_lookup(analysis_init)
            verification_lookup = _initial_to_lookup(verif_init)
            manual_lookup = _initial_to_lookup(manual_init)

            for key, res in manual_results_map.items():
                manual_lookup.setdefault(key, {}).update(res)

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
        if anlage.analysis_json:
            funcs = anlage.analysis_json.get("functions")
            if isinstance(funcs, dict) and "value" in funcs:
                funcs = funcs["value"]
            if funcs is None:
                table = anlage.analysis_json.get("table_functions")
                if isinstance(table, dict):
                    funcs = []
                    for k, v in table.items():
                        if isinstance(v, dict):
                            funcs.append({"name": k, **v})
                        else:
                            logger.warning(
                                "Unerwarteter Typ in table_functions f\xc3\xbcr %s: %s",
                                k,
                                type(v),
                            )
                else:
                    funcs = []
        for item in funcs or []:
            name = item.get("funktion") or item.get("name")
            if name:
                for old, new in FIELD_RENAME.items():
                    if old in item and new not in item:
                        item[new] = item[old]
                answers[name] = item
                for sub in item.get("subquestions", []):
                    s_text = sub.get("frage_text")
                    if not s_text:
                        continue
                    for old, new in FIELD_RENAME.items():
                        if old in sub and new not in sub:
                            sub[new] = sub[old]
                    answers[f"{name}: {s_text}"] = sub
        rows = []
        fields_def = get_anlage2_fields()

        for func in Anlage2Function.objects.order_by("name"):
            lookup_key = func.name
            func_status = analysis_lookup.get(lookup_key, {}).get("technisch_vorhanden")
            if func.name == "Anwesenheitsüberwachung":
                debug_logger.info(
                    "--- Starte detaillierte Prüfung für Funktion: '%s' ---",
                    func.name,
                )
                if func_status is True:
                    debug_logger.info("-> Status: Als 'Technisch verfügbar' erkannt.")
                elif func_status is False:
                    debug_logger.info(
                        "-> Status: Als 'Technisch NICHT verfügbar' erkannt."
                    )
                note = None
                tv_entry = answers.get(lookup_key, {}).get("technisch_vorhanden")
                if isinstance(tv_entry, dict):
                    note = tv_entry.get("note") or tv_entry.get("text")
                if note:
                    debug_logger.info("-> Entscheidungsgrundlage im Text: '%s'", note)
            else:
                debug_logger.info(
                    "--- Starte Prüfung für Funktion: '%s' ---", func.name
                )
                if answers.get(lookup_key):
                    debug_logger.info("-> Ergebnis: Im Dokument gefunden.")
                else:
                    debug_logger.info("-> Ergebnis: Nicht im Dokument gefunden.")
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
                    analysis_lookup,
                    verification_lookup,
                    manual_lookup,
                    result_map,
                )
            )
            for sub in func.anlage2subquestion_set.all().order_by("id"):
                lookup_key = f"{func.name}: {sub.frage_text}"
                if not (func.name == "Anwesenheitsüberwachung" and func_status is not True):
                    debug_logger.info(
                        "--- Starte Prüfung für Unterfrage: '%s' ---", sub.frage_text
                    )
                    if answers.get(lookup_key):
                        debug_logger.info("-> Ergebnis: Im Dokument gefunden.")
                    else:
                        debug_logger.info(
                            "-> Ergebnis: Nicht im Dokument gefunden."
                        )
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
                        analysis_lookup,
                        verification_lookup,
                        manual_lookup,
                        result_map,
                        sub_id=sub.id,
                    )
                )
    elif anlage.anlage_nr == 4:
        items = []
        if anlage.analysis_json:
            items = anlage.analysis_json.get("items")
        if isinstance(items, dict):
            items = items.get("value", [])
        if not items:
            items = []
        if request.method == "POST":
            if "analysis_json" in request.POST or "manual_analysis_json" in request.POST:
                json_form = BVProjectFileJSONForm(request.POST, instance=anlage)
                if json_form.is_valid():
                    json_form.save()
                    return redirect("projekt_detail", pk=anlage.projekt.pk)
                form = json_form
            else:
                form = Anlage4ReviewForm(request.POST, items=items)
                if form.is_valid():
                    anlage.manual_analysis_json = form.get_json()
                    anlage.save(update_fields=["manual_analysis_json"])
                    return redirect("projekt_detail", pk=anlage.projekt.pk)
        else:
            form = Anlage4ReviewForm(initial=anlage.manual_analysis_json, items=items)
        template = "projekt_file_anlage4_review.html"
        rows = [
            (text, form[f"item{idx}_ok"], form[f"item{idx}_note"]) for idx, text in enumerate(items)
        ]
    else:
        if request.method == "POST":
            form = BVProjectFileJSONForm(request.POST, instance=anlage)
            if form.is_valid():
                form.save()
                return redirect("projekt_detail", pk=anlage.projekt.pk)
        else:
            form = BVProjectFileJSONForm(instance=anlage)
        template = "projekt_file_json_form.html"

    context = {"form": form, "anlage": anlage}
    if anlage.anlage_nr == 1:
        context["qa"] = qa
    elif anlage.anlage_nr == 2:
        context.update(
            {
                "rows": rows,
                "fields": [f[0] for f in fields_def],
                "labels": [f[1] for f in fields_def],
                "field_pairs": fields_def,
                "no_ai_fields": ["einsatz_bei_telefonica", "zur_lv_kontrolle"],
            }
        )
    elif anlage.anlage_nr == 4:
        context["rows"] = rows
    logger.info("projekt_file_edit_json beendet für Anlage %s", pk)
    return render(request, template, context)


@login_required
@require_http_methods(["POST"])
def anlage1_generate_email(request, pk):
    """Erstellt einen E-Mail-Text aus den Vorschlägen."""
    try:
        anlage = BVProjectFile.objects.get(pk=pk)
    except BVProjectFile.DoesNotExist:
        return JsonResponse({"error": "not found"}, status=404)
    if anlage.anlage_nr != 1:
        return JsonResponse({"error": "invalid"}, status=400)

    review = anlage.question_review or {}
    suggestions: list[str] = []
    for i in get_anlage1_numbers():
        text = review.get(str(i), {}).get("vorschlag")
        if text:
            suggestions.append(text)

    prefix = get_prompt(
        "anlage1_email",
        "Formuliere eine freundliche E-Mail an den Fachbereich. Bitte fasse die folgenden Vorschläge zusammen:\n\n",
    )
    prompt_text = prefix + "\n".join(f"- {s}" for s in suggestions)
    base_obj = Prompt.objects.filter(name="anlage1_email").first()
    prompt_obj = Prompt(name="tmp", text=prompt_text, role=base_obj.role if base_obj else None)
    try:
        text = query_llm(
            prompt_obj,
            {},
            model_type="default",
            project_prompt=anlage.projekt.project_prompt,
        )
    except RuntimeError:
        return JsonResponse({"error": "llm"}, status=500)
    except Exception:
        logger.exception("LLM Fehler")
        return JsonResponse({"error": "llm"}, status=502)

    return JsonResponse({"text": text})


def _validate_llm_output(text: str) -> tuple[bool, str]:
    """Prüfe, ob die LLM-Antwort technisch brauchbar ist."""
    if not text:
        return False, "Antwort leer"
    if len(text.split()) < 5:
        return False, "Antwort zu kurz"
    return True, ""


def _run_llm_check(name: str, additional: str | None = None, project_prompt: str | None = None) -> tuple[str, bool]:
    """Führt die LLM-Abfrage für eine einzelne Software durch."""
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
    base_obj = Prompt.objects.filter(name="initial_llm_check").first()
    prompt_obj = Prompt(name="tmp", text=prompt_text, role=base_obj.role if base_obj else None)

    logger.debug("Starte LLM-Check für %s", name)
    reply = query_llm(prompt_obj, {}, project_prompt=project_prompt)
    valid, _ = _validate_llm_output(reply)
    logger.debug("LLM-Antwort für %s: %s", name, reply[:100])
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
    """Löst die Einzelprüfung der Anlage-2-Funktionen aus."""
    model = request.POST.get("model")
    try:
        check_anlage2_functions(pk, model_name=model)
    except RuntimeError:
        return JsonResponse(
            {"error": "Missing LLM credentials from environment."}, status=500
        )
    except Exception:
        logger.exception("LLM Fehler")
        return JsonResponse({"status": "error"}, status=502)
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
            Anlage2FunctionResult.objects.filter(
                projekt=anlage.projekt, funktion=sub_obj.funktion
            )
            .order_by("-id")
            .first()
        )
        if not parent_res or parent_res.technisch_verfuegbar is not True:
            return JsonResponse(
                {
                    "status": "skipped",
                    "message": "Hauptfunktion ist nicht vorhanden",
                }
            )
    else:
        logger.error(
            "FEHLER: Weder function_id noch subquestion_id im POST-Request gefunden. Sende 400 Bad Request."
        )
        return JsonResponse({"error": "invalid"}, status=400)

    task_id = async_task(
        "core.llm_tasks.worker_verify_feature",
        anlage.projekt_id,
        object_type,
        obj_id,
        model,
    )

    return JsonResponse({"status": "queued", "task_id": task_id})


@login_required
def ajax_check_task_status(request, task_id: str) -> JsonResponse:
    """Prüft den Status eines Django-Q-Tasks und gibt ihn als JSON zurück."""
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

    Anlage2FunctionResult.objects.update_or_create(
        projekt=anlage.projekt,
        funktion=funktion,
        defaults={
            "technisch_verfuegbar": status,
            "raw_json": {"notes": notes, "subquestion_id": sub_id},
            "source": "manual",
        },
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

        status_val = data.get("status")
        if status_val in (True, "True", "true", "1", 1):
            status = True
        elif status_val in (False, "False", "false", "0", 0):
            status = False
        else:
            status = None

        notes = data.get("notes", "")
        ki_beteiligt = data.get("ki_beteiligt")

        if pf_id is None or func_id is None:
            return JsonResponse({"error": "invalid"}, status=400)

        anlage = get_object_or_404(BVProjectFile, pk=pf_id)
        if anlage.anlage_nr != 2:
            return JsonResponse({"error": "invalid"}, status=400)

        funktion = get_object_or_404(Anlage2Function, pk=func_id)
        if sub_id:
            get_object_or_404(Anlage2SubQuestion, pk=sub_id)

        defaults = {
            "technisch_verfuegbar": status,
            "ki_beteiligung": ki_beteiligt,
            "raw_json": {"notes": notes, "subquestion_id": sub_id},
            "source": "manual",
            "manual_result": {
                "technisch_vorhanden": status,
                "ki_beteiligung": ki_beteiligt,
            },
        }

        anlage2_logger.debug(
            "Review gespeichert: pf=%s func=%s sub=%s status=%s ki=%s notes=%r",
            pf_id,
            func_id,
            sub_id,
            status,
            ki_beteiligt,
            notes,
        )

        res, _created = Anlage2FunctionResult.objects.update_or_create(
            projekt=anlage.projekt,
            funktion=funktion,
            defaults=defaults,
        )

        if sub_id is None:
            res.is_negotiable = True
            res.save(update_fields=["is_negotiable"])

        gap_text = res.gap_summary
        ai_val = None
        if isinstance(res.ai_result, dict):
            ai_val = res.ai_result.get("technisch_verfuegbar")
        if ai_val is not None and ai_val != status:
            task_id = async_task(
                "core.llm_tasks.worker_generate_gap_summary",
                res.id,
            )
            anlage2_logger.debug("Gap-Summary Task gestartet: %s", task_id)
            # Bei synchronem Testing wartet async_task nicht, daher neu laden
            if task_id is None:
                res.refresh_from_db()
                gap_text = res.gap_summary
        gap_text = gap_text or ""

        manual_data = anlage.manual_analysis_json or {"functions": {}}
        func_entry = manual_data.setdefault("functions", {}).setdefault(
            str(func_id), {}
        )
        if sub_id:
            sub_map = func_entry.setdefault("subquestions", {}).setdefault(
                str(sub_id), {}
            )
            sub_map["technisch_vorhanden"] = status
            sub_map["ki_beteiligung"] = ki_beteiligt
        else:
            func_entry["technisch_vorhanden"] = status
            func_entry["ki_beteiligung"] = ki_beteiligt

        anlage.manual_analysis_json = manual_data
        anlage.save(update_fields=["manual_analysis_json"])

        return JsonResponse({
            "status": "success",
            "gap_summary": gap_text,
            "is_negotiable": res.is_negotiable,
        })
    except Exception as exc:  # pragma: no cover - Schutz vor unerwarteten Fehlern
        logger.error("Fehler beim Speichern des manuellen Reviews: %s", exc)
        return JsonResponse({"status": "error", "message": str(exc)}, status=500)


@login_required
@require_POST
def ajax_reset_all_reviews(request, pk: int) -> JsonResponse:
    """L\u00f6scht alle manuellen und KI-Bewertungen f\u00fcr eine Anlage."""

    project_file = get_object_or_404(BVProjectFile, pk=pk)
    if project_file.anlage_nr != 2:
        return JsonResponse({"error": "invalid"}, status=400)

    Anlage2FunctionResult.objects.filter(
        projekt=project_file.projekt
    ).exclude(source="parser").delete()
    Anlage2FunctionResult.objects.filter(projekt=project_file.projekt).update(
        doc_result=None,
        ai_result=None,
        manual_result=None,
        is_negotiable=False,
    )
    project_file.verification_json = {}
    project_file.manual_analysis_json = None
    project_file.save(update_fields=["verification_json", "manual_analysis_json"])

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
        field == "manual_reviewed"
        and project_file.anlage_nr == 3
        and project_file.projekt.anlagen.filter(anlage_nr=3).count()
        == project_file.projekt.anlagen.filter(anlage_nr=3, manual_reviewed=True).count()
    ):
        try:
            set_project_status(project_file.projekt, "ENDGEPRUEFT")
        except ValueError:
            pass
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"status": "ok", field: new_val})
    if "HTTP_REFERER" in request.META:
        return redirect(request.META["HTTP_REFERER"])
    return redirect("projekt_detail", pk=project_file.projekt.pk)


@login_required
@require_http_methods(["POST"])
def projekt_file_delete_result(request, pk: int):
    """Löscht Analyse- und Review-Ergebnisse einer Anlage."""
    project_file = get_object_or_404(BVProjectFile, pk=pk)

    if project_file.anlage_nr == 2:
        Anlage2FunctionResult.objects.filter(
            projekt=project_file.projekt
        ).exclude(source="parser").delete()
        project_file.verification_json = {}
        Anlage2FunctionResult.objects.filter(projekt=project_file.projekt).update(
            is_negotiable=False
        )

    project_file.analysis_json = None
    project_file.manual_analysis_json = None
    project_file.manual_reviewed = False
    project_file.verhandlungsfaehig = False
    project_file.save(
        update_fields=[
            "analysis_json",
            "manual_analysis_json",
            "manual_reviewed",
            "verhandlungsfaehig",
            "verification_json",
            
        ]
    )

    if project_file.anlage_nr == 3:
        return redirect("anlage3_review", pk=project_file.projekt.pk)
    return redirect("projekt_detail", pk=project_file.projekt.pk)


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
@require_POST
def ajax_start_gutachten_generation(request, project_id):
    """Startet die Gutachten-Erstellung als Hintergrund-Task."""
    knowledge_id = request.POST.get("knowledge_id")
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid"}, status=400)

    if not SoftwareKnowledge.objects.filter(pk=knowledge_id, projekt_id=project_id).exists():
        return JsonResponse({"error": "invalid"}, status=400)

    task_id = async_task(
        "core.llm_tasks.worker_generate_gutachten",
        project_id,
        knowledge_id,
        timeout=600,
    )
    return JsonResponse({"status": "queued", "task_id": task_id})


@login_required
def gutachten_view(request, pk):
    """Zeigt den Text eines Gutachtens an."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.projekt
    context = {
        "projekt": projekt,
        "text": gutachten.text,
        "gutachten": gutachten,
        "categories": LLMConfig.get_categories(),
        "category": "gutachten",
    }
    return render(request, "gutachten_view.html", context)


@login_required
def gutachten_download(request, pk):
    """Stellt das Gutachten als formatiertes DOCX bereit."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.projekt

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
            response[
                "Content-Disposition"
            ] = f'attachment; filename="Gutachten_{projekt.title}.docx"'
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


@login_required
def gutachten_edit(request, pk):
    """Ermöglicht das Bearbeiten und erneute Speichern des Gutachtens."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.projekt
    if request.method == "POST":
        text = request.POST.get("text", "")
        gutachten.text = text
        gutachten.save(update_fields=["text"])
        messages.success(request, "Gutachten gespeichert")
        return redirect("gutachten_view", pk=gutachten.pk)
    return render(request, "gutachten_edit.html", {"projekt": projekt, "text": gutachten.text})


@login_required
@require_http_methods(["POST"])
def gutachten_delete(request, pk):
    """Löscht das Gutachten und entfernt den Verweis im Projekt."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.projekt
    gutachten.delete()
    return redirect("projekt_detail", pk=projekt.pk)


@login_required
@require_http_methods(["POST"])
def gutachten_llm_check(request, pk):
    """Löst den LLM-Funktionscheck für das Gutachten aus."""
    gutachten = get_object_or_404(Gutachten, pk=pk)
    projekt = gutachten.software_knowledge.projekt
    category = request.POST.get("model_category")
    model = LLMConfig.get_default(category) if category else None
    try:
        note = check_gutachten_functions(projekt.pk, model_name=model)
        if note:
            projekt.gutachten_function_note = note
            projekt.save(update_fields=["gutachten_function_note"])
        messages.success(request, "Gutachten geprüft")
    except ValueError:
        messages.error(request, "Kein Gutachten vorhanden")
    except RuntimeError:
        messages.error(request, "Missing LLM credentials from environment.")
    except Exception:
        logger.exception("LLM Fehler")
        messages.error(request, "LLM-Fehler beim Funktionscheck")
    return redirect("gutachten_view", pk=gutachten.pk)


@login_required
def edit_ki_justification(request, pk):
    """Erlaubt das Bearbeiten der KI-Begründung."""
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

    verif = anlage.verification_json or {}
    data = verif.get(key, {})
    if request.method == "POST":
        text = request.POST.get("ki_begruendung", "").strip()
        data["ki_begruendung"] = text
        verif[key] = data
        anlage.verification_json = verif
        anlage.save(update_fields=["verification_json"])
        messages.success(request, "Begründung gespeichert")
        return redirect("projekt_file_edit_json", pk=anlage.pk)

    context = {
        "anlage": anlage,
        "object": obj,
        "object_type": obj_type,
        "ki_begruendung": data.get("ki_begruendung", ""),
    }
    return render(request, "edit_ki_justification.html", context)


@login_required
def justification_detail_edit(request, file_id, function_key):
    """Zeigt und bearbeitet die KI-Begründung zu einer Funktion."""

    anlage = get_object_or_404(BVProjectFile, pk=file_id)
    if anlage.anlage_nr != 2:
        raise Http404

    verif = anlage.verification_json or {}
    data = verif.get(function_key, {})
    if request.method == "POST":
        form = JustificationForm(request.POST)
        if form.is_valid():
            data["ki_begruendung"] = form.cleaned_data["justification"]
            verif[function_key] = data
            anlage.verification_json = verif
            anlage.save(update_fields=["verification_json"])
            messages.success(request, "Begründung gespeichert")
            return redirect("projekt_file_edit_json", pk=anlage.pk)
    else:
        form = JustificationForm(initial={"justification": data.get("ki_begruendung", "")})

    justification_html = markdownify(data.get("ki_begruendung")) if data.get("ki_begruendung") else ""
    context = {
        "project_file": anlage,
        "function_name": function_key,
        "form": form,
        "justification_html": justification_html,
    }
    return render(request, "justification_detail.html", context)


@login_required
def justification_delete(request, file_id, function_key):
    """Löscht die KI-Begründung für einen Funktionsschlüssel."""

    anlage = get_object_or_404(BVProjectFile, pk=file_id)
    if anlage.anlage_nr != 2:
        raise Http404

    verif = anlage.verification_json or {}
    entry = verif.get(function_key, {})
    if isinstance(entry, dict) and "ki_begruendung" in entry:
        entry.pop("ki_begruendung")
        if entry:
            verif[function_key] = entry
        else:
            verif.pop(function_key, None)
        anlage.verification_json = verif
        anlage.save(update_fields=["verification_json"])
        messages.success(request, "Begründung gelöscht")

    return redirect("projekt_file_edit_json", pk=anlage.pk)

@login_required
@require_POST
def ajax_start_initial_checks(request, project_id):
    """Startet den Initialcheck für alle Software-Typen eines Projekts."""
    projekt = get_object_or_404(BVProject, pk=project_id)
    names = projekt.software_list
    tasks = []
    for name in names:
        sk, _ = SoftwareKnowledge.objects.get_or_create(
            projekt=projekt,
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
def ajax_rerun_initial_check_with_context(request) -> JsonResponse:
    """Startet den Initial-Check erneut mit zusätzlichem Kontext."""

    knowledge_id = request.POST.get("knowledge_id")
    user_context = request.POST.get("user_context", "")
    try:
        knowledge_id = int(knowledge_id)
    except (TypeError, ValueError):
        return JsonResponse({"error": "invalid"}, status=400)

    if not SoftwareKnowledge.objects.filter(pk=knowledge_id).exists():
        return JsonResponse({"error": "invalid"}, status=400)

    task_id = async_task(
        "core.llm_tasks.worker_run_initial_check",
        knowledge_id,
        user_context,
    )
    return JsonResponse({"status": "queued", "task_id": task_id})


@login_required
def edit_knowledge_description(request, knowledge_id):
    """Bearbeitet die Beschreibung eines Knowledge-Eintrags."""
    knowledge = get_object_or_404(SoftwareKnowledge, pk=knowledge_id)
    if request.method == "POST":
        form = KnowledgeDescriptionForm(request.POST, instance=knowledge)
        if form.is_valid():
            form.save()
            messages.success(request, "Beschreibung gespeichert")
            return redirect("projekt_detail", pk=knowledge.projekt.pk)
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
    """Löscht einen Knowledge-Eintrag."""
    knowledge = get_object_or_404(SoftwareKnowledge, pk=knowledge_id)
    project_pk = knowledge.projekt.pk
    knowledge.delete()
    return redirect("projekt_detail", pk=project_pk)


@login_required
def download_knowledge_as_word(request, knowledge_id):
    """Stellt die Beschreibung als Word-Datei bereit."""
    knowledge = get_object_or_404(SoftwareKnowledge, pk=knowledge_id)
    if not knowledge.description:
        raise Http404
    temp_file_path = os.path.join(tempfile.gettempdir(), f"knowledge_{knowledge_id}.docx")
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
        return redirect("projekt_detail", pk=knowledge.projekt.pk)
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


@login_required
def anlage5_dummy(request):
    """Zeigt einen Platzhalter f\xFCr Anlage 5."""
    return render(request, "anlage5_dummy.html")


@login_required
def anlage6_dummy(request):
    """Zeigt einen Platzhalter f\xFCr Anlage 6."""
    return render(request, "anlage6_dummy.html")
