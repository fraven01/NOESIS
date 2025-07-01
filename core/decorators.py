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
            try:
                tile = Tile.objects.get(slug=slug)
            except Tile.DoesNotExist:
                return HttpResponseForbidden("Nicht berechtigt")

            if tile.permission:
                perm = f"{tile.permission.content_type.app_label}.{tile.permission.codename}"
                if user.has_perm(perm):
                    return view_func(request, *args, **kwargs)
            if tile.users.filter(pk=user.pk).exists():
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("Nicht berechtigt")

        return _wrapped

    return decorator
