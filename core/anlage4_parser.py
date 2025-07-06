import re
import logging
from pathlib import Path
from typing import List

from docx import Document

from .models import BVProjectFile, Anlage4Config, Anlage4ParserConfig
from thefuzz import fuzz

logger = logging.getLogger("anlage4_debug")


def parse_anlage4(
    project_file: BVProjectFile, cfg: Anlage4Config | None = None
) -> List[str]:
    """Parst Anlage 4 anhand der Konfiguration."""
    logger.info("parse_anlage4 gestartet für Datei %s", project_file.pk)
    if cfg is None:
        cfg = project_file.anlage4_config or Anlage4Config.objects.first()
    columns = [c.lower() for c in (cfg.table_columns if cfg else [])]
    neg_patterns = [re.compile(p, re.I) for p in (cfg.negative_patterns if cfg else [])]
    patterns = [re.compile(p, re.I) for p in (cfg.regex_patterns if cfg else [])]

    logger.debug(
        "Konfiguration: columns=%s, regex_patterns=%s, negative_patterns=%s",
        columns,
        [p.pattern for p in patterns],
        [p.pattern for p in neg_patterns],
    )

    text = project_file.text_content or ""
    logger.debug("Rohtext der Anlage4 (%s Zeichen): %s", len(text), text)

    for pat in neg_patterns:
        logger.debug("Pr\u00fcfe negatives Muster '%s'", pat.pattern)
        match = pat.search(text)
        if match:
            logger.error(
                "Negative pattern erkannt: %s -> %r", pat.pattern, match.group(0)
            )
            return []

    items: List[str] = []
    structure: str | None = None

    path = Path(project_file.upload.path)
    if path.exists() and path.suffix.lower() == ".docx":
        try:
            doc = Document(str(path))
            for table in doc.tables:
                logger.debug("Prüfe Tabelle mit %s Zeilen", len(table.rows))
                found = False
                for row in table.rows:
                    if len(row.cells) < 2:
                        continue
                    key = row.cells[0].text.strip().lower()
                    if key in columns:
                        value = row.cells[1].text.strip()
                        if value:
                            if not found:
                                structure = "table detected"
                                found = True
                            logger.debug("Gefundenes Paar %s: %s", key, value)
                            items.append(value)
                if found and items:
                    logger.debug("%s - %s items", structure, len(items))
                    return items
        except Exception as exc:  # pragma: no cover - ungültige Datei
            logger.error("Anlage4Parser Fehler", exc_info=True)
            structure = structure or ("free text found" if text.strip() else "empty document")
    
    for pat in patterns:
        logger.debug("Suche Muster '%s'", pat.pattern)
        matches = pat.findall(text)
        logger.debug("Gefundene Treffer für '%s': %s", pat.pattern, matches)
        for m in matches:
            logger.debug("Treffer hinzugefügt: %s", m)
            items.append(m)

    if structure is None:
        structure = "free text found" if text.strip() else "empty document"
    logger.debug("%s - %s items", structure, len(items))
    for idx, item in enumerate(items):
        logger.debug("Item %s: %s", idx, item)
    logger.info(
        "parse_anlage4 beendet für Datei %s mit %s Zwecken",
        project_file.pk,
        len(items),
    )
    return items


def parse_anlage4_dual(project_file: BVProjectFile) -> List[str]:
    """Parst Anlage 4 mit Dual-Strategie."""

    logger.info("parse_anlage4_dual gestartet für Datei %s", project_file.pk)
    cfg = project_file.anlage4_parser_config or Anlage4ParserConfig.objects.first()
    columns = [c.lower() for c in (cfg.table_columns if cfg else [])]
    rules = cfg.text_rules if cfg else []

    path = Path(project_file.upload.path)
    if path.exists() and path.suffix.lower() == ".docx" and columns:
        try:
            doc = Document(str(path))
            for table in doc.tables:
                logger.debug("Dual Parser prüft Tabelle mit %s Zeilen", len(table.rows))
                items = []
                for row in table.rows:
                    if len(row.cells) < 2:
                        continue
                    key = row.cells[0].text.strip().lower()
                    if key in columns:
                        value = row.cells[1].text.strip()
                        if value:
                            logger.debug("Dual Parser gefundenes Paar %s: %s", key, value)
                            items.append(value)
                if items:
                    logger.debug("Tabelle erkannt - %s Items", len(items))
                    return items
        except Exception:  # pragma: no cover - ungültige Datei
            logger.error("Anlage4Parser Dual Fehler", exc_info=True)

    text = project_file.text_content or ""
    logger.debug("Rohtext f\u00fcr Dual-Parser (%s Zeichen): %s", len(text), text)
    blocks: list[str] = []
    current: list[str] = []
    name_keys = [
        r["keyword"]
        for r in rules
        if isinstance(r, dict) and r.get("field") == "name_der_auswertung"
    ]
    for r in rules:
        if not isinstance(r, dict):
            logger.warning("Ungültige Regel: %r", r)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(fuzz.partial_ratio(k.lower(), stripped.lower()) >= 80 for k in name_keys):
            if current:
                logger.debug("Neuer Block gefunden, aktueller Block hat %s Zeilen", len(current))
                blocks.append(" \n".join(current))
                current = []
        current.append(stripped)
        logger.debug("Zeile hinzugefügt: %s", stripped)
    if current:
        logger.debug("Finaler Block hat %s Zeilen", len(current))
        blocks.append(" \n".join(current))
    logger.debug("Textparser gefunden %s Blöcke", len(blocks))
    return blocks
