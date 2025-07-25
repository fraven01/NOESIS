from django.urls import reverse
from .models import Area


def main_navigation(request):
    """Stellt die Navigationseinträge für das Grundlayout bereit."""
    nav = [
        {"label": "Startseite", "url": reverse("home")}
    ]
    user = request.user
    if user.is_authenticated:
        for area in Area.objects.all():
            if area.users.filter(pk=user.pk).exists():
                nav.append({"label": area.name, "url": reverse(area.slug)})
        nav.append({"label": "Mein Konto", "url": reverse("account")})
        nav.append({"label": "Abmelden", "url": reverse("logout"), "post": True})
    else:
        nav.append({"label": "Anmelden", "url": reverse("login")})
    return {"main_navigation": nav}
