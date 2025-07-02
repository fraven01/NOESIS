from functools import wraps
from django.http import HttpResponseForbidden


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if user.is_superuser or user.groups.filter(name="admin").exists():
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("Nicht berechtigt")
    return _wrapped


def tile_required(slug: str):
    """Erlaubt den Zugriff nur, wenn der Nutzer die angegebene Tile besitzt."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            from .models import Tile

            user = request.user
            if Tile.objects.filter(slug=slug, users=user).exists():
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("Nicht berechtigt")

        return _wrapped

    return decorator
