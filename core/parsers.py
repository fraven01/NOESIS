from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from .models import BVProjectFile
from .docx_utils import parse_anlage2_table

logger = logging.getLogger(__name__)


class AbstractParser(ABC):
    """Abstrakte Basisklasse f\u00fcr Parser."""

    name: str

    @abstractmethod
    def parse(self, project_file: BVProjectFile) -> list[dict[str, object]]:
        """Parst eine Projektdatei."""
        raise NotImplementedError


class TableParser(AbstractParser):
    """Parser f\u00fcr strukturierte Tabelle."""

    name = "table"

    def parse(self, project_file: BVProjectFile) -> list[dict[str, object]]:
        return parse_anlage2_table(Path(project_file.upload.path))

