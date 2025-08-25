#!/bin/bash
# Erstellt eine virtuelle Umgebung und installiert Abh\u00e4ngigkeiten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Entwicklungswerkzeuge installieren
pip install -r requirements-dev.txt

# Für zukünftige E2E-Tests kann die Umgebungsvariable
# NOESIS_RUN_SELENIUM=1 gesetzt werden.

# Systemabhängigkeiten installieren (pandoc wird für DOCX-Exporte benötigt)
if command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y pandoc
fi

