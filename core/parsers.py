from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from .models import BVProjectFile, AntwortErkennungsRegel
from .docx_utils import parse_anlage2_table
from .text_parser import extract_function_segments, apply_rules

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


class ExactParser(AbstractParser):
    """Parser mit exakten Satzregeln."""

    name = "exact"

    def parse(self, project_file: BVProjectFile) -> list[dict[str, object]]:
        """Parst das Dokument anhand exakter Regeln."""

        text = project_file.text_content or ""
        segments = extract_function_segments(text)
        rules = list(AntwortErkennungsRegel.objects.all())

        results: dict[str, dict[str, object]] = {}
        order: list[str] = []

        for func_name, text_part in segments:
            if ":" in func_name:
                main_name = func_name.split(":", 1)[0]
                main_entry = results.get(main_name)
                if not main_entry or main_entry.get("technisch_verfuegbar", {}).get("value") is not True:
                    continue

            entry = results.setdefault(func_name, {"funktion": func_name})
            if func_name not in order:
                order.append(func_name)

            line_entry: dict[str, object] = {}
            apply_rules(line_entry, text_part, rules, func_name=func_name)
            for key, value in line_entry.items():
                entry[key] = value

        return [results[k] for k in order]

