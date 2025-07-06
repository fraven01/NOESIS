class GenerativeModel:
    def __init__(self, *args: object, **kwargs: object) -> None:
        """Initialisiert das Dummy-Modell."""

        pass

    def generate_content(self, *args: object, **kwargs: object):
        """Erzeugt eine leere Antwort als Platzhalter."""
        class R:
            text = ""
        return R()


def configure(api_key: str = "") -> None:
    """Konfiguriert das Stub-Modul."""

    pass


def list_models() -> list[object]:
    """Gibt eine Liste verf\u00fcgbarer Modelle zur\u00fcck."""

    class M:
        def __init__(self, name: str) -> None:
            self.name = name

    return [M("stub-model")]
