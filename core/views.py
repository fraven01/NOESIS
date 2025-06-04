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
    rec_dir = Path(settings.BASE_DIR) / 'recordings' / bereich
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
@admin_required
def start_recording_view(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect('home')
    start_recording(bereich, Path(settings.BASE_DIR))
    return redirect('recording_page', bereich=bereich)


@login_required
@admin_required
def stop_recording_view(request, bereich):
    if bereich not in ["work", "personal"]:
        return redirect('home')
    stop_recording()
    return redirect('recording_page', bereich=bereich)


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
