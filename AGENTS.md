# AGENTS.md

## Zweck der Webanwendung
- Die Anwendung "NOESIS" ist eine spezialisierte, digitale Assistenz zur Unterstützung von Betriebsräten. Ihr Hauptzweck ist die Vereinfachung, Strukturierung und Nachvollziehbarkeit von Prozessen rund um Betriebsvereinbarungen (BV).

Kernfunktionen:

Strukturiertes Projektmanagement:

Verwaltung von BV-Projekten mit konfigurierbaren Status-Definitionen.
Slot-basiertes Management der 6 Standard-Anlagen, was eine klare Übersicht über fehlende oder vorhandene Dokumente gibt.
Revisionssichere Speicherung von Anlagedokumenten, bei der frühere Versionen erhalten bleiben.
KI-gestützte Dokumenten-Analyse:

Ein duales Parser-System für Anlage 2, das sowohl strukturierte Tabellen als auch unstrukturierte Textdokumente verarbeiten kann.
Ein vollständig Alias-gesteuertes Parsersystem, das über den Admin-Bereich konfiguriert werden kann, um sich an verschiedene Formulierungen anzupassen.
Mehrstufige, asynchrone KI-Prüfungen für Software-Komponenten, die Folgendes umfassen:
Ein Initial-Check, ob eine Software dem System bekannt ist.
Eine detaillierte Beschreibung der Software und ihrer Funktionen.
Eine gezielte Prüfung auf das Vorhandensein von mitbestimmungspflichtigen Funktionen (Anlage 2).
Eine konditionale Prüfung auf KI-Beteiligung bei diesen Funktionen.
Generierung von Gutachten, sowohl für einzelne Software-Komponenten als auch als zusammenfassender Gesamtbericht.
Konfigurierbarkeit und Kontrolle:

Ein benutzerdefinierter Admin-Bereich ermöglicht die vollständige Konfiguration der Systemlogik ohne Code-Änderungen.
LLM-Rollen und Prompts können zentral definiert und verwaltet werden, um den Antwortstil und die "Persönlichkeit" der KI zu steuern.
Workflow "TalkDiary":

Aufnahme und KI-gestützte Transkription von Audio-Gesprächen zur einfachen Protokollierung.

## Commit-Richtlinien
- Verwende Präfixe wie `feat:`, `fix:` oder `docs:` in Commit-Botschaften.
- Erste Zeile enthält eine kurze Zusammenfassung, dann eine Leerzeile und ggf. eine detaillierte Beschreibung.

## Stil und Code
- Python-Code nach PEP8.
- Kommentare und Docstrings auf Deutsch.
- Wichtige Funktionen mit Typ-Hints versehen.

## Technische Architektur & Abhängigkeiten
Backend: Django 5.x
Asynchrone Tasks: django-q2 wird für alle langlaufenden Prozesse (LLM-Anfragen, Analysen) verwendet. Dies erfordert einen laufenden qcluster-Prozess.
Dokumenten-Export: Die Konvertierung von Markdown zu .docx erfordert die System-Abhängigkeit pandoc.
Datenbank: SQLite für die Entwicklung, für den Produktivbetrieb ist PostgreSQL empfohlen.


## Projektstruktur
core/: Zentrale Django-App mit Modellen, Views, Formularen und den meisten Geschäftslogiken.
migrations/: Django-Migrationsdateien, inklusive Daten-Migrationen für Standard-Prompts und -Rollen.
Nach `python manage.py migrate` füllt `python manage.py seed_initial_data` die Datenbank mit Standarddaten.
templatetags/: Eigene Template-Erweiterungen (z.B. für Markdown-Rendering).
management/commands/: Eigene manage.py-Befehle.
noesis/: Projekteinstellungen und URL-Konfiguration.
static/: Statische Dateien; css/ enthält globale und admin-spezifische Stylesheets.
templates/: HTML-Vorlagen, inklusive eines admin-Unterordners zum Überschreiben der Standard-Admin-Ansicht.
llm-debug.log: Dediziertes Logfile für alle LLM-Prompts und -Antworten.
Procfile: Definiert die Prozesse (web, worker) für den Start mit honcho.

## Admin-Bereiche

- `/projects-admin/` – Projekt-Admin für alle projektbezogenen Modelle und
  Einstellungen (z.B. Funktionskatalog, Parser-Regeln).
- `/admin/` – System-Admin (das reguläre Django-Admin) für globale
  Konfiguration wie Benutzer und Gruppen.


-   **Implementierung von CRUD-Ansichten:** Entwicklung von Listen-, Erstellungs-, Bearbeitungs- und Löschansichten für verschiedene Modelle.

-   **Implementierung einer robusten Import/Export-Funktion:** Entwicklung einer idempotenten Import- und Exportlogik für die gesamte Anwendungskonfiguration, inklusive der Handhabung von Many-to-Many-Beziehungen und der Integration in die Admin-Oberfläche.
-   **Analyse und Refactoring:** Bewertung von Code-Alternativen (Patches) und Umsetzung der besten Lösung.

## Tests und Checks
- Vor jedem Commit `python manage.py makemigrations --check` ausführen.
- Ebenfalls vor jedem Commit `pytest` ausführen (dank automatischer LLM-Mocking-Fixture ohne echte API-Anfragen).

