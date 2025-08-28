"""
Führt vor dem Commit grundlegende Checks und Tests aus:

- Prüft, ob neue Migrationen nötig wären (makemigrations --check)
- Führt pytest aus (Konfiguration über pytest.ini)

Exit-Code ist ungleich 0, wenn einer der Schritte fehlschlägt.
"""

from __future__ import annotations

import subprocess
import sys


def run(cmd: list[str]) -> int:
    print("$", " ".join(cmd))
    proc = subprocess.run(cmd)
    return proc.returncode


def main() -> int:
    # 1) Django-Migrations-Check (verhindert unbeabsichtigte Schema-Änderungen)
    code = run([sys.executable, "manage.py", "makemigrations", "--check"])
    if code != 0:
        print("Fehler: makemigrations --check meldet ausstehende Änderungen.")
        return code

    # 2) Tests ausführen
    # Nutzen von subprocess statt pytest.main für robustes Verhalten in Hooks
    # Schnelllauf in Hooks: e2e/selenium/slow ausschließen
    code = run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-m",
            "not e2e and not selenium and not slow",
        ]
    )
    if code != 0:
        print("Fehler: Pytest ist fehlgeschlagen.")
        return code

    print("OK: Checks und Tests erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
