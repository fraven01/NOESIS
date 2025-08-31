import pytest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ...parser_manager import parser_manager

pytestmark = pytest.mark.unit


class ParserManagerTests:
    """Tests für den ParserManager."""

    def _pf(self, **kwargs) -> SimpleNamespace:
        """Hilfsfunktion zum Erstellen eines einfachen Projektfiles."""
        defaults = {
            "pk": 1,
            "upload": SimpleNamespace(name="file.docx"),
            "parser_mode": None,
            "parser_order": None,
            "text_content": "",
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_unknown_parser_returns_empty_list(self) -> None:
        """Ein unbekannter Parser liefert eine leere Liste."""
        pf = self._pf(parser_mode="table_only")
        with patch.object(parser_manager, "_parsers", {}), patch(
            "core.parser_manager.Anlage2Config.get_instance",
            return_value=SimpleNamespace(parser_mode="auto", parser_order=["exact"]),
        ):
            result = parser_manager.parse_anlage2(pf)
        assert result == []

    def test_text_only_uses_text_parser(self) -> None:
        """Der Modus 'text_only' nutzt den Textparser."""
        pf = self._pf(parser_mode="text_only")
        parser_mock = Mock()
        parser_mock.parse.return_value = [{"funktion": "Test"}]
        with patch.object(
            parser_manager, "_parsers", {"text": parser_mock}
        ), patch(
            "core.parser_manager.Anlage2Config.get_instance",
            return_value=SimpleNamespace(parser_mode="auto", parser_order=["exact"]),
        ):
            result = parser_manager.parse_anlage2(pf)
        parser_mock.parse.assert_called_once_with(pf)
        assert result == [{"funktion": "Test"}]

    def test_parser_exception_results_in_empty_list(self) -> None:
        """Wirft der Parser eine Exception, wird eine leere Liste zurückgegeben."""
        pf = self._pf(parser_mode="text_only")
        parser_mock = Mock()
        parser_mock.parse.side_effect = ValueError("boom")
        with patch.object(
            parser_manager, "_parsers", {"text": parser_mock}
        ), patch(
            "core.parser_manager.Anlage2Config.get_instance",
            return_value=SimpleNamespace(parser_mode="auto", parser_order=["exact"]),
        ):
            result = parser_manager.parse_anlage2(pf)
        parser_mock.parse.assert_called_once_with(pf)
        assert result == []
