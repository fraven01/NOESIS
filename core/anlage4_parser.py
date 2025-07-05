import re
import logging
from pathlib import Path
from typing import List

from docx import Document

from .models import BVProjectFile, Anlage4Config, Anlage4ParserConfig
from thefuzz import fuzz

logger = logging.getLogger("anlage4_debug")


def parse_anlage4(project_file: BVProjectFile) -> List[str]:
    """Parst Anlage 4 anhand der Konfiguration."""
    logger.info("parse_anlage4 gestartet für Datei %s", project_file.pk)
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
                headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
                logger.debug(
                    "Vergleiche Tabellen-Header %s mit Konfig %s", headers, columns
                )
                match_cols = [i for i, h in enumerate(headers) if h in columns]
                if not match_cols:
                    continue
                structure = "table detected"
                idx = match_cols[0]
                logger.debug(
                    "Nutze Spalte %s (%s)", idx, headers[idx]
                )
                for row in table.rows[1:]:
                    val = row.cells[idx].text.strip()
                    if val:
                        logger.debug("Gefundener Tabellenwert: %s", val)
                        items.append(val)
                if items:
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
                headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
                match_cols = [i for i, h in enumerate(headers) if h in columns]
                if not match_cols:
                    continue
                idx = match_cols[0]
                items = []
                for row in table.rows[1:]:
                    val = row.cells[idx].text.strip()
                    if val:
                        items.append(val)
                if items:
                    logger.debug("Tabelle erkannt - %s Items", len(items))
                    return items
        except Exception:  # pragma: no cover - ungültige Datei
            logger.error("Anlage4Parser Dual Fehler", exc_info=True)

    text = project_file.text_content or ""
    logger.debug("Rohtext f\u00fcr Dual-Parser (%s Zeichen): %s", len(text), text)
    blocks: list[str] = []
    current: list[str] = []
    name_keys = [r["keyword"] for r in rules if r.get("field") == "name_der_auswertung"]
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
