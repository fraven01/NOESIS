from pathlib import Path
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from .decorators import admin_required
from .obs_utils import start_recording, stop_recording, is_recording
from django.conf import settings


@login_required
def home(request):
    return render(request, 'home.html')


@login_required
def work(request):
    return render(request, 'work.html')


@login_required
def personal(request):
    return render(request, 'personal.html')


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
