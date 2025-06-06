from django import forms
from pathlib import Path
from .models import Recording, BVProject


class RecordingForm(forms.ModelForm):
    class Meta:
        model = Recording
        fields = ["bereich", "audio_file"]
        widgets = {
            "bereich": forms.Select(
                choices=Recording.BEREICH_CHOICES,
                attrs={"class": "border rounded p-2"},
            ),
            "audio_file": forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
        }

    def clean_audio_file(self):
        """Prüft die Dateiendung des Uploads."""
        f = self.cleaned_data["audio_file"]
        ext = Path(f.name).suffix.lower()
        if ext not in [".wav", ".mkv"]:
            raise forms.ValidationError("Nur WAV oder MKV erlaubt")
        return f


class TranscriptUploadForm(forms.Form):
    """Formular zum manuellen Hochladen eines Transkripts."""

    recording = forms.ModelChoiceField(queryset=Recording.objects.none())
    transcript_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["recording"].queryset = Recording.objects.filter(
                user=user, transcript_file=""
            )
        self.fields["recording"].widget.attrs.update({"class": "border rounded p-2"})

    def clean_transcript_file(self):
        f = self.cleaned_data["transcript_file"]
        if not f.name.endswith(".md"):
            raise forms.ValidationError("Nur .md Dateien erlaubt")
        return f


class BVProjectForm(forms.ModelForm):
    class Meta:
        model = BVProject
        fields = ["beschreibung", "software_typen", "status"]
        labels = {
            "beschreibung": "Beschreibung",
            "software_typen": "Software-Typen (kommagetrennt)",
            "status": "Status",
        }
        widgets = {
            "beschreibung": forms.Textarea(attrs={"class": "border rounded p-2"}),
            "software_typen": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "status": forms.Select(attrs={"class": "border rounded p-2"}),
        }

    def clean_software_typen(self) -> str:
        """Bereinigt die Eingabe und stellt sicher, dass sie nicht leer ist."""
        raw = self.cleaned_data.get("software_typen", "")
        names = [s.strip() for s in raw.split(",") if s.strip()]
        if not names:
            raise forms.ValidationError(
                "Software-Typen dürfen nicht leer sein.")
        cleaned = ", ".join(names)
        return cleaned

    def save(self, commit: bool = True):
        """Speichert das Projekt mit Titel aus den Software-Namen."""
        instance: BVProject = super().save(commit=False)
        cleaned = self.cleaned_data["software_typen"]
        instance.software_typen = cleaned
        instance.title = cleaned
        if commit:
            instance.save()
        return instance

