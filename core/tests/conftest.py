"""Gemeinsame Testkonfiguration für das core-Modul."""

from unittest.mock import patch

import pytest


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
