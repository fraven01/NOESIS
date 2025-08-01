from functools import wraps
from django.http import HttpResponseForbidden
from .models import BVProjectFile


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
                perm = (
                    f"{tile.permission.content_type.app_label}"
                    f".{tile.permission.codename}"
                )
                if user.has_perm(perm):
                    return view_func(request, *args, **kwargs)
            if tile.users.filter(pk=user.pk).exists():
                return view_func(request, *args, **kwargs)
            if tile.groups.filter(id__in=request.user.groups.all()).exists():
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("Nicht berechtigt")

        return _wrapped

    return decorator


def updates_file_status(func):
    """Setzt den Verarbeitungsstatus einer Datei nach Abschluss des Tasks."""

    @wraps(func)
    def _wrapped(file_id: int, *args, **kwargs):
        file_obj = BVProjectFile.objects.get(pk=file_id)
        try:
            result = func(file_id, *args, **kwargs)
            file_obj.processing_status = BVProjectFile.COMPLETE
            return result
        except Exception:
            file_obj.processing_status = BVProjectFile.FAILED
            raise
        finally:
            file_obj.save(update_fields=["processing_status"])

    return _wrapped
