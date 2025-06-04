from django import forms
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
        f = self.cleaned_data["audio_file"]
        if f.content_type not in ["audio/wav", "audio/x-wav", "audio/mpeg"]:
            raise forms.ValidationError("Nur WAV oder MP3 erlaubt")
        return f
