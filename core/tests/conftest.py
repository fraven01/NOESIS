"""Gemeinsame Testkonfiguration für das core-Modul."""

from unittest.mock import patch

import pytest


@pytest.fixture(scope="session", autouse=True)
def _seed_db(django_db_setup, django_db_blocker) -> None:
    """Initialisiert einmalig die Testdatenbank."""
    from django.contrib.auth.models import User
    from .test_general import seed_test_data

    with django_db_blocker.unblock():
        seed_test_data()
        User.objects.create_user("baseuser", password="pass")
        User.objects.create_superuser(
            "basesuper", "admin@example.com", password="pass"
        )


@pytest.fixture(autouse=True)
def mock_llm_api_calls():
    """Ersetzt externe LLM-Aufrufe durch statische Antworten."""
    with (
        patch("core.llm_utils.query_llm", return_value="Mock-Antwort"),
        patch("core.llm_utils.query_llm_with_images", return_value="Mock-Antwort"),
        patch("core.llm_tasks.query_llm", return_value="Mock-Antwort"),
        patch("core.llm_tasks.query_llm_with_images", return_value="Mock-Antwort"),
        patch("google.generativeai.configure"),
        patch("google.generativeai.list_models", return_value=[]),
    ):
        yield
