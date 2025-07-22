from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from .models import BVProjectFile, AntwortErkennungsRegel
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


class ExactParser(AbstractParser):
    """Parser mit exakten Satzregeln."""

    name = "exact"

    def parse(self, project_file: BVProjectFile) -> list[dict[str, object]]:
        """Parst das Dokument anhand exakter Regeln."""

        results: list[dict[str, object]] = []
        text = (project_file.text_content or "").lower()
        for rule in AntwortErkennungsRegel.objects.all().order_by("prioritaet"):
            if rule.erkennungs_phrase.lower() in text:
                actions = rule.actions_json or []
                if isinstance(actions, dict):
                    actions = [
                        {"field": k, "value": v} for k, v in actions.items()
                    ]
                entry: dict[str, object] = {"funktion": rule.regel_name}
                for act in actions:
                    field = act.get("field")
                    if not field:
                        continue
                    entry[field] = {"value": bool(act.get("value")), "note": None}
                results.append(entry)
        return results

