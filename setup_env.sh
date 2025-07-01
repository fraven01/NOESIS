#!/bin/bash
# Erstellt eine virtuelle Umgebung und installiert Abh\u00e4ngigkeiten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Entwicklungswerkzeuge installieren
pip install -r requirements-dev.txt

