# AGENTS.md

## Zweck der Webanwendung
- Digitale, persönliche Assistenz zur Aufnahme und Transkription von Audio (Workflow "TalkDiary").
- Unterstützung des Betriebsrats bei der Beurteilung von Softwaresystemen gem. §87 Abs. 1 Nr. 6 BetrVG.
- Geplante Analyse- und Visualisierungsfunktionen für Transkripte und Systemdaten.
- Klare Trennung zwischen beruflichen und privaten Bereichen.

## Commit-Richtlinien
- Verwende Präfixe wie `feat:`, `fix:` oder `docs:` in Commit-Botschaften.
- Erste Zeile enthält eine kurze Zusammenfassung, dann eine Leerzeile und ggf. eine detaillierte Beschreibung.

## Stil und Code
- Python-Code nach PEP8.
- Kommentare und Docstrings auf Deutsch.
- Wichtige Funktionen mit Typ-Hints versehen.

## Projektstruktur
- `core/`: Zentrale Django-App mit Modellen, Views, Formularen und Hilfsfunktionen.
  - `migrations/`: Django-Migrationsdateien.
  - `templatetags/`: Eigene Template-Erweiterungen.
- `noesis/`: Projekteinstellungen und URL-Konfiguration.
- `static/`: Statische Dateien; `css/` enthält Stylesheets.
- `templates/`: HTML-Vorlagen.
- `media/`: Benutzerdateien wie Audio und Transkripte (sollte per `.gitignore` ausgeschlossen werden).
- `requirements.txt`: Python-Abhängigkeiten.
- `manage.py`: Verwaltungsbefehle für Django.

## Tests und Checks
- Vor jedem Commit `python manage.py makemigrations --check` ausführen.
- Mit `python manage.py test` die Test-Suite starten.
