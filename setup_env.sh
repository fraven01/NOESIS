#!/bin/bash
# Erstellt eine virtuelle Umgebung und installiert Abh\u00e4ngigkeiten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Entwicklungswerkzeuge installieren
pip install -r requirements-dev.txt

# Optional Selenium-Tests aktivieren
read -p "Sollen Selenium-Tests ausgeführt werden? (j/n) " run_selenium
if [[ $run_selenium == "j" || $run_selenium == "J" ]]; then
    # Variable für aktuelle Sitzung setzen
    export NOESIS_RUN_SELENIUM=1
    # Variable dauerhaft im Aktivierungsskript hinterlegen
    if ! grep -q "NOESIS_RUN_SELENIUM" venv/bin/activate; then
        echo "export NOESIS_RUN_SELENIUM=1" >> venv/bin/activate
    fi
    echo "NOESIS_RUN_SELENIUM=1 in venv/bin/activate gesetzt."
fi

# Systemabhängigkeiten installieren (pandoc wird für DOCX-Exporte benötigt)
if command -v apt-get >/dev/null; then
    sudo apt-get update
    sudo apt-get install -y pandoc
fi

