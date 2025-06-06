from django.conf import settings
from django.db import models
from django.utils import timezone
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
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    duration = models.FloatField(null=True, blank=True)
    excerpt = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.audio_file.name} ({self.bereich})"

    @property
    def recording_path(self):
        return self.audio_file.name

    @property
    def transcript_path(self):
        return self.transcript_file.name if self.transcript_file else ""


class BVProject(models.Model):
    """Projekt zur Bewertung von Betriebsvereinbarungen."""

    title = models.CharField("Titel", max_length=50, blank=True)
    beschreibung = models.TextField("Beschreibung", blank=True)
    software_typen = models.CharField(
        "Software-Typen", max_length=200, blank=True
    )
    created_at = models.DateTimeField("Erstellt am", auto_now_add=True)
    llm_geprueft = models.BooleanField("LLM geprüft", default=False)
    llm_antwort = models.TextField("LLM-Antwort", blank=True)
    llm_initial_output = models.TextField("LLM Initialantwort", blank=True)
    llm_validated = models.BooleanField("LLM validiert", default=False)
    llm_geprueft_am = models.DateTimeField("LLM geprüft am", null=True, blank=True)
    system_classification = models.JSONField(blank=True, null=True)
    anlage1_check = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        """Speichert das Projekt und setzt den Titel aus den Software-Namen."""
        if self.software_typen:
            cleaned = ", ".join([s.strip() for s in self.software_typen.split(",") if s.strip()])
            self.software_typen = cleaned
            self.title = cleaned
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.title


def project_file_upload_path(instance, filename):
    return f"bvprojects/{instance.project_id}/{filename}"


class BVProjectFile(models.Model):
    """Datei, die einem BVProject zugeordnet ist."""

    project = models.ForeignKey(
        BVProject, related_name="files", on_delete=models.CASCADE
    )
    category = models.CharField(max_length=50, blank=True)
    file = models.FileField(upload_to=project_file_upload_path)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.project_id}:{self.file.name}"

