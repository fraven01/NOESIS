# AGENTS.md

## Zweck
NOESIS unterstützt Betriebsräte bei der Erstellung und Bewertung von Betriebsvereinbarungen. Fokus: Transparente Projektverwaltung, KI‑gestützte Analysen und Audio‑gestützte Dokumentation.

## Commit-Richtlinien
- Präfixe: `feat:`, `fix:`, `docs:`, `chore:`, …
- Erste Zeile: kurze Zusammenfassung, dann Leerzeile und optional detaillierte Beschreibung.

## Stil & Code
- Python nach PEP8, Kommentare/Docstrings auf Deutsch, wichtige Funktionen mit Typ-Hints.
- Templates folgen dem vorhandenen Tailwind‑Stil; Farbkontraste gemäß WCAG 2.1.

## Tests & Pre-Commit
Vor jedem Commit müssen lokal bestanden sein:
```bash
python manage.py makemigrations --check
pytest -q
```

`pre-commit` (siehe `.pre-commit-config.yaml`) führt diese Checks automatisch aus. Notfalls `git commit --no-verify` verwenden.

## Architekturüberblick

* **Backend**: Django 5.x
* **Asynchrone Tasks**: `django-q2` (läuft als `qcluster`)
* **Dokumentexport**: Pandoc (`markdown_placeholder.py`)
* **LLM-Integration**: Langfuse SDK 3.3.1, Konfiguration über Admin‐Bereich
* **Navigation**: Kontextprozessoren `user_navigation`, `admin_navigation`
* **TalkDiary**: Audioaufnahme mit optionaler OBS‑Steuerung und Whisper-Transkription
* **Vision-Modell**: Konfigurierbar unter `/projects-admin/vision/`

## Management-Befehle

* `seed_initial_data`: Standarddaten einspielen
* `export_configs` / `import_configs`: Export/Import der Konfiguration
* `clear_async_tasks [--queued|--failed]`: Aufräumen der Django-Q-Queues
