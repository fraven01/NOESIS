import re
import logging
from pathlib import Path
from typing import List

from docx import Document

from .models import BVProjectFile, Anlage4Config

logger = logging.getLogger(__name__)


def parse_anlage4(project_file: BVProjectFile) -> List[str]:
    """Parst Anlage 4 anhand der Konfiguration."""
    cfg = project_file.anlage4_config or Anlage4Config.objects.first()
    columns = [c.lower() for c in (cfg.table_columns if cfg else [])]
    neg_patterns = [re.compile(p, re.I) for p in (cfg.negative_patterns if cfg else [])]
    patterns = [re.compile(p, re.I) for p in (cfg.regex_patterns if cfg else [])]

    text = project_file.text_content or ""
    for pat in neg_patterns:
        if pat.search(text):
            return []

    items: List[str] = []

    path = Path(project_file.upload.path)
    if path.exists() and path.suffix.lower() == ".docx":
        try:
            doc = Document(str(path))
            for table in doc.tables:
                headers = [cell.text.strip().lower() for cell in table.rows[0].cells]
                match_cols = [i for i, h in enumerate(headers) if h in columns]
                if not match_cols:
                    continue
                idx = match_cols[0]
                for row in table.rows[1:]:
                    val = row.cells[idx].text.strip()
                    if val:
                        items.append(val)
                if items:
                    return items
        except Exception as exc:  # pragma: no cover - ungültige Datei
            logger.error("Anlage4Parser Fehler: %s", exc)

    for pat in patterns:
        items.extend(pat.findall(text))

    return items
