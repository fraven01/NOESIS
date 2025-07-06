"""Leichtgewichtiger Whisper-Ersatz f\u00fcr Testl\u00e4ufe."""


class DummyModel:
    """Imitiert ein Whisper-Modell."""
    def transcribe(self, *args, **kwargs):
        return {"text": ""}

def load_model(name: str, device: str | None = None) -> DummyModel:
    """Gibt ein Dummy-Whisper-Modell zur\u00fcck."""

    return DummyModel()
