# NOESIS

NOESIS ist eine Django‑basierte Assistenzplattform für Betriebsräte. Sie unterstützt den gesamten Lebenszyklus von Betriebsvereinbarungen (BV) und vereint Projektverwaltung, KI‑gestützte Dokumentanalyse sowie Audio‑Notizen („TalkDiary“).

## Kernfunktionen
- **Projekt- und Dokumentenmanagement**: Anlage von BV‑Projekten, revisionssichere Versionierung von Anlagen und Slot‑basiertes Dokumenten‑Tracking.  
- **KI-Analyse**: Strukturierte/unkommentierte Parser für Anlagen, LLM‑gestützte Prüfung von Software‑Funktionen inkl. KI‑Beteiligung.  
- **Audio & TalkDiary**: Aufnahme, Transkription (Whisper) und Ablage von Gesprächsnotizen; optional Steuerung von OBS.  
- **Dynamische Navigation**: Sidebar aus `Area`‑/`Tile`‑Modellen, Admin‑Bereiche unter `/projects-admin/` und `/admin/`.  
- **Export**: Markdown‑zu‑DOCX via `pandoc`.

## Installation
1. **Python 3.11** installieren und virtuelle Umgebung anlegen:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. **Abhängigkeiten**:

   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # für Entwicklung/Tests
   ```
3. **Systempakete**: `pandoc` und ggf. weitere Bibliotheken installieren.
4. **Assets bauen**:

   ```bash
   npm --prefix theme/static_src run build
   ```

## Entwicklung

* `.env.example` kopieren und anpassen (`DJANGO_SECRET_KEY`, API‑Keys etc.).
* Datenbank migrieren:

  ```bash
  python manage.py migrate
  python manage.py seed_initial_data
  ```

## Tests & Qualitätssicherung

* Tests laufen mit:

  ```bash
  python manage.py makemigrations --check
  pytest -q
  ```
* `pre-commit` einrichten:

  ```bash
  pre-commit install
  ```

  (führt die obigen Checks automatisch aus)

## Admin- und Nutzeroberfläche

* `/projects-admin/`: Projekt‑Admin für Konfigurationen und Parser-Regeln
* `/admin/`: klassisches Django‑Admin für Benutzer/Gruppen
* Sidebar und Breadcrumbs werden per Kontextprozessor generiert (`core/context_processors.py`).

## Weitere Informationen

* Ausführliche Spezifikation des Anlage‑2‑Workflows in `docs/anlage2_workflow_final.md`.
* Für Vision‑Modelle `OPENAI_API_KEY` bzw. `GOOGLE_API_KEY` setzen.

