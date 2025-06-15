from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    Recording,
    Prompt,
    Tile,
    UserTileAccess,
    Area,
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
    list_display = ("slug", "name", "bereich", "url_name", "image")


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


