#!/usr/bin/env python3
"""Prüft Django-Templates auf ausreichenden Farbkontrast.

Das Skript rendert das angegebene Template mit den Django-Einstellungen
und führt anschließend Pa11y mit dem Axe-Runner aus, der mögliche
Barrierefreiheitsprobleme – darunter auch den Farbkontrast – meldet.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import django
from django.template.loader import render_to_string


def main() -> int:
    parser = argparse.ArgumentParser(description="Template rendern und Kontrast prüfen")
    parser.add_argument(
        "template",
        nargs="?",
        default="base.html",
        help="Pfad zum Django-Template, das geprüft werden soll",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "noesis.settings")
    os.environ.setdefault("DJANGO_SECRET_KEY", "dev-secret")
    django.setup()

    html = render_to_string(args.template)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    try:
        cmd = ["npx", "pa11y", "--runner", "axe", tmp_path]
        result = subprocess.run(cmd, check=False)
        return result.returncode
    finally:
        os.unlink(tmp_path)


if __name__ == "__main__":
    raise SystemExit(main())
