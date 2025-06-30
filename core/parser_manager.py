from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, List, Type

from .models import BVProjectFile, Anlage2Config
from .docx_utils import parse_anlage2_table

logger = logging.getLogger(__name__)


class AbstractParser(ABC):
    """Abstrakte Basisklasse für Parser."""

    name: str

    @abstractmethod
    def parse(self, project_file: BVProjectFile) -> list[dict[str, object]]:
        """Parst eine Projektdatei."""
        raise NotImplementedError


class TableParser(AbstractParser):
    """Parser für strukturierte Tabelle."""

    name = "table"

    def parse(self, project_file: BVProjectFile) -> list[dict[str, object]]:
        return parse_anlage2_table(Path(project_file.upload.path))


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
            if result:
                return result
        return []


parser_manager = ParserManager()
parser_manager.register(TableParser)
