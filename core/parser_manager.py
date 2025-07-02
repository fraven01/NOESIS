from __future__ import annotations

import logging
from typing import Dict, List, Type

from .models import BVProjectFile, Anlage2Config
from .parsers import AbstractParser, TableParser
from .text_parser import FuzzyTextParser

logger = logging.getLogger(__name__)


class ParserManager:
    """Verwaltet verfügbare Parser und ihre Auswahl."""

    def __init__(self) -> None:
        self._parsers: Dict[str, AbstractParser] = {}

    def register(self, parser_cls: Type[AbstractParser]) -> None:
        parser = parser_cls()
        self._parsers[parser.name] = parser
        logger.debug("Parser '%s' registriert", parser.name)

    def get(self, name: str) -> AbstractParser | None:
        return self._parsers.get(name)

    def available_names(self) -> List[str]:
        return list(self._parsers.keys())

    def parse_anlage2(self, project_file: BVProjectFile) -> list[dict[str, object]]:
        cfg = Anlage2Config.get_instance()
        parser_order = cfg.parser_order or ["table"]
        best_result: list[dict[str, object]] = []
        best_count = -1
        for name in parser_order:
            parser = self.get(name)
            if parser is None:
                logger.warning("Unbekannter Parser: %s", name)
                continue
            try:
                result = parser.parse(project_file)
            except Exception as exc:  # pragma: no cover - Fehlkonfiguration
                logger.error("Parser '%s' Fehler: %s", name, exc)
                result = []
            count = _count_technisch_true(result)
            if count > best_count:
                best_result = result
                best_count = count
        return best_result


def _count_technisch_true(data: list[dict[str, object]]) -> int:
    """Zählt Einträge mit technisch vorhandener Funktion."""
    count = 0
    for item in data:
        val = item.get("technisch_verfuegbar")
        if isinstance(val, dict):
            if val.get("value") is True:
                count += 1
        elif isinstance(val, str):
            if val.lower() == "ja":
                count += 1
        elif val is True:
            count += 1
    return count


parser_manager = ParserManager()
parser_manager.register(TableParser)
parser_manager.register(FuzzyTextParser)
