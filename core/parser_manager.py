from __future__ import annotations

import logging
from typing import Dict, List, Type

from .models import BVProjectFile, Anlage2Config
from .parsers import AbstractParser, TableParser, ExactParser

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
        """Führt die Parser gemäß Konfiguration aus."""

        cfg = Anlage2Config.get_instance()
        mode = project_file.parser_mode or cfg.parser_mode
        order = project_file.parser_order or cfg.parser_order or ["exact"]

        if mode == "table_only":
            return self._run_single("table", project_file)
        if mode == "exact_only":
            return self._run_single("exact", project_file)
        if mode == "text_only":
            candidates = [n for n in order if n in {"text", "exact"}]
            if not candidates:
                candidates = [n for n in ("text", "exact") if n in self._parsers]
        else:  # auto or unknown mode
            candidates = order

        for name in candidates:
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

    def _run_single(self, name: str, project_file: BVProjectFile) -> list[dict[str, object]]:
        """Hilfsfunktion, führt einen einzelnen Parser aus."""

        parser = self.get(name)
        if parser is None:
            logger.warning("Unbekannter Parser: %s", name)
            return []
        try:
            return parser.parse(project_file)
        except Exception as exc:  # pragma: no cover - Fehlkonfiguration
            logger.error("Parser '%s' Fehler: %s", name, exc)
            return []


parser_manager = ParserManager()
parser_manager.register(TableParser)
parser_manager.register(ExactParser)

