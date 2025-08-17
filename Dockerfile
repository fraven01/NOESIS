# Schritt 1: Ein schlankes Python-Basis-Image verwenden
FROM python:3.11-slim

# Schritt 2: Umgebungsvariablen für einen stabilen Betrieb setzen
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV PORT 8080

# Schritt 3: Systemabhängigkeiten installieren
# pandoc: für den DOCX-Export
# nodejs & npm: für den TailwindCSS-Build
RUN apt-get update && apt-get install -y pandoc nodejs npm --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Schritt 4: Das Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Schritt 5: Python-Abhängigkeiten installieren
# Zuerst nur die Anforderungsdatei kopieren, um den Docker-Cache optimal zu nutzen
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Schritt 6: Den gesamten Anwendungscode in den Container kopieren
COPY . .
RUN ls -la /app

# Einstiegspunkt-Skript kopieren und ausführbar machen
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Schritt 7: Frontend-Abhängigkeiten installieren und CSS bauen
# Wechseln in das Verzeichnis, in dem sich die package.json befindet
WORKDIR /app/theme/static_src
RUN npm install

# Zurück zum Hauptverzeichnis für die Django-Befehle
WORKDIR /app

# TailwindCSS kompilieren
RUN python manage.py tailwind build

# Schritt 8: Statische Dateien für die Produktion sammeln
# Django sammelt alle statischen Dateien (inkl. dem kompilierten CSS) an einem Ort
RUN python manage.py collectstatic --no-input

# Schritt 9: Einstiegspunkt und Standardbefehl definieren
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["web"]
