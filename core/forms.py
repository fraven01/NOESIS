from django import forms
from pathlib import Path
from .models import Recording, BVProject, BVProjectFile


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
    docx_file = forms.FileField(
        required=False,
        label="DOCX-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )
    class Meta:
        model = BVProject
        fields = ["beschreibung", "software_typen"]
        labels = {
            "beschreibung": "Beschreibung",
            "software_typen": "Software-Typen (kommagetrennt)",
        }
        widgets = {
            "beschreibung": forms.Textarea(attrs={"class": "border rounded p-2"}),
            "software_typen": forms.TextInput(attrs={"class": "border rounded p-2"}),
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

    def clean_docx_file(self):
        f = self.cleaned_data.get("docx_file")
        if f and not f.name.lower().endswith(".docx"):
            raise forms.ValidationError("Nur .docx Dateien erlaubt")
        return f


class BVProjectUploadForm(forms.Form):
    docx_file = forms.FileField(
        label="DOCX-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )

    def clean_docx_file(self):
        f = self.cleaned_data.get("docx_file")
        if f and not f.name.lower().endswith(".docx"):
            raise forms.ValidationError("Nur .docx Dateien erlaubt")
        return f


class BVProjectFileForm(forms.ModelForm):
    class Meta:
        model = BVProjectFile
        fields = ["anlage_nr", "upload"]
        labels = {"anlage_nr": "Anlage Nr", "upload": "Datei"}
        widgets = {
            "anlage_nr": forms.Select(
                choices=[(i, str(i)) for i in range(1, 7)],
                attrs={"class": "border rounded p-2"},
            ),
            "upload": forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
        }

