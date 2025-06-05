from pathlib import Path
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.core.files.storage import default_storage
from django.contrib import messages
import os
import subprocess
import whisper
import torch

from .forms import RecordingForm
from .models import Recording, transcript_upload_path

from .decorators import admin_required
from .obs_utils import start_recording, stop_recording, is_recording

import logging

import time

import markdown
from django.conf import settings

logger = logging.getLogger(__name__)

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


@login_required
def home(request):
    return render(request, 'home.html')


@login_required
def work(request):
    is_admin = request.user.groups.filter(name='admin').exists()
    context = {
        'is_admin': is_admin,
    }
    return render(request, 'work.html', context)


@login_required
def personal(request):
    is_admin = request.user.groups.filter(name='admin').exists()
    context = {
        'is_admin': is_admin,
    }
    return render(request, 'personal.html', context)


@login_required
def account(request):
    return render(request, 'account.html')


@login_required
@admin_required
def recording_page(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect('home')
    rec_dir = Path(settings.MEDIA_ROOT) / 'recordings' / bereich
    files = []
    if rec_dir.exists():
        for f in sorted(rec_dir.iterdir(), reverse=True):
            files.append({
                'name': f.name,
                'mtime': f.stat().st_mtime
            })
    context = {
        'bereich': bereich,
        'is_recording': is_recording(),
        'recordings': files,
    }
    return render(request, 'recording.html', context)


@login_required
def start_recording_view(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect('home')
    start_recording(bereich, Path(settings.MEDIA_ROOT))
    return redirect('recording_page', bereich=bereich)


@login_required
def stop_recording_view(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect('home')
    stop_recording()
    time.sleep(1)
    _process_recordings_for_user(bereich, request.user)
    return redirect('recording_page', bereich=bereich)


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
            logger.debug("Upload erhalten: %s f\u00fcr Bereich %s", uploaded.name, bereich)

            rel_path = Path("recordings") / bereich / uploaded.name
            storage_name = default_storage.get_available_name(str(rel_path))
            if storage_name != str(rel_path):
                messages.info(request, "Datei existierte bereits, wurde umbenannt.")

            file_path = default_storage.save(storage_name, uploaded)
            logger.debug("Datei gespeichert: %s", file_path)

            abs_path = default_storage.path(file_path)
            final_rel = file_path
            if Path(abs_path).suffix.lower() == ".mkv":
                ffmpeg = Path(settings.BASE_DIR) / "tools" / (
                    "ffmpeg.exe" if (Path(settings.BASE_DIR) / "tools" / "ffmpeg.exe").exists() else "ffmpeg"
                )
                if not ffmpeg.exists():
                    ffmpeg = "ffmpeg"
                wav_rel = Path(file_path).with_suffix(".wav")
                wav_storage = default_storage.get_available_name(str(wav_rel))
                wav_abs = default_storage.path(wav_storage)
                try:
                    logger.debug("Konvertiere %s nach %s", abs_path, wav_abs)
                    subprocess.run([str(ffmpeg), "-y", "-i", abs_path, wav_abs], check=True)
                    Path(abs_path).unlink(missing_ok=True)
                    final_rel = wav_storage
                except Exception:
                    return HttpResponseBadRequest("Konvertierung fehlgeschlagen")

            if Recording.objects.filter(audio_file=final_rel, user=request.user).exists():
                messages.info(request, "Aufnahme bereits in der Datenbank.")
                return redirect("dashboard")

            recording = Recording.objects.create(
                user=request.user,
                bereich=bereich,
                audio_file=final_rel,
            )

            out_dir = Path(settings.MEDIA_ROOT) / f"transcripts/{recording.bereich}"
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

    logger.debug("Beginne Verarbeitung f\u00fcr Bereich '%s' und Benutzer '%s'", bereich, user)
    media_root = Path(settings.MEDIA_ROOT)
    base_dir = Path(settings.BASE_DIR)
    rec_dir = media_root / "recordings" / bereich
    trans_dir = media_root / "transcripts" / bereich

    rec_dir.mkdir(parents=True, exist_ok=True)
    trans_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = base_dir / "tools" / (
        "ffmpeg.exe" if (base_dir / "tools" / "ffmpeg.exe").exists() else "ffmpeg"
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
                subprocess.run([str(ffmpeg), "-y", "-i", str(mkv), str(wav)], check=True)

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
            bereich=bereich,
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
def talkdiary(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect("home")

    # always process new recordings; manual rescan available via query param
    _process_recordings_for_user(bereich, request.user)

    recordings = Recording.objects.filter(user=request.user, bereich=bereich).order_by("-created_at")

    context = {
        "bereich": bereich,
        "recordings": recordings,
        "is_recording": is_recording(),
        "is_admin": request.user.groups.filter(name="admin").exists(),

    }
    return render(request, "talkdiary.html", context)


@login_required
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

    html = markdown.markdown(md_text)

    context = {
        "recording": rec,
        "transcript_html": html,
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

    ffmpeg = Path(settings.BASE_DIR) / "tools" / ("ffmpeg.exe" if (Path(settings.BASE_DIR) / "tools" / "ffmpeg.exe").exists() else "ffmpeg")
    if not ffmpeg.exists():
        ffmpeg = "ffmpeg"

    if audio_path.suffix.lower() == ".mkv":
        wav_path = audio_path.with_suffix(".wav")
        try:
            logger.debug("Konvertiere %s nach %s", audio_path, wav_path)
            subprocess.run([str(ffmpeg), "-y", "-i", str(audio_path), str(wav_path)], check=True)
        except Exception as exc:
            logger.error("ffmpeg failed: %s", exc)
            messages.error(request, "Konvertierung fehlgeschlagen")
            return redirect("talkdiary_%s" % rec.bereich)
        audio_path = wav_path
        rec.audio_file.name = f"recordings/{rec.bereich}/{wav_path.name}"
        rec.save()

    messages.info(request, "Transkription gestartet")

    model = _get_whisper_model()
    try:
        logger.debug("Starte Transkription: %s", audio_path)
        result = model.transcribe(str(audio_path), language="de")
    except Exception as exc:
        logger.error("whisper failed: %s", exc)
        messages.error(request, "Transkription fehlgeschlagen")
        return redirect("talkdiary_%s" % rec.bereich)

    md_path = out_dir / f"{Path(rec.audio_file.name).stem}.md"
    md_path.write_text(result["text"], encoding="utf-8")
    with md_path.open("rb") as f:
        rec.transcript_file.save(md_path.name, f, save=False)
    rec.excerpt = "\n".join(result["text"].splitlines()[:5])
    rec.save()
    logger.debug("Transkription abgeschlossen f\u00fcr %s", rec)
    messages.success(request, "Transkription abgeschlossen")

    return redirect("talkdiary_%s" % rec.bereich)


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
        rec.transcript_missing = (
            rec.transcript_file == "" or (transcript_path and not transcript_path.exists())
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
                (Path(settings.MEDIA_ROOT) / rec.audio_file.name).unlink(missing_ok=True)
            if rec.transcript_file:
                (Path(settings.MEDIA_ROOT) / rec.transcript_file.name).unlink(missing_ok=True)
            rec.delete()
        return redirect("admin_talkdiary")

    context = {
        "recordings": filtered,
        "active_filter": active_filter or "",
    }
    return render(request, "admin_talkdiary.html", context)
