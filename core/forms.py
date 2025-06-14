from django import forms
from django.forms import Textarea, modelformset_factory
from pathlib import Path
from .models import (
    Recording,
    BVProject,
    BVProjectFile,
    ProjectStatus,
    Anlage1Question,
    Anlage2Function,
    Anlage2SubQuestion,
    Anlage2Config,
    Anlage2GlobalPhrase,
    SoftwareKnowledge,
    Area,
)

try:
    from .models import SoftwareType
except Exception:  # pragma: no cover - optional model
    SoftwareType = None
from .llm_tasks import ANLAGE1_QUESTIONS


# Auswahloptionen für die Bewertung einer Frage in Anlage 1
REVIEW_STATUS_CHOICES = [
    ("ok", "ok"),
    ("unklar", "unklar"),
    ("unvollständig", "unvollständig"),
]


def get_anlage1_numbers() -> list[int]:
    """Gibt die vorhandenen Fragen-Nummern zurück."""
    qs = list(Anlage1Question.objects.order_by("num"))
    if qs:
        return [q.num for q in qs]
    return list(range(1, len(ANLAGE1_QUESTIONS) + 1))


def get_anlage2_fields() -> list[tuple[str, str]]:
    """Liefert die Spaltenüberschriften für Anlage 2."""
    cfg = Anlage2Config.get_instance()
    out: list[tuple[str, str]] = []
    defaults = {
        "technisch_vorhanden": "Technisch vorhanden",
        "einsatz_bei_telefonica": "Einsatz bei Telefónica",
        "zur_lv_kontrolle": "Zur LV-Kontrolle",
        "ki_beteiligung": "KI-Beteiligung",
    }
    for field, label in defaults.items():
        heading = cfg.headers.filter(field_name=field).first() if cfg else None
        out.append((field, heading.text if heading else label))
    return out


class RecordingForm(forms.ModelForm):
    bereich = forms.ModelChoiceField(
        queryset=Area.objects.all(),
        widget=forms.Select(attrs={"class": "border rounded p-2"}),
    )

    class Meta:
        model = Recording
        fields = ["bereich", "audio_file"]
        widgets = {
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


class DocxValidationMixin:
    """Mixin mit Validierung für DOCX-Dateien."""

    def clean_docx_file(self):
        """Erlaubt nur Dateien mit der Endung .docx."""
        f = self.cleaned_data.get("docx_file")
        if f and not f.name.lower().endswith(".docx"):
            raise forms.ValidationError("Nur .docx Dateien erlaubt")
        return f


class BVProjectForm(DocxValidationMixin, forms.ModelForm):
    docx_file = forms.FileField(
        required=False,
        label="DOCX-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )
    if SoftwareType:
        software_type = forms.ModelMultipleChoiceField(
            queryset=SoftwareType.objects.none(),
            widget=forms.CheckboxSelectMultiple,
            required=False,
            label="Software-Typen",
        )
    class Meta:
        model = BVProject
        fields = ["title", "beschreibung", "software_typen", "status"]
        labels = {
            "title": "Name",
            "beschreibung": "Beschreibung",
            "software_typen": "Software-Typen",
            "status": "Status",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "beschreibung": forms.Textarea(attrs={"class": "border rounded p-2"}),
            "software_typen": forms.HiddenInput(),
            "status": forms.Select(attrs={"class": "border rounded p-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if SoftwareType:
            self.fields["software_type"].queryset = SoftwareType.objects.all()
        if not self.instance or not self.instance.pk:
            self.fields.pop("status", None)
        else:
            self.fields["status"].queryset = ProjectStatus.objects.all()
        if self.data:
            self.software_list = [
                s.strip() for s in self.data.getlist("software") if s.strip()
            ]
        else:
            raw = self.initial.get("software_typen") or getattr(
                self.instance, "software_typen", ""
            )
            self.software_list = [s.strip() for s in raw.split(",") if s.strip()]

    def clean_software_typen(self) -> str:
        """Bereinigt die Eingabe und stellt sicher, dass sie nicht leer ist."""
        raw_list = self.data.getlist("software")
        if raw_list:
            names = [s.strip() for s in raw_list if s.strip()]
        else:
            raw = self.cleaned_data.get("software_typen", "")
            names = [s.strip() for s in raw.split(",") if s.strip()]
        if not names:
            raise forms.ValidationError(
                "Software-Typen dürfen nicht leer sein.")
        cleaned = ", ".join(names)
        self.software_list = names
        return cleaned



class BVProjectUploadForm(DocxValidationMixin, forms.Form):
    docx_file = forms.FileField(
        label="DOCX-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )



class BVProjectFileForm(forms.ModelForm):
    class Meta:
        model = BVProjectFile
        fields = ["anlage_nr", "upload", "manual_comment", "manual_analysis_json"]
        labels = {
            "anlage_nr": "Anlage Nr",
            "upload": "Datei",
            "manual_comment": "Kommentar",
            "manual_analysis_json": "Manuelle Analyse (JSON)",
        }
        widgets = {
            "anlage_nr": forms.Select(
                choices=[(i, str(i)) for i in range(1, 7)],
                attrs={"class": "border rounded p-2"},
            ),
            "upload": forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
            "manual_comment": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 3}
            ),
            "manual_analysis_json": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 5}
            ),
        }


class BVProjectFileJSONForm(forms.ModelForm):
    """Formular zum Bearbeiten der Analyse-Daten einer Anlage."""

    class Meta:
        model = BVProjectFile
        fields = ["analysis_json", "manual_analysis_json"]
        labels = {
            "analysis_json": "Automatische Analyse (JSON)",
            "manual_analysis_json": "Manuelle Analyse (JSON)",
        }
        widgets = {
            "analysis_json": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 10}
            ),
            "manual_analysis_json": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 10}
            ),
        }


class Anlage1ReviewForm(forms.Form):
    """Manuelle Prüfung der Fragen aus Anlage 1."""

    def __init__(self, *args, initial=None, **kwargs):
        super().__init__(*args, **kwargs)
        data = initial or {}
        for i in get_anlage1_numbers():
            self.fields[f"q{i}_ok"] = forms.BooleanField(
                required=False,
                label=f"Frage {i} geprüft und in Ordnung",
                widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
            )
            self.fields[f"q{i}_note"] = forms.CharField(
                required=False,
                label=f"Frage {i} Kommentar intern",
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.fields[f"q{i}_status"] = forms.ChoiceField(
                required=False,
                choices=REVIEW_STATUS_CHOICES,
                label=f"Frage {i} Status",
                widget=forms.Select(attrs={"class": "border rounded p-2"}),
            )
            self.fields[f"q{i}_hinweis"] = forms.CharField(
                required=False,
                label=f"Frage {i} Hinweise PMO",
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.fields[f"q{i}_vorschlag"] = forms.CharField(
                required=False,
                label=f"Frage {i} Vorschlag an Fachbereich",
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.initial[f"q{i}_ok"] = data.get(str(i), {}).get("ok", False)
            self.initial[f"q{i}_note"] = data.get(str(i), {}).get("note", "")
            self.initial[f"q{i}_status"] = data.get(str(i), {}).get("status", "")
            self.initial[f"q{i}_hinweis"] = data.get(str(i), {}).get("hinweis", "")
            self.initial[f"q{i}_vorschlag"] = data.get(str(i), {}).get("vorschlag", "")

    def get_json(self) -> dict:
        out = {}
        if not self.is_valid():
            return out
        for i in get_anlage1_numbers():
            key = str(i)
            q_data: dict[str, object] = {
                "status": self.cleaned_data.get(f"q{i}_status", ""),
                "hinweis": self.cleaned_data.get(f"q{i}_hinweis", ""),
                "vorschlag": self.cleaned_data.get(f"q{i}_vorschlag", ""),
            }
            if f"q{i}_ok" in self.cleaned_data:
                q_data["ok"] = self.cleaned_data.get(f"q{i}_ok", False)
            if f"q{i}_note" in self.cleaned_data:
                q_data["note"] = self.cleaned_data.get(f"q{i}_note", "")
            out[key] = q_data
        return out





class Anlage2ReviewForm(forms.Form):
    """Manuelle Pr\xfcfung der Funktionen aus Anlage 2."""

    def __init__(self, *args, initial=None, **kwargs):
        super().__init__(*args, **kwargs)
        data = (initial or {}).get("functions", {})
        fields = get_anlage2_fields()
        for func in Anlage2Function.objects.order_by("name"):
            f_data = data.get(str(func.id), {})
            for field, _ in fields:
                name = f"func{func.id}_{field}"
                self.fields[name] = forms.BooleanField(
                    required=False,
                    widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
                )
                self.initial[name] = f_data.get(field, False)
            for sub in func.anlage2subquestion_set.all().order_by("id"):
                s_data = f_data.get("subquestions", {}).get(str(sub.id), {})
                for field, _ in fields:
                    name = f"sub{sub.id}_{field}"
                    self.fields[name] = forms.BooleanField(
                        required=False,
                        widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
                    )
                    self.initial[name] = s_data.get(field, False)

    def get_json(self) -> dict:
        out = {"functions": {}}
        if not self.is_valid():
            return out
        fields = get_anlage2_fields()
        for func in Anlage2Function.objects.order_by("name"):
            item: dict[str, object] = {}
            for field, _ in fields:
                item[field] = self.cleaned_data.get(
                    f"func{func.id}_{field}", False
                )
            sub_dict: dict[str, dict] = {}
            for sub in func.anlage2subquestion_set.all().order_by("id"):
                sub_item = {
                    field: self.cleaned_data.get(f"sub{sub.id}_{field}", False)
                    for field, _ in fields
                }
                sub_dict[str(sub.id)] = sub_item
            if sub_dict:
                item["subquestions"] = sub_dict
            out["functions"][str(func.id)] = item
        return out



class Anlage2FunctionForm(forms.ModelForm):
    """Formular für eine Funktion aus Anlage 2."""

    class Meta:
        model = Anlage2Function
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "border rounded p-2"}),
        }


class Anlage2SubQuestionForm(forms.ModelForm):
    """Formular für eine Unterfrage zu Anlage 2."""

    class Meta:
        model = Anlage2SubQuestion
        fields = ["frage_text", "detection_phrases"]
        labels = {"frage_text": "Frage"}
        widgets = {
            "frage_text": Textarea(attrs={"class": "border rounded p-2", "rows": 3}),
            "detection_phrases": Textarea(attrs={"rows": 10}),
        }


class Anlage2FunctionImportForm(forms.Form):
    """Formular für den JSON-Import des Funktionskatalogs."""

    json_file = forms.FileField(
        label="JSON-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )
    clear_first = forms.BooleanField(
        required=False,
        label="Datenbank vorher leeren",
        widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
    )


class PhraseForm(forms.Form):
    """Einzelnes Feld für eine Erkennungsphrase."""

    phrase = forms.CharField(
        label="",
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class Anlage2GlobalPhraseForm(forms.ModelForm):
    """Formular für eine globale Erkennungsphrase."""

    class Meta:
        model = Anlage2GlobalPhrase
        fields = ["phrase_text"]
        labels = {"phrase_text": ""}
        widgets = {
            "phrase_text": forms.TextInput(attrs={"class": "form-control"}),
        }


Anlage2GlobalPhraseFormSet = modelformset_factory(
    Anlage2GlobalPhrase,
    form=Anlage2GlobalPhraseForm,
    extra=1,
    can_delete=True,
)


class Anlage2ConfigForm(forms.ModelForm):
    """Formular für die Anlage-2-Konfiguration."""

    class Meta:
        model = Anlage2Config
        fields = ["enforce_subquestion_override"]
        labels = {
            "enforce_subquestion_override": "Unterfragen überschreiben Hauptfunktion",
        }
        widgets = {
            "enforce_subquestion_override": forms.CheckboxInput(attrs={"class": "mr-2"}),
        }


class EditJustificationForm(forms.Form):
    """Formular zum Bearbeiten einer KI-Begründung."""

    justification = forms.CharField(
        label="Begründung",
        required=False,
        widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 4}),
    )


class KnowledgeDescriptionForm(forms.ModelForm):
    """Formular zum Bearbeiten der Beschreibung einer Software."""

    class Meta:
        model = SoftwareKnowledge
        fields = ["description"]
        labels = {"description": "Beschreibung"}
        widgets = {
            "description": forms.Textarea(attrs={"class": "border rounded p-2", "rows": 5})
        }



class ProjectStatusForm(forms.ModelForm):
    """Formular für einen Projektstatus."""

    class Meta:
        model = ProjectStatus
        fields = ["name", "key", "ordering", "is_default", "is_done_status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "key": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "ordering": forms.NumberInput(attrs={"class": "border rounded p-2"}),
            "is_default": forms.CheckboxInput(attrs={"class": "mr-2"}),
            "is_done_status": forms.CheckboxInput(attrs={"class": "mr-2"}),
        }

