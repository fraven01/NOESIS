"""Tests für die Hilfsfunktionen rund um das LLM."""

from types import SimpleNamespace

import pytest

from core import llm_utils, models

pytestmark = pytest.mark.unit


class DummyResponse:
    """Einfache Antwort mit nur den benötigten Attributen."""

    text = "ok"
    candidates = []
    prompt_feedback = None
    usage_metadata = SimpleNamespace(
        prompt_token_count=1, candidates_token_count=1, total_token_count=2
    )


def _setup_base(monkeypatch, settings):
    """Gemeinsame Grundeinstellungen und Patches setzen."""
    import importlib

    importlib.reload(llm_utils)

    settings.GOOGLE_API_KEY = "test-key"
    settings.OPENAI_API_KEY = ""
    monkeypatch.setattr(
        models.LLMConfig, "get_default", classmethod(lambda cls, _: "gemini-pro"),
    )
    monkeypatch.setattr(llm_utils.genai, "configure", lambda api_key: None)


def test_falls_back_to_default_role(monkeypatch, settings):
    """Wenn keine Rolle gesetzt ist, wird die Standardrolle genutzt."""

    captured = {}

    def filter_stub(**kwargs):
        class _QS:
            def first(self):
                return SimpleNamespace(role_prompt="DEFAULT")

        return _QS()

    monkeypatch.setattr(models.LLMRole.objects, "filter", filter_stub)

    class DummyModel:
        def __init__(self, name):
            captured["model"] = name

        def generate_content(self, prompt, generation_config):
            captured["prompt"] = prompt
            captured["generation_config"] = generation_config
            return DummyResponse()

    _setup_base(monkeypatch, settings)
    monkeypatch.setattr(llm_utils.genai, "GenerativeModel", DummyModel)

    prompt_obj = SimpleNamespace(name="p", text="Aufgabe", role=None, use_system_role=True)

    result = llm_utils.query_llm(prompt_obj, context_data={}, max_output_tokens=7)

    assert result == "ok"
    assert captured["prompt"].startswith("DEFAULT\n\n---\n\nAufgabe")


def test_respects_max_output_tokens(monkeypatch, settings):
    """Der Parameter max_output_tokens wird an das Modell weitergegeben."""

    captured = {}

    class DummyModel:
        def __init__(self, name):
            pass

        def generate_content(self, prompt, generation_config):
            captured.update(generation_config)
            return DummyResponse()

    _setup_base(monkeypatch, settings)
    monkeypatch.setattr(llm_utils.genai, "GenerativeModel", DummyModel)

    prompt_obj = SimpleNamespace(name="p", text="Aufgabe", role=None, use_system_role=False)

    llm_utils.query_llm(prompt_obj, context_data={}, max_output_tokens=5)

    assert captured["max_output_tokens"] == 5


def test_google_api_call_error(monkeypatch, settings):
    """Ein GoogleAPICallError wird unverändert weitergegeben."""
    _setup_base(monkeypatch, settings)

    error = llm_utils.g_exceptions.GoogleAPICallError("boom")

    class DummyModel:
        def __init__(self, name):
            pass

        def generate_content(self, prompt, generation_config):
            raise error

    monkeypatch.setattr(llm_utils.genai, "GenerativeModel", DummyModel)

    prompt_obj = SimpleNamespace(name="p", text="Aufgabe", role=None, use_system_role=False)

    with pytest.raises(llm_utils.g_exceptions.GoogleAPICallError):
        llm_utils.query_llm(prompt_obj, context_data={})
