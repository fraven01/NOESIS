from pathlib import Path
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.http import HttpResponseBadRequest
import subprocess

from .forms import RecordingForm
from .models import Recording

from .decorators import admin_required
from .obs_utils import start_recording, stop_recording, is_recording
import time
import markdown
from django.conf import settings


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
    else:
        start_recording(bereich, Path(settings.MEDIA_ROOT))

    if "HTTP_REFERER" in request.META:
        return redirect(request.META["HTTP_REFERER"])
    return redirect("talkdiary_%s" % bereich)


@login_required
def upload_recording(request):
    if request.method == "POST":
        form = RecordingForm(request.POST, request.FILES)
        if form.is_valid():
            recording = form.save(commit=False)
            recording.user = request.user
            recording.save()

            out_dir = Path(settings.MEDIA_ROOT) / f"transcripts/{recording.bereich}"
            out_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                "whisper",
                recording.audio_file.path,
                "--model",
                "base",
                "--language",
                "de",
                "--output_format",
                "txt",
                "--output_dir",
                str(out_dir),
            ]

            try:
                subprocess.run(cmd, check=True)
            except Exception:
                return HttpResponseBadRequest("Transkription fehlgeschlagen")

            txt_path = out_dir / f"{Path(recording.audio_file.name).stem}.txt"
            if txt_path.exists():
                md_path = out_dir / f"{Path(recording.audio_file.name).stem}.md"
                txt_content = txt_path.read_text(encoding="utf-8")
                md_path.write_text(txt_content, encoding="utf-8")
                with md_path.open("rb") as f:
                    recording.transcript_file.save(md_path.name, f, save=False)
                lines = txt_content.splitlines()[:5]
                recording.excerpt = "\n".join(lines)
                recording.save()

            return redirect("dashboard")
    else:
        form = RecordingForm()

    return render(request, "upload_recording.html", {"form": form})


@login_required
def dashboard(request):
    recordings = Recording.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "dashboard.html", {"recordings": recordings})


def _process_recordings_for_user(bereich: str, user) -> list:
    """Convert and transcribe recordings for ``bereich`` and ``user``.

    Returns a list of :class:`Recording` objects found or created.
    """
    media_root = Path(settings.MEDIA_ROOT)
    base_dir = Path(settings.BASE_DIR)
    rec_dir = media_root / "recordings" / bereich
    trans_dir = media_root / "transcripts" / bereich
    rec_dir.mkdir(parents=True, exist_ok=True)
    trans_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = base_dir / "tools" / ("ffmpeg.exe" if (base_dir / "tools" / "ffmpeg.exe").exists() else "ffmpeg")
    if not ffmpeg.exists():
        ffmpeg = "ffmpeg"

    # convert mkv to wav and remove mkv
    for mkv in list(rec_dir.glob("*.mkv")) + list(rec_dir.glob("*.MKV")):
        wav = mkv.with_suffix(".wav")
        if not wav.exists():
            try:
                subprocess.run([str(ffmpeg), "-y", "-i", str(mkv), str(wav)], check=True)
                mkv.unlink(missing_ok=True)
            except Exception:
                pass

    # transcribe wav files
    for wav in list(rec_dir.glob("*.wav")) + list(rec_dir.glob("*.WAV")):
        md = trans_dir / f"{wav.stem}.md"
        if not md.exists():
            cmd = [
                "whisper",
                str(wav),
                "--model",
                "base",
                "--language",
                "de",
                "--output_format",
                "md",
                "--output_dir",
                str(trans_dir),
            ]
            try:
                subprocess.run(cmd, check=True)
            except Exception:
                pass

    recordings = []
    for wav in list(rec_dir.glob("*.wav")) + list(rec_dir.glob("*.WAV")):
        md = trans_dir / f"{wav.stem}.md"
        excerpt = ""
        if md.exists():
            lines = md.read_text(encoding="utf-8").splitlines()[:2]
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
        recordings.append(rec_obj)

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
