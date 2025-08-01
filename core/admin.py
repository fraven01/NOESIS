from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User, Group
from django import forms
from django.utils.html import format_html
from django.contrib.admin.widgets import (
    FilteredSelectMultiple,
    AdminFileWidget,
)
from django.urls import URLPattern, URLResolver, get_resolver
from .models import (
    Tile,
    UserTileAccess,
    Area,
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
    """Formular für Area mit Gruppen-Zuweisung."""

    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=FilteredSelectMultiple("Gruppen", is_stacked=False),
    )

    class Meta:
        model = Area
        fields = ["slug", "name", "image", "groups"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["groups"].initial = self.instance.groups.all()

    def save(self, commit=True):
        area = super().save(commit)
        if commit:
            area.groups.set(self.cleaned_data["groups"])
        return area


class TileAdminForm(forms.ModelForm):
    """Formular für Tile mit Bildvorschau."""

    areas = forms.ModelMultipleChoiceField(
        queryset=Area.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=FilteredSelectMultiple("Gruppen", is_stacked=False),
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
            self.fields["groups"].initial = self.instance.groups.all()
            self.fields["users"].initial = self.instance.users.all()

    def save(self, commit=True):
        tile = super().save(commit)
        if commit:
            tile.areas.set(self.cleaned_data["areas"])
            tile.groups.set(self.cleaned_data["groups"])
            tile.users.set(self.cleaned_data["users"])
        return tile


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




# Registrierung der Modelle
admin.site.register(Tile, TileAdmin)
admin.site.register(Area, AreaAdmin)
