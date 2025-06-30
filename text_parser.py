#!/usr/bin/env python
"""Kommandozeilentool für den Text-Parser von Anlage 2."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "noesis.settings")
django.setup()

from core.docx_utils import extract_text
from core.llm_tasks import parse_anlage2_text


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python text_parser.py <file>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    if path.suffix.lower() == ".docx":
        text = extract_text(path)
    else:
        text = path.read_text(encoding="utf-8")

    results = parse_anlage2_text(text)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
