from django.conf import settings
from django.db import models
from pathlib import Path


def recording_upload_path(instance, filename):
    return f"recordings/{instance.bereich}/{filename}"


def transcript_upload_path(instance, filename):
    stem = Path(filename).stem
    return f"transcripts/{instance.bereich}/{stem}.md"


class Recording(models.Model):
    PERSONAL = "personal"
    WORK = "work"
    BEREICH_CHOICES = [
        (PERSONAL, "personal"),
        (WORK, "work"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    bereich = models.CharField(max_length=10, choices=BEREICH_CHOICES)
    audio_file = models.FileField(upload_to=recording_upload_path)
    transcript_file = models.FileField(upload_to=transcript_upload_path, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    excerpt = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.audio_file.name} ({self.bereich})"
