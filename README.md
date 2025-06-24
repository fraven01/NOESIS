# NOESIS

Dieses Projekt ist eine Django-Anwendung als persönlicher und personalisierter Agent.
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
   Diese Version nutzt **Django-Q2** (>=1.8.0) für Hintergrundprozesse.

## Tests und Checks

Vor jedem Commit müssen laut `AGENTS.md` folgende Befehle erfolgreich laufen:

```bash
python manage.py makemigrations --check
python manage.py test
```

## Logging

Alle Debug-Ausgaben des Projekts werden zusätzlich in `debug.log` im Projektverzeichnis gespeichert. Diese Datei ist über `.gitignore` vom Versionskontrollsystem ausgenommen.

## Datenbankmigrationen

Führe nach dem Einspielen neuer Code-Änderungen immer `python manage.py migrate` aus. Damit werden Datenbankanpassungen, wie etwa das Entfernen von Unique-Constraints, wirksam. Mit

```bash
python manage.py showmigrations
```

lässt sich prüfen, ob alle Migrationen angewendet wurden.

## Hintergrund-Tasks

Für langlaufende Aktionen nutzt die Anwendung **Django‑Q2**. Neben dem
``runserver``-Prozess muss deshalb ein weiterer Worker laufen:

```bash
python manage.py qcluster
```

Ohne diesen Prozess werden keine Hintergrundaufgaben ausgeführt.

## Markdown-Verarbeitung

Alle Antworten der LLMs enthalten Markdown. Im Web werden sie mit
`markdown.markdown()` zu HTML umgewandelt. In der Kommandozeile übernimmt
`rich` die Darstellung über `rich.markdown.Markdown`.

### Gutachten verwalten

1. Klicke in der Projekt-Detailansicht auf **Gutachten erstellen**. Der Hintergrund-Task startet sofort und nach Fertigstellung erscheint automatisch ein Link zum Dokument.
2. Nach erfolgreicher Erstellung zeigt `/work/projekte/<pk>/gutachten/view/` den Text an und bietet einen Download-Link.
3. Über `/work/projekte/<pk>/gutachten/edit/` kann der Text im Browser bearbeitet und erneut gespeichert werden.
4. Ein POST-Request an `/work/projekte/<pk>/gutachten/delete/` entfernt das Dokument wieder aus dem Projekt.

### Anlage 1 prüfen

Der Aufruf

```bash
python manage.py check_anlage1 42
```

führt eine hybride Analyse der Systembeschreibung durch. Zunächst versucht der
Parser zu jeder im Admin hinterlegten Frage eine Antwort direkt aus dem Text zu
extrahieren. Anschließend werden – abhängig von den Einstellungen – einzelne
Fragen zusätzlich einem LLM vorgelegt. Das Ergebnis wird als JSON in der
zugehörigen Anlage gespeichert. Für jede Frage enthält es neben der Antwort die
Felder `status`, `hinweis` und `vorschlag`. Diese lassen sich nachträglich im
Webinterface anpassen und dokumentieren die manuelle Bewertung.

Im Admin-Bereich kann pro Frage separat festgelegt werden, ob sie beim
Parserlauf (`parser_enabled`) und/oder bei der LLM-Auswertung
(`llm_enabled`) berücksichtigt wird.
Für jede Frage lassen sich mehrere Varianten hinterlegen, die der Parser beim
Extrahieren berücksichtigt.

### Anlage 2 analysieren

Die Analyse der zweiten Anlage erfolgt über das Webinterface. In der
Projektübersicht lässt sich über den Button **Prüfen** neben Anlage 2 der
Parser starten. Dieser ermittelt ausschließlich anhand des Dokuments, welche
Funktionen oder Unterfragen ausgefüllt wurden. Eine Abfrage zum
**KI‑Beteiligung**‑Flag findet dabei nicht statt. In der Detailansicht kann im
Bedarfsfall eine weitergehende Prüfung per LLM ausgelöst werden.

### Kachel-Zugriff verwalten

Im Admin-Bereich können einzelnen Benutzern Kacheln zugewiesen werden. Nach der
Anmeldung lassen sich diese unter "Users" bearbeiten. Dort erscheint eine
zusätzliche Inline-Tabelle, über die sich die verfügbaren Tiles wie
"TalkDiary" oder "Projektverwaltung" auswählen lassen.

### Modernisiertes Admin-Interface

Das Django-Admin wurde optisch überarbeitet. Eine Seitenleiste listet alle
Modelle übersichtlich auf und bietet eine Suchleiste. Die neue Datei
`static/css/admin.css` steuert das Layout.

### Funktionskatalog verwalten

Administratorinnen und Administratoren erreichen die Übersicht aller Anlage‑2-Funktionen unter `/projects-admin/anlage2/`. Dort lassen sich neue Einträge anlegen, vorhandene Funktionen bearbeiten und auch wieder löschen. Über den Button **Importieren** kann eine JSON-Datei hochgeladen werden, die den Funktionskatalog enthält. Ist `/projects-admin/anlage2/import/` aufrufbar, bietet das Formular zudem die Option, die Datenbank vor dem Import zu leeren. Mit **Exportieren** wird der aktuelle Katalog als JSON unter `/projects-admin/anlage2/export/` heruntergeladen. Der Zugriff auf alle genannten URLs erfordert Mitgliedschaft in der Gruppe `admin`.

### KI-Begründung per Tooltip

Bei der LLM-Prüfung einzelner Funktionen ruft der Hintergrundtask zusätzlich den
Prompt `anlage2_feature_justification` auf. Dieser fragt nach einer kurzen
Begründung, warum die Funktion bei der angegebenen Software üblicherweise
vorhanden ist. Das Ergebnis wird als `ki_begruendung` gespeichert und im
Review-Formular neben dem Funktionsnamen als Info-Symbol angezeigt. Ein
Mouseover blendet den Text als Tooltip ein.

### Zweistufige KI‑Beteiligungsprüfung

In der Review-Ansicht von Anlage 2 lässt sich für jede Funktion eine
"KI‑Prüfung starten". Der Prozess arbeitet nun in zwei Stufen. Zunächst wird
geklärt, ob die Funktion technisch verfügbar ist. Nur wenn diese Prüfung
bejaht wird, folgt Stufe 2 mit der Einschätzung, ob üblicherweise eine
KI‑Beteiligung vorliegt. Beide Ergebnisse erscheinen anschließend direkt in der
Tabelle, wobei die Begründung weiterhin über den Info‑Link abrufbar ist.

Die Antwort auf die KI-Frage wird unter `ki_beteiligt` gespeichert. Gibt das
Modell "Ja" zurück, folgt zudem eine kurze Erläuterung, die im Feld
`ki_beteiligt_begruendung` landet.

### Edit-Ansicht für Analysedaten

Über den Link **Analyse bearbeiten** gelangt man zu `/work/anlage/<pk>/edit-json/`.
Die Seite lädt die aus Dokumentanalyse und manueller Bewertung entstandene
JSON-Struktur in ein Formular. Nach Anpassungen lassen sich die Daten erneut
speichern und fließen so in die weitere Auswertung ein.


### LLM-Check f\u00fcr Software-Wissen

Beim Anlegen eines Projekts kann jetzt ein zweistufiger LLM-Check gestartet werden. Dabei wird zuerst gepr\u00fcft, ob das Modell die jeweilige Software kennt. Nur bei einer positiven Antwort folgt Schritt zwei mit einer Kurzbeschreibung, die in der Tabelle **Software-Wissen** landet.
Dort lassen sich die Eintr\u00e4ge bequem bearbeiten, l\u00f6schen oder als Word-Datei exportieren.

### Initial-Pr\u00fcfung der Software-Komponenten

In der Detailansicht eines Projekts befindet sich unterhalb der Anlagen\u00fcbersicht eine Tabelle **Initial-Pr\u00fcfung der Software-Komponenten**. Hier l\u00e4sst sich f\u00fcr alle hinterlegten Software-Typen ein zweistufiger LLM-Check starten.

1. Klicke auf **Pr\u00fcfung starten**, um die Analyse f\u00fcr s\u00e4mtliche Eintr\u00e4ge gleichzeitig auszul\u00f6sen. Alternativ kann jede Zeile einzeln \u00fcber den Button **Pr\u00fcfung starten** gepr\u00fcft werden.
2. Zuerst ermittelt das LLM, ob die angegebene Software bekannt ist. Nur wenn dies bejaht wird, folgt eine zweite Abfrage mit der Bitte um eine kurze Beschreibung, die anschlie\u00dfend in der Tabelle erscheint.
3. Erkennt das Modell die Software nicht, zeigt die Zeile einen Hinweis mit dem Button **Kontext hinzuf\u00fcgen & erneut pr\u00fcfen**. Dar\u00fcber l\u00e4sst sich in einem Modal ein zus\u00e4tzlicher Beschreibungstext eingeben, der beim erneuten Durchlauf an das LLM \u00fcbermittelt wird.

Der Fortschritt der Initial-Pr\u00fcfung wird oberhalb der Tabelle angezeigt. Nach Abschluss k\u00f6nnen die erzeugten Beschreibungen bearbeitet, exportiert oder gel\u00f6scht werden.

### Tailwind CSS aktualisieren

Für den Offline-Betrieb enthält das Repository die Datei `static/css/tailwind.min.css`. Sie basiert auf einer vorkompilierten CDN-Version.

Aktualisierung per Download:

```bash
curl -L https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css -o static/css/tailwind.min.css
```

Eigene Builds lassen sich mit dem offiziellen CLI erzeugen:

```bash
curl -L -o tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.4/tailwindcss-linux-x64
chmod +x tailwindcss
./tailwindcss -i static/css/src/tailwind.css -o static/css/tailwind.min.css --minify
```
