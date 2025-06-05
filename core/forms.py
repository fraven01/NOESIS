from django import forms
from pathlib import Path
from .models import Recording


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
