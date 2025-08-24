"""Gemeinsame Testkonfiguration für das core-Modul."""
from unittest.mock import patch

import pytest
from django.core.management import call_command


@pytest.fixture(scope="session", autouse=True)
def _seed_db(django_db_setup, django_db_blocker) -> None:
    """Initialisiert einmalig die Testdatenbank."""
    with django_db_blocker.unblock():
        from django.contrib.auth.models import User
        from core.models import LLMConfig, Anlage4Config, Anlage4ParserConfig

        call_command("seed_initial_data", verbosity=0)
        LLMConfig.objects.get_or_create()
        Anlage4Config.objects.get_or_create()
        Anlage4ParserConfig.objects.get_or_create()
        if not User.objects.filter(username="baseuser").exists():
            User.objects.create_user("baseuser", password="pass")
        # Sicherstellen, dass der Superuser aus dem Seed-Skript
        # ein bekanntes Passwort für die Tests besitzt.
        superuser = User.objects.get(username="frank")
        superuser.set_password("pass")
        superuser.save()


@pytest.fixture
def user(db) -> "User":
    """Gibt den Basisbenutzer zurück."""
    from django.contrib.auth.models import User

    return User.objects.get(username="baseuser")


@pytest.fixture
def superuser(db) -> "User":
    """Gibt den Basis-Superuser zurück."""
    from django.contrib.auth.models import User

    return User.objects.get(username="frank")


@pytest.fixture(autouse=True)
def mock_llm_api_calls():
    """Ersetzt externe LLM-Aufrufe durch statische Antworten."""
    with (
        patch("core.llm_utils.query_llm", return_value="Mock-Antwort"),
        patch("core.llm_utils.query_llm_with_images", return_value="Mock-Antwort"),
        patch("core.llm_tasks.query_llm", return_value="Mock-Antwort"),
        patch("google.generativeai.configure"),
        patch("google.generativeai.list_models", return_value=[]),
    ):
        yield
