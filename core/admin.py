from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django import forms
from django.utils.html import format_html
from django.contrib.admin.widgets import FilteredSelectMultiple, AdminFileWidget
from django.urls import URLPattern, URLResolver, get_resolver
from .models import (
    Recording,
    Prompt,
    Tile,
    UserTileAccess,
    Area,
    BVProjectFile,
    Anlage2Function,
    Anlage2FunctionResult,
    FormatBParserRule,
    AntwortErkennungsRegel,
    Anlage4Config,
)


def get_url_choices() -> list[tuple[str, str]]:
    """Gibt alle benannten URL-Namen als Auswahl zurück."""
    resolver = get_resolver()
    choices: list[tuple[str, str]] = []

    def collect(patterns):
        for p in patterns:
            if isinstance(p, URLPattern):
                if p.name:
                    label = p.name.replace("_", " ").title()
                    choices.append((p.name, label))
            elif isinstance(p, URLResolver):
                collect(p.url_patterns)

    collect(resolver.url_patterns)
    # Duplikate entfernen
    seen = set()
    unique_choices = []
    for name, label in choices:
        if name not in seen:
            seen.add(name)
            unique_choices.append((name, label))
    return sorted(unique_choices)


class AdminImagePreviewWidget(AdminFileWidget):
    """Widget mit Bildvorschau."""

    def render(self, name, value, attrs=None, renderer=None):
        output = []
        if value and getattr(value, "url", None):
            output.append(
                f'<img src="{value.url}" style="max-height: 100px;" />'
            )
        output.append(super().render(name, value, attrs, renderer))
        return format_html("<br>".join(output))


class AreaAdminForm(forms.ModelForm):
    """Formular für Area mit Benutzerzuweisung."""

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=FilteredSelectMultiple("Benutzer", is_stacked=False),
    )

    class Meta:
        model = Area
        fields = ["slug", "name", "image", "users"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["users"].initial = self.instance.users.all()

    def save(self, commit=True):
        area = super().save(commit)
        if commit:
            area.users.set(self.cleaned_data["users"])
        return area


class TileAdminForm(forms.ModelForm):
    """Formular für Tile mit Bildvorschau."""

    areas = forms.ModelMultipleChoiceField(
        queryset=Area.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        required=False,
        widget=FilteredSelectMultiple("Benutzer", is_stacked=False),
    )
    url_name = forms.ChoiceField(choices=[])  # wird im __init__ befüllt

    class Meta:
        model = Tile
        fields = "__all__"
        widgets = {"image": AdminImagePreviewWidget}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["url_name"].choices = get_url_choices()
        if self.instance.pk:
            self.fields["areas"].initial = self.instance.areas.all()
            self.fields["users"].initial = self.instance.users.all()

    def save(self, commit=True):
        tile = super().save(commit)
        if commit:
            tile.areas.set(self.cleaned_data["areas"])
            tile.users.set(self.cleaned_data["users"])
        return tile


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    list_display = ("user", "bereich", "audio_file", "created_at", "duration")


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ("name",)


class TileAdmin(admin.ModelAdmin):
    form = TileAdminForm
    list_display = ("name", "image_thumb", "areas_display")
    readonly_fields = ("image_thumb",)

    def areas_display(self, obj) -> str:
        """Zeigt die zugewiesenen Bereiche."""
        return ", ".join(a.name for a in obj.areas.all())

    areas_display.short_description = "Bereiche"

    def image_thumb(self, obj) -> str:
        """Gibt eine kleine Bildvorschau zurück."""
        if obj.image:
            return format_html(
                '<img src="{}" style="height:50px;" />', obj.image.url
            )
        return "-"

    image_thumb.short_description = "Bild"


@admin.register(UserTileAccess)
class UserTileAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "tile")


class AreaAdmin(admin.ModelAdmin):
    form = AreaAdminForm
    list_display = ("slug", "name", "image")


class UserTileAccessInline(admin.TabularInline):
    model = UserTileAccess
    extra = 1


class CustomUserAdmin(BaseUserAdmin):
    inlines = [UserTileAccessInline]


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Anlage2Function)
class Anlage2FunctionAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Anlage2FunctionResult)
class Anlage2FunctionResultAdmin(admin.ModelAdmin):
    list_display = (
        "projekt",
        "funktion",
        "technisch_verfuegbar",
        "ki_beteiligung",
    )


@admin.register(BVProjectFile)
class BVProjectFileAdmin(admin.ModelAdmin):
    list_display = (
        "projekt",
        "anlage_nr",
        "manual_reviewed",
        "verhandlungsfaehig",
    )
    list_editable = ("manual_reviewed", "verhandlungsfaehig")


@admin.register(FormatBParserRule)
class FormatBParserRuleAdmin(admin.ModelAdmin):
    list_display = ("key", "target_field", "ordering")
    list_editable = ("target_field", "ordering")


@admin.register(AntwortErkennungsRegel)
class AntwortErkennungsRegelAdmin(admin.ModelAdmin):
    list_display = ("regel_name", "ziel_feld", "wert", "prioritaet")
    list_editable = ("ziel_feld", "wert", "prioritaet")


class Anlage4ConfigForm(forms.ModelForm):
    class Meta:
        model = Anlage4Config
        fields = "__all__"
        widgets = {
            "prompt_template": forms.Textarea(attrs={"rows": 4}),
        }


@admin.register(Anlage4Config)
class Anlage4ConfigAdmin(admin.ModelAdmin):
    form = Anlage4ConfigForm


# Registrierung der Modelle
admin.site.register(Tile, TileAdmin)
admin.site.register(Area, AreaAdmin)


