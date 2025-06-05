# NOESIS

Dieses Projekt ist eine Django-Anwendung zur Verwaltung und Analyse von Audio-Aufnahmen und Transkripten.

## Installation

1. Installiere Python 3.11 und `pip`.
2. Erstelle und aktiviere eine virtuelle Umgebung:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Installiere die Abhängigkeiten:
   ```bash
   pip install -r requirements.txt
   # Für Entwicklungs- und Testwerkzeuge:
   pip install -r requirements-dev.txt
   ```

## Tests und Checks

Vor jedem Commit müssen laut `AGENTS.md` folgende Befehle erfolgreich laufen:

```bash
python manage.py makemigrations --check
python manage.py test
```
