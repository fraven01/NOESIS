from functools import wraps
from django.http import HttpResponseForbidden


def admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.groups.filter(name='admin').exists():
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden('Nicht berechtigt')
    return _wrapped
