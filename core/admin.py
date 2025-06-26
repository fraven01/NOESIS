from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    Recording,
    Prompt,
    Tile,
    UserTileAccess,
    Area,
    BVProject,
    BVProjectFile,
    Anlage2Function,
    Anlage2FunctionResult,
)


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    list_display = ("user", "bereich", "audio_file", "created_at", "duration")


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Tile)
class TileAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "url_name", "areas_display", "image")

    def areas_display(self, obj) -> str:
        """Zeigt die zugewiesenen Bereiche."""
        return ", ".join(a.name for a in obj.areas.all())

    areas_display.short_description = "Bereiche"


@admin.register(UserTileAccess)
class UserTileAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "tile")


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "image")


class UserTileAccessInline(admin.TabularInline):
    model = UserTileAccess
    extra = 1


class CustomUserAdmin(BaseUserAdmin):
    inlines = [UserTileAccessInline]


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(BVProject)
class BVProjectAdmin(admin.ModelAdmin):
    """Benutzerfreundliche Darstellung von BV-Projekten im Admin."""

    list_display = ("title", "status", "created_at", "software_typen")
    list_filter = ("status",)
    search_fields = ("title", "beschreibung", "software_typen")
    fieldsets = (
        (
            "Allgemeine Projektinformationen",
            {"fields": ("title", "software_typen", "status")},
        ),
        (
            "Inhaltliche Beschreibung",
            {"classes": ("collapse",), "fields": ("beschreibung",)},
        ),
        (
            "Klassifizierung & Gutachten (Automatisch generiert)",
            {
                "classes": ("collapse",),
                "fields": (
                    "classification_json",
                    "gutachten_file",
                    "gutachten_function_note",
                ),
            },
        ),
    )


@admin.register(Anlage2Function)
class Anlage2FunctionAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Anlage2FunctionResult)
class Anlage2FunctionResultAdmin(admin.ModelAdmin):
    list_display = (
        "projekt",
        "funktion",
        "technisch_verfuegbar",
        "ki_beteiligung",
        "source",
    )
    list_filter = ("source", "technisch_verfuegbar", "ki_beteiligung")


@admin.register(BVProjectFile)
class BVProjectFileAdmin(admin.ModelAdmin):
    list_display = (
        "projekt",
        "anlage_nr",
        "manual_reviewed",
        "verhandlungsfaehig",
    )
    list_editable = ("manual_reviewed", "verhandlungsfaehig")


