from django import forms
from django.forms import Textarea, modelformset_factory
import json
import logging
from pathlib import Path
from django.conf import settings


class MultiFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True
from .models import (
    Recording,
    BVProject,
    BVProjectFile,
    ProjectStatus,
    Anlage1Question,
    Anlage2Function,
    Anlage2SubQuestion,
    Anlage2Config,
    # Anlage2GlobalPhrase,
    SoftwareKnowledge,
    Area,
    LLMRole,
    Prompt,
    Tile,
    Anlage2ColumnHeading,
    AntwortErkennungsRegel,
    Anlage4Config,
    Anlage4ParserConfig,
    Anlage3ParserRule,
    ZweckKategorieA,
    SupervisionStandardNote,

    PARSER_MODE_CHOICES,
    Anlage3Metadata,
)

detail_logger = logging.getLogger("anlage2_detail")


class ActionsJSONWidget(forms.Widget):
    """Widget für die Eingabe von Aktionen als dynamische Liste."""

    template_name = "widgets/actions_json_widget.html"

    def __init__(self, choices: list[tuple[str, str]], attrs: dict | None = None) -> None:
        super().__init__(attrs)
        self.choices = choices

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if isinstance(value, dict):
            value = [{"field": k, "value": v} for k, v in value.items()]
        context["widget"]["value"] = json.dumps(value or [])
        context["choices"] = json.dumps(self.choices)
        return context
from django.contrib.auth.models import Group
from .parser_manager import parser_manager
from .llm_tasks import ANLAGE1_QUESTIONS


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


def get_parser_choices() -> list[tuple[str, str]]:
    """Liefert die verfügbaren Parser-Namen."""
    names = parser_manager.available_names()
    return [(n, n) for n in names]


class RecordingForm(forms.ModelForm):
    bereich = forms.ModelChoiceField(
        queryset=Area.objects.all(),
        widget=forms.Select(attrs={"class": "border rounded p-2"}),
    )

    class Meta:
        model = Recording
        fields = ["bereich", "audio_file"]
        widgets = {
            "audio_file": forms.ClearableFileInput(
                attrs={"class": "border rounded p-2"}
            ),
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
    class Meta:
        model = BVProject
        fields = ["title", "beschreibung", "status"]
        labels = {
            "title": "Name",
            "beschreibung": "Beschreibung",
            "status": "Status",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "beschreibung": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 5}
            ),
            "status": forms.Select(attrs={"class": "border rounded p-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance or not self.instance.pk:
            self.fields.pop("status", None)
        else:
            self.fields["status"].queryset = ProjectStatus.objects.all()

    def save(self, software_list: list[str] | None = None, commit: bool = True):
        projekt = super().save(commit=False)
        if commit:
            projekt.save()
        if software_list is not None:
            from .models import BVSoftware

            projekt.bvsoftware_set.all().delete()
            cleaned = [s.strip() for s in software_list if s.strip()]
            for name in cleaned:
                BVSoftware.objects.create(project=projekt, name=name)
            if not projekt.title and cleaned:
                projekt.title = ", ".join(cleaned)
                projekt.save(update_fields=["title"])
        if commit:
            self.save_m2m()
        return projekt


class BVProjectUploadForm(DocxValidationMixin, forms.Form):
    docx_file = forms.FileField(
        label="DOCX-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )


class BVProjectFileForm(forms.ModelForm):
    parser_order = forms.MultipleChoiceField(
        choices=get_parser_choices(), required=False
    )

    parser_mode = forms.ChoiceField(
        choices=PARSER_MODE_CHOICES, required=False
    )
    class Meta:
        model = BVProjectFile
        fields = [
            "upload",
            "parser_mode",
            "parser_order",
            "manual_comment",
        ]
        labels = {
            "upload": "Datei",
            "parser_mode": "Parser-Modus",
            "parser_order": "Parser-Reihenfolge",
            "manual_comment": "Kommentar",
            "manual_reviewed": "Manuell geprüft",
            "verhandlungsfaehig": "Verhandlungsfähig",
        }
        widgets = {
            "upload": MultiFileInput(
                attrs={"class": "hidden", "id": "id_upload", "multiple": True}
            ),
            "manual_comment": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 3}
            ),
            "manual_reviewed": forms.CheckboxInput(attrs={"class": "mr-2"}),
            "verhandlungsfaehig": forms.CheckboxInput(attrs={"class": "mr-2"}),
            "parser_mode": forms.Select(attrs={"class": "border rounded p-2"}),
            "parser_order": forms.SelectMultiple(
                attrs={"class": "border rounded p-2"}
            ),
        }

    def __init__(self, *args, anlage_nr=None, **kwargs):
        self.anlage_nr = anlage_nr
        super().__init__(*args, **kwargs)
        self.fields["manual_comment"].required = False
        if self.anlage_nr is None:
            self.anlage_nr = getattr(self.instance, "anlage_nr", None)
        nr = self.anlage_nr
        if str(nr) != "2":
            self.fields.pop("parser_mode", None)
            self.fields.pop("parser_order", None)
        else:
            self.fields["parser_order"].choices = get_parser_choices()
            if not self.is_bound:
                self.initial["parser_order"] = self.instance.parser_order

    def clean_upload(self):
        """Prüft Größe und Endung abhängig von der Anlagen-Nummer."""

        f = self.cleaned_data["upload"]
        ext = Path(f.name).suffix.lower()
        nr = self.anlage_nr or getattr(self.instance, "anlage_nr", None)

        if f.size > settings.MAX_UPLOAD_SIZE:
            raise forms.ValidationError(
                "Datei überschreitet die maximale Größe"
            )

        if nr == 3:
            if ext not in [".docx", ".pdf"]:
                raise forms.ValidationError(
                    "Nur .docx oder .pdf erlaubt für Anlage 3"
                )
        else:
            if ext != ".docx":
                raise forms.ValidationError("Nur .docx Dateien erlaubt")
        return f

    def save(self, commit: bool = True) -> BVProjectFile:
        obj = super().save(commit=False)
        if self.anlage_nr is not None:
            obj.anlage_nr = self.anlage_nr
        if "parser_mode" in self.cleaned_data:
            obj.parser_mode = self.cleaned_data.get("parser_mode") or ""
        if "parser_order" in self.cleaned_data:
            obj.parser_order = self.cleaned_data.get("parser_order") or []
        if commit:
            obj.save()
        return obj


class BVProjectFileJSONForm(forms.ModelForm):
    """Formular zum Bearbeiten der Analyse-Daten einer Anlage."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.anlage_nr == 3:
            self.fields.pop("manual_analysis_json", None)

    class Meta:
        model = BVProjectFile
        fields = [
            "analysis_json",
            "manual_analysis_json",
            "manual_reviewed",
            "verhandlungsfaehig",
        ]
        labels = {
            "analysis_json": "Automatische Analyse (JSON)",
            "manual_analysis_json": "Manuelle Analyse (JSON)",
            "manual_reviewed": "Manuell geprüft",
            "verhandlungsfaehig": "Verhandlungsfähig",
        }
        widgets = {
            "analysis_json": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 10}
            ),
            "manual_analysis_json": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 10}
            ),
            "manual_reviewed": forms.CheckboxInput(attrs={"class": "mr-2"}),
            "verhandlungsfaehig": forms.CheckboxInput(attrs={"class": "mr-2"}),
        }


class BVGapNotesForm(forms.ModelForm):
    """Formular f\u00fcr GAP-Notizen ohne Benutzereingabe."""

    class Meta:
        model = BVProjectFile
        fields: list[str] = []


class Anlage1ReviewForm(forms.Form):
    """Manuelle Prüfung der Fragen aus Anlage 1."""

    def __init__(self, *args, initial=None, **kwargs):
        super().__init__(*args, **kwargs)
        data = initial or {}
        for i in get_anlage1_numbers():
            self.fields[f"q{i}_ok"] = forms.BooleanField(
                required=False,
                label=f"Frage {i} verhandlungsfähig",
                widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
            )
            self.fields[f"q{i}_hinweis"] = forms.CharField(
                required=False,
                label=f"Frage {i} Interne Arbeitsanmerkung (Gap-Analyse)",
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.fields[f"q{i}_vorschlag"] = forms.CharField(
                required=False,
                label=f"Frage {i} (Extern) Anmerkungen für den Fachbereich",
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.initial[f"q{i}_ok"] = data.get(str(i), {}).get("ok", False)
            self.initial[f"q{i}_hinweis"] = data.get(str(i), {}).get("hinweis", "")
            self.initial[f"q{i}_vorschlag"] = data.get(str(i), {}).get("vorschlag", "")

    def get_json(self) -> dict:
        out = {}
        if not self.is_valid():
            return out
        for i in get_anlage1_numbers():
            key = str(i)
            q_data: dict[str, object] = {
                "hinweis": self.cleaned_data.get(f"q{i}_hinweis", ""),
                "vorschlag": self.cleaned_data.get(f"q{i}_vorschlag", ""),
            }
            if f"q{i}_ok" in self.cleaned_data:
                q_data["ok"] = self.cleaned_data.get(f"q{i}_ok", False)
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
            self.fields[f"func{func.id}_gap_summary"] = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.initial[f"func{func.id}_gap_summary"] = f_data.get("gap_summary", "")
            self.fields[f"func{func.id}_gap_notiz"] = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.initial[f"func{func.id}_gap_notiz"] = f_data.get("gap_notiz", "")
            for sub in func.anlage2subquestion_set.all().order_by("id"):
                s_data = f_data.get("subquestions", {}).get(str(sub.id), {})
                for field, _ in fields:
                    name = f"sub{sub.id}_{field}"
                    self.fields[name] = forms.BooleanField(
                        required=False,
                        widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
                    )
                    self.initial[name] = s_data.get(field, False)
                self.fields[f"sub{sub.id}_gap_summary"] = forms.CharField(
                    required=False,
                    widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
                )
                self.initial[f"sub{sub.id}_gap_summary"] = s_data.get("gap_summary", "")
                self.fields[f"sub{sub.id}_gap_notiz"] = forms.CharField(
                    required=False,
                    widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
                )
                self.initial[f"sub{sub.id}_gap_notiz"] = s_data.get("gap_notiz", "")

    def get_json(self) -> dict:
        out = {"functions": {}}
        if not self.is_valid():
            return out
        fields = get_anlage2_fields()
        for func in Anlage2Function.objects.order_by("name"):
            item: dict[str, object] = {}
            for field, _ in fields:
                item[field] = self.cleaned_data.get(f"func{func.id}_{field}", False)
            item["gap_summary"] = self.cleaned_data.get(
                f"func{func.id}_gap_summary", ""
            )
            item["gap_notiz"] = self.cleaned_data.get(
                f"func{func.id}_gap_notiz", ""
            )
            sub_dict: dict[str, dict] = {}
            for sub in func.anlage2subquestion_set.all().order_by("id"):
                sub_item = {
                    field: self.cleaned_data.get(f"sub{sub.id}_{field}", False)
                    for field, _ in fields
                }
                sub_item["gap_summary"] = self.cleaned_data.get(
                    f"sub{sub.id}_gap_summary", ""
                )
                sub_item["gap_notiz"] = self.cleaned_data.get(
                    f"sub{sub.id}_gap_notiz", ""
                )
                sub_dict[str(sub.id)] = sub_item
            if sub_dict:
                item["subquestions"] = sub_dict
            out["functions"][str(func.id)] = item
        return out


class Anlage4ReviewForm(forms.Form):
    """Manuelle Pr\xfcfung der Auswertungen aus Anlage 4."""

    def __init__(self, *args, items=None, initial=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = items or []
        init = initial or {}
        for idx, _text in enumerate(self.items):
            self.fields[f"item{idx}_ok"] = forms.BooleanField(
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
                label="Geprüft",
            )
            self.fields[f"item{idx}_nego"] = forms.BooleanField(
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
                label="Verhandlungsfähig",
            )
            self.fields[f"item{idx}_note"] = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
            )
            self.initial[f"item{idx}_ok"] = init.get(str(idx), {}).get("ok", False)
            self.initial[f"item{idx}_nego"] = init.get(str(idx), {}).get("nego", False)
            self.initial[f"item{idx}_note"] = init.get(str(idx), {}).get("note", "")

    def get_json(self) -> dict:
        out: dict[str, dict] = {}
        if not self.is_valid():
            return out
        for idx in range(len(self.items)):
            out[str(idx)] = {
                "ok": self.cleaned_data.get(f"item{idx}_ok", False),
                "nego": self.cleaned_data.get(f"item{idx}_nego", False),
                "note": self.cleaned_data.get(f"item{idx}_note", ""),
            }
        return out


class Anlage5ReviewForm(forms.Form):
    """Manuelle Bestätigung der Zwecke aus Anlage 5."""

    purposes = forms.ModelMultipleChoiceField(
        queryset=ZweckKategorieA.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={"class": "mr-2"}),
        required=False,
        label="Standardzwecke",
    )
    sonstige = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
        label="Sonstige Zwecke",
    )

    def get_json(self) -> dict:
        if not self.is_valid():
            return {}
        return {
            "purposes": [p.pk for p in self.cleaned_data["purposes"]],
            "sonstige": self.cleaned_data["sonstige"],
        }


class Anlage3MetadataForm(forms.ModelForm):
    """Formular f\u00fcr die extrahierten Metadaten der Anlage 3."""

    class Meta:
        model = Anlage3Metadata
        fields = ["name", "beschreibung", "zeitraum", "art"]
        labels = {
            "name": "Name der Auswertung",
            "beschreibung": "Beschreibung",
            "zeitraum": "Zeitraum",
            "art": "Art der Auswertung",
        }
        widgets = {
            "beschreibung": forms.Textarea(attrs={"class": "border rounded p-2", "rows": 2}),
        }


class Anlage6ReviewForm(forms.ModelForm):
    """Formular f\u00fcr die manuelle Sichtpr\u00fcfung von Anlage 6."""

    class Meta:
        model = BVProjectFile
        fields = ["anlage6_note", "manual_reviewed", "verhandlungsfaehig"]
        labels = {
            "anlage6_note": "Pr\u00fcfnotiz",
            "manual_reviewed": "Gepr\u00fcft",
            "verhandlungsfaehig": "Verhandlungsf\u00e4hig",
        }
        widgets = {
            "anlage6_note": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 4}
            ),
            "manual_reviewed": forms.CheckboxInput(attrs={"class": "mr-2"}),
            "verhandlungsfaehig": forms.CheckboxInput(attrs={"class": "mr-2"}),
        }


class Anlage2FunctionForm(forms.ModelForm):
    """Formular für eine Funktion aus Anlage 2."""

    name_aliases = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False
    )

    class Meta:
        model = Anlage2Function
        fields = ["name", "name_aliases"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "border rounded p-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aliases = []
        if self.instance and self.instance.detection_phrases:
            aliases = self.instance.detection_phrases.get("name_aliases", [])
        if not self.is_bound:
            self.initial["name_aliases"] = "\n".join(aliases)

    def save(self, name_aliases: list[str] | None = None, commit: bool = True):
        if name_aliases is None:
            value = self.cleaned_data.get("name_aliases", "")
            alias_list = [v.strip() for v in value.splitlines() if v.strip()]
        else:
            alias_list = [v.strip() for v in name_aliases if v.strip()]
        data = dict(self.instance.detection_phrases or {})
        data["name_aliases"] = alias_list
        self.instance.detection_phrases = data
        return super().save(commit=commit)


class Anlage2SubQuestionForm(forms.ModelForm):
    """Formular für eine Unterfrage zu Anlage 2."""

    name_aliases = forms.CharField(
        widget=Textarea(attrs={"rows": 3}), required=False
    )

    class Meta:
        model = Anlage2SubQuestion
        fields = ["frage_text", "name_aliases"]
        labels = {"frage_text": "Frage"}
        widgets = {
            "frage_text": Textarea(attrs={"class": "border rounded p-2", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aliases = []
        if self.instance and self.instance.detection_phrases:
            aliases = self.instance.detection_phrases.get("name_aliases", [])
        if not self.is_bound:
            self.initial["name_aliases"] = "\n".join(aliases)

    def save(self, name_aliases: list[str] | None = None, commit: bool = True):
        if name_aliases is None:
            value = self.cleaned_data.get("name_aliases", "")
            alias_list = [v.strip() for v in value.splitlines() if v.strip()]
        else:
            alias_list = [v.strip() for v in name_aliases if v.strip()]
        data = dict(self.instance.detection_phrases or {})
        data["name_aliases"] = alias_list
        self.instance.detection_phrases = data
        return super().save(commit=commit)


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


class PromptImportForm(forms.Form):
    """Formular für den JSON-Import der Prompts."""

    json_file = forms.FileField(
        label="JSON-Datei der Prompts",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )
    clear_first = forms.BooleanField(
        required=False,
        label="Datenbank vorher leeren",
        widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
    )


class LLMRoleImportForm(forms.Form):
    """Formular für den JSON-Import der LLM-Rollen."""

    json_file = forms.FileField(
        label="JSON-Datei der Rollen",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )


class Anlage1ImportForm(forms.Form):
    """Formular für den JSON-Import der Anlage-1-Fragen."""

    json_file = forms.FileField(
        label="JSON-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )
    clear_first = forms.BooleanField(
        required=False,
        label="Datenbank vorher leeren",
        widget=forms.CheckboxInput(attrs={"class": "mr-2"}),
    )


class Anlage2ConfigForm(forms.ModelForm):
    """Formular für die Anlage-2-Konfiguration."""

    parser_order = forms.MultipleChoiceField(
        choices=get_parser_choices(),
        required=False,
    )

    OPTIONAL_JSON_FIELDS = [
        "text_technisch_verfuegbar_true",
        "text_technisch_verfuegbar_false",
        "text_einsatz_telefonica_true",
        "text_einsatz_telefonica_false",
        "text_zur_lv_kontrolle_true",
        "text_zur_lv_kontrolle_false",
        "text_ki_beteiligung_true",
        "text_ki_beteiligung_false",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.OPTIONAL_JSON_FIELDS:
            self.fields[name] = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={"rows": 2}),
                label=self.fields[name].label,
            )
            if not self.is_bound:
                current = getattr(self.instance, name, [])
                self.initial[name] = "\n".join(current)
        # Vorhandene Instanzwerte nutzen, falls nichts übergeben wurde
        self.fields["parser_mode"].required = False

    def save(self, commit: bool = True) -> Anlage2Config:
        """Speichert nur übergebene Werte."""
        instance = super().save(commit=False)
        for name in self.OPTIONAL_JSON_FIELDS:
            value = self.cleaned_data.get(name)
            if not value:
                # Fehlender oder leerer Wert: Ursprünglichen beibehalten
                setattr(instance, name, getattr(self.instance, name))
            else:
                setattr(
                    instance,
                    name,
                    [v.strip() for v in value.splitlines() if v.strip()],
                )
        if not self.cleaned_data.get("parser_mode"):
            instance.parser_mode = self.instance.parser_mode
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Anlage2Config

        fields = [
            "enforce_subquestion_override",
            "parser_mode",
            "parser_order",
            "text_technisch_verfuegbar_true",
            "text_technisch_verfuegbar_false",
            "text_einsatz_telefonica_true",
            "text_einsatz_telefonica_false",
            "text_zur_lv_kontrolle_true",
            "text_zur_lv_kontrolle_false",
            "text_ki_beteiligung_true",
            "text_ki_beteiligung_false",
        ]
        labels = {
            "enforce_subquestion_override": "Unterfragen überschreiben Hauptfunktion",
            "parser_mode": "Parser-Modus",
            "parser_order": "Parser-Reihenfolge",
            "text_technisch_verfuegbar_true": "Text‑Parser: technisch verfügbar – Ja",
            "text_technisch_verfuegbar_false": "Text‑Parser: technisch verfügbar – Nein",
            "text_einsatz_telefonica_true": "Text‑Parser: Einsatz bei Telefónica – Ja",
            "text_einsatz_telefonica_false": "Text‑Parser: Einsatz bei Telefónica – Nein",
            "text_zur_lv_kontrolle_true": "Text‑Parser: zur LV-Kontrolle – Ja",
            "text_zur_lv_kontrolle_false": "Text‑Parser: zur LV-Kontrolle – Nein",
            "text_ki_beteiligung_true": "Text‑Parser: KI-Beteiligung – Ja",
            "text_ki_beteiligung_false": "Text‑Parser: KI-Beteiligung – Nein",
        }
        widgets = {
            "enforce_subquestion_override": forms.CheckboxInput(attrs={"class": "mr-2"}),
            "parser_mode": forms.Select(attrs={"class": "border rounded p-2"}),
            "parser_order": forms.Select(attrs={"class": "border rounded p-2"}),
            "text_technisch_verfuegbar_true": forms.Textarea(attrs={"rows": 2}),
            "text_technisch_verfuegbar_false": forms.Textarea(attrs={"rows": 2}),
            "text_einsatz_telefonica_true": forms.Textarea(attrs={"rows": 2}),
            "text_einsatz_telefonica_false": forms.Textarea(attrs={"rows": 2}),
            "text_zur_lv_kontrolle_true": forms.Textarea(attrs={"rows": 2}),
            "text_zur_lv_kontrolle_false": forms.Textarea(attrs={"rows": 2}),
            "text_ki_beteiligung_true": forms.Textarea(attrs={"rows": 2}),
            "text_ki_beteiligung_false": forms.Textarea(attrs={"rows": 2}),
        }


class EditJustificationForm(forms.Form):
    """Formular zum Bearbeiten einer KI-Begründung."""

    justification = forms.CharField(
        label="Begründung",
        required=False,
        widget=forms.Textarea(attrs={"class": "border rounded p-2", "rows": 4}),
    )


class JustificationForm(forms.Form):
    """Formular zum Bearbeiten eines KI-Begründungstextes."""

    justification = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 15}),
        label="KI-Begründung bearbeiten",
        required=False,
    )


class KnowledgeDescriptionForm(forms.ModelForm):
    """Formular zum Bearbeiten der Beschreibung einer Software."""

    class Meta:
        model = SoftwareKnowledge
        fields = ["description"]
        labels = {"description": "Beschreibung"}
        widgets = {
            "description": forms.Textarea(
                attrs={"class": "border rounded p-2 w-full", "rows": 20}
            )
        }


class ProjectContextForm(forms.ModelForm):
    """Formular zum Bearbeiten des Projekt-Kontexts."""

    class Meta:
        model = BVProject
        fields = ["project_prompt"]
        labels = {"project_prompt": "Projekt-Kontext"}
        widgets = {
            "project_prompt": forms.Textarea(
                attrs={"class": "border rounded p-2 w-full", "rows": 20}
            )
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


class LLMRoleForm(forms.ModelForm):
    """Formular zur Verwaltung von LLM-Rollen."""

    class Meta:
        model = LLMRole
        fields = ["name", "role_prompt", "is_default"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "role_prompt": Textarea(attrs={"class": "border rounded p-2", "rows": 5}),
            "is_default": forms.CheckboxInput(attrs={"class": "mr-2"}),
        }


class PromptForm(forms.ModelForm):
    """Formular zum Bearbeiten eines LLM-Prompts."""

    class Meta:
        model = Prompt
        fields = ["name", "text", "role", "use_system_role"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "text": Textarea(attrs={"class": "border rounded p-2", "rows": 5}),
            "role": forms.Select(attrs={"class": "border rounded p-2"}),
            "use_system_role": forms.CheckboxInput(attrs={"class": "mr-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        choices = [("", "--------- (Globale Standard-Rolle verwenden)")]
        all_roles = LLMRole.objects.all().order_by("name")
        for role in all_roles:
            display_name = f"{role.name} (Standard)" if role.is_default else role.name
            choices.append((role.pk, display_name))
        self.fields["role"].choices = choices


class ZweckKategorieAForm(forms.ModelForm):
    """Formular für einen Zweck der Kategorie A."""

    class Meta:
        model = ZweckKategorieA
        fields = ["beschreibung"]
        labels = {"beschreibung": "Beschreibung"}
        widgets = {
            "beschreibung": forms.Textarea(
                attrs={"class": "border rounded p-2", "rows": 3}
            )
        }


class SupervisionStandardNoteForm(forms.ModelForm):
    """Formular für eine Standardnotiz zur Supervision."""

    class Meta:
        model = SupervisionStandardNote
        fields = ["note_text", "is_active", "display_order"]
        labels = {
            "note_text": "Text der Notiz",
            "is_active": "Aktiv",
            "display_order": "Reihenfolge",
        }
        widgets = {
            "note_text": forms.TextInput(attrs={"class": "border rounded p-2"}),
            "is_active": forms.CheckboxInput(attrs={"class": "mr-2"}),
            "display_order": forms.NumberInput(attrs={"class": "border rounded p-2"}),
        }


class UserPermissionsForm(forms.Form):
    """Formular zur Bearbeitung von Benutzerrechten."""

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Gruppen",
    )
    tiles = forms.ModelMultipleChoiceField(
        queryset=Tile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Tiles",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["groups"].queryset = Group.objects.all()
        self.fields["tiles"].queryset = Tile.objects.all()
        if user is not None:
            self.fields["groups"].initial = user.groups.all()
            self.fields["tiles"].initial = user.tiles.all()


class UserImportForm(forms.Form):
    """Formular für den Import von Benutzerrechten."""

    json_file = forms.FileField(
        label="JSON-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )


class ProjectStatusImportForm(forms.Form):
    """Formular für den Import von Projektstatus."""

    json_file = forms.FileField(
        label="JSON-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )


class Anlage2ConfigImportForm(forms.Form):
    """Formular für den Import der globalen Phrasen."""

    json_file = forms.FileField(
        label="JSON-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )


class ProjectImportForm(forms.Form):
    """Formular für den Import von Projekten."""

    json_file = forms.FileField(
        label="Projekt-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )


class Anlage2ParserRuleImportForm(forms.Form):
    """Formular für den Import der Parser-Regeln."""

    json_file = forms.FileField(
        label="JSON-Datei",
        widget=forms.ClearableFileInput(attrs={"class": "border rounded p-2"}),
    )


class Anlage4ConfigForm(forms.ModelForm):
    """Formular für die Anlage-4-Konfiguration."""

    class Meta:
        model = Anlage4Config
        fields = "__all__"
        widgets = {
            "prompt_template": forms.Textarea(attrs={"rows": 4}),
        }


class Anlage4ParserPromptForm(forms.ModelForm):
    """Formular zum Bearbeiten der Anlage-4-Prompts."""

    class Meta:
        model = Anlage4ParserConfig
        fields = ["prompt_plausibility"]
        widgets = {
            "prompt_plausibility": forms.Textarea(attrs={"rows": 4}),
        }


class Anlage4ParserConfigForm(forms.ModelForm):
    """Formular für die Anlage-4-Parser-Konfiguration."""

    name_aliases = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    gesellschaft_aliases = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False
    )
    fachbereich_aliases = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False
    )

    class Meta:
        model = Anlage4ParserConfig
        fields = [
            "table_columns",
            "delimiter_phrase",
            "gesellschaften_phrase",
            "fachbereiche_phrase",
            "name_aliases",
            "gesellschaft_aliases",
            "fachbereich_aliases",
        ]
        widgets = {
            "table_columns": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in ["name_aliases", "gesellschaft_aliases", "fachbereich_aliases"]:
            self.initial[field] = "\n".join(getattr(self.instance, field, []))

    def save(
        self,
        negative_patterns: list[str] | None = None,
        alias_lists: dict[str, list[str]] | None = None,
        table_columns: list[str] | None = None,
        commit: bool = True,
    ):
        """Speichert die Parser-Konfiguration."""

        if alias_lists is None:
            for field in [
                "name_aliases",
                "gesellschaft_aliases",
                "fachbereich_aliases",
            ]:
                value = self.cleaned_data.get(field, "")
                setattr(
                    self.instance,
                    field,
                    [v.strip() for v in value.splitlines() if v.strip()],
                )
        else:
            self.instance.name_aliases = [
                v.strip() for v in alias_lists.get("name_aliases", []) if v.strip()
            ]
            self.instance.gesellschaft_aliases = [
                v.strip()
                for v in alias_lists.get("gesellschaft_aliases", [])
                if v.strip()
            ]
            self.instance.fachbereich_aliases = [
                v.strip()
                for v in alias_lists.get("fachbereich_aliases", [])
                if v.strip()
            ]

        if table_columns is not None:
            self.instance.table_columns = [c.strip() for c in table_columns if c.strip()]

        if negative_patterns is not None:
            self.instance.negative_patterns = [
                v.strip() for v in negative_patterns if v.strip()
            ]

        return super().save(commit=commit)



class AntwortErkennungsRegelForm(forms.ModelForm):
    """Formular für eine Parser-Antwortregel."""

    actions_json = forms.JSONField(
        required=False,
        widget=ActionsJSONWidget(choices=Anlage2ColumnHeading.FIELD_CHOICES),
        label="Aktionen",
    )

    class Meta:
        model = AntwortErkennungsRegel
        fields = [
            "regel_name",
            "erkennungs_phrase",
            "regel_anwendungsbereich",
            "actions_json",
            "prioritaet",
        ]
        widgets = {
            "regel_name": forms.TextInput(
                attrs={"class": "border rounded p-2 w-full"}
            ),
            "erkennungs_phrase": forms.TextInput(
                attrs={"class": "border rounded p-2 w-full"}
            ),
            "regel_anwendungsbereich": forms.Select(
                attrs={"class": "border rounded p-2 w-full"}
            ),
            "prioritaet": forms.NumberInput(attrs={"class": "border rounded p-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        detail_logger.debug(
            "Init RegelForm PK=%s actions_json=%r",
            getattr(self.instance, "pk", None),
            self.initial.get("actions_json"),
        )

    def save(self, commit: bool = True) -> AntwortErkennungsRegel:
        self.instance.actions_json = self.cleaned_data.get("actions_json")
        detail_logger.debug(
            "Speichere Regel PK=%s actions_json=%r",
            getattr(self.instance, "pk", None),
            self.instance.actions_json,
        )
        return super().save(commit=commit)


class ParserSettingsForm(forms.ModelForm):
    """Formular für parserbezogene Einstellungen einer Anlage."""

    parser_order = forms.MultipleChoiceField(
        choices=get_parser_choices(), required=False
    )
    parser_mode = forms.ChoiceField(
        choices=PARSER_MODE_CHOICES, required=False
    )

    class Meta:
        model = BVProjectFile
        fields = ["parser_mode", "parser_order"]
        widgets = {
            "parser_mode": forms.Select(attrs={"class": "border rounded p-2"}),
            "parser_order": forms.SelectMultiple(attrs={"class": "border rounded p-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parser_order"].choices = get_parser_choices()
        if self.instance and not self.is_bound:
            self.initial["parser_order"] = self.instance.parser_order

    def save(self, commit: bool = True) -> BVProjectFile:
        obj = super().save(commit=False)
        obj.parser_mode = self.cleaned_data.get("parser_mode") or ""
        obj.parser_order = self.cleaned_data.get("parser_order") or []
        if commit:
            obj.save(update_fields=["parser_mode", "parser_order"])
        return obj


class ActionForm(forms.Form):
    """Formular für eine einzelne Regel-Aktion."""

    field = forms.ChoiceField(
        choices=Anlage2ColumnHeading.FIELD_CHOICES,
        label="Feld",
    )
    value = forms.BooleanField(label="Wert", required=False)


class Anlage3ParserRuleForm(forms.ModelForm):
    """Formular für eine Parser-Regel von Anlage 3."""

    aliases = forms.CharField(widget=Textarea(attrs={"rows": 3}), required=False)

    class Meta:
        model = Anlage3ParserRule
        fields = ["field_name", "aliases", "ordering"]
        labels = {
            "field_name": "Feldname",
            "aliases": "Alias-Phrasen (eine pro Zeile)",
            "ordering": "Reihenfolge",
        }
        widgets = {
            "field_name": forms.Select(attrs={"class": "border rounded p-2"}),
            "ordering": forms.NumberInput(attrs={"class": "border rounded p-2"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and not self.is_bound:
            self.initial["aliases"] = "\n".join(self.instance.aliases or [])

    def save(self, commit: bool = True) -> Anlage3ParserRule:
        aliases_raw = self.cleaned_data.get("aliases", "")
        alias_list = [v.strip() for v in aliases_raw.splitlines() if v.strip()]
        self.instance.aliases = alias_list
        return super().save(commit=commit)


