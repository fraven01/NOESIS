from rich.console import Console
from rich.markdown import Markdown

_console = Console()


def print_markdown(text: str) -> None:
    """Gibt Markdown-Text formatiert auf der Konsole aus."""
    _console.print(Markdown(text))
