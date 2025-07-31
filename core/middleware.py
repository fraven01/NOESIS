from django.contrib import messages
from django.db import DatabaseError

from .models import LLMConfig


class LLMConfigNoticeMiddleware:
    """Zeigt Admins einen Hinweis bei geänderten LLM-Modellen."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.groups.filter(name__iexact="admin").exists():
            try:
                cfg = LLMConfig.objects.first()
            except DatabaseError:
                cfg = None
            if cfg and cfg.models_changed:
                messages.warning(
                    request,
                    "Die Liste der verfügbaren LLM-Modelle hat sich geändert. Bitte prüfen Sie die LLM-Einstellungen.",
                )
        response = self.get_response(request)
        return response
