# NOESIS

Dieses Projekt ist eine Django-Anwendung als persönlicher und personalisierter Agent.
## Installation

1. Installiere Python 3.11 und `pip`.
2. Erstelle und aktiviere eine virtuelle Umgebung:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. Installiere die Abhängigkeiten (oder führe `./setup_env.sh` aus, um alles automatisch einzurichten):
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
python manage.py migrate
python manage.py test
```

## Logging

Alle Debug-Ausgaben des Projekts werden zusätzlich in `debug.log` im Projektverzeichnis gespeichert. Diese Datei ist über `.gitignore` vom Versionskontrollsystem ausgenommen.
Parserbezogene Informationen landen in `parser-debug.log` im selben Verzeichnis. Das Log protokolliert alle Schritte beim Einlesen der Tabelle.
Während der Entwicklung schreibt jede Anlage ihr eigenes Debug-Log. Die Dateien
`anlage1-debug.log` bis `anlage6-debug.log` enthalten detaillierte Meldungen der
jeweiligen Analysefunktionen. Durch den Eintrag `*.log` im `.gitignore` werden
diese Protokolle nicht ins Repository aufgenommen.

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

Daneben bietet die Detailansicht einen separaten **Parser**‑Button. Dieser
ruft nur den Dokumentparser auf, ohne die Ergebnisse mit der
Systembeschreibung abzugleichen. Nach Änderungen an Aliaslisten lässt sich so
die Tabelle unkompliziert neu einlesen. Sämtliche Schritte landen in der
Logdatei `parser-debug.log`.


Erkennungsphrasen für den Textparser können nun zeilenweise eingegeben werden;
jede Zeile wird als eigene Phrase gespeichert.

Um den Parser auch ohne Weboberfläche zu testen, steht das Skript
`text_parser.py` bereit. Es erwartet eine Text- oder DOCX-Datei und gibt die
erkannten Funktionen als JSON aus:

```bash
python text_parser.py anlage2.docx
```



Eine LLM‑gestützte Prüfung ist nur nötig, wenn das Layout deutlich von der
erwarteten Struktur abweicht oder ungewöhnliche Formulierungen verwendet werden.
Liegt die Anlage etwa nur als Fließtext vor oder enthält sie unbekannte
Bezeichnungen, hilft der LLM‑Check, die Funktionen richtig zuzuordnen.


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

Der Textparser nutzt die Einträge aus dem Funktionskatalog, um die Anlage 2 zu analysieren. Dabei werden die Funktionsnamen als Alias für die Erkennungsphrasen verwendet. Das bedeutet, dass der Parser automatisch nach den Funktionsnamen sucht und diese als Treffer zählt. Die zurodnung, ob etwas technisch verfügbar ist, erfolgt ausschließlich über die über die Felder `technisch_vorhanden` und `technisch_verfuegbar`. Diese Felder sind für den Textparser relevant und werden bei der Analyse berücksichtigt.
Der Textparser berücksichtigt stets den Funktionsnamen bzw. den Fragetext als
Alias. Zusätzliche Varianten können für den Tabellenparser 3über das Feld `name_aliases` hinterlegt
werden. Doppelte Einträge werden automatisch ignoriert.
Beim Einlesen gleicht der Parser jede Zeile bis zum Doppelpunkt mit allen bekannten Fragen ab. Dabei kommt Fuzzy-Matching zum Einsatz; nur bei ausreichender Ähnlichkeit (Standard 80 %) gilt die Frage als erkannt.
Anschließend wird der Antwortteil ausgewertet. Hier greifen die **AntwortErkennungsRegeln**. Jede Regel enthält eine Phrase, ein Zielfeld und den zu setzenden Wert. Wird die Phrase gefunden, entfernt der Parser sie und trägt den Wert im entsprechenden Feld ein.
Beispiel: Die Regel "nicht im Einsatz" mit Ziel `einsatz_telefonica` und Wert `False` führt dazu, dass der Satz "Die Funktion ist nicht im Einsatz." automatisch `einsatz_telefonica` auf "nein" setzt.

Erkennungsphrasen werden einfach zeilenweise eingegeben.
JSON-Strukturen sind nicht mehr erforderlich; jede Zeile steht f\u00fcr eine Phrase.


### Format-B Textparser

Für kurze Listen gibt es ein vereinfachtes Eingabeformat. Welche Tokens oder
Keys ausgewertet werden, lässt sich über die Admin‑Ansicht **FormatBParserRule**
anpassen. Das Modell ordnet jedem Token ein Zielfeld zu. Standardmäßig sind die
Kürzel `tv`, `tel`, `lv` und `ki` hinterlegt und weisen auf die Felder
`technisch_verfuegbar`, `einsatz_telefonica`, `zur_lv_kontrolle` und
`ki_beteiligung`.
Jede Zeile enthält den Funktionsnamen und optional diese Tokens. Ein
Doppelpunkt trennt den Schlüssel vom Wert `ja` oder `nein`. Nummerierungen wie
`1.` oder Bindestriche am Zeilenanfang werden ignoriert.

Beispiel:

```text
Login; tv: ja; tel: nein; lv: nein; ki: ja
```

erzeugt

```json
[
  {
    "funktion": "Login",
    "technisch_verfuegbar": {"value": true, "note": null},
    "einsatz_telefonica": {"value": false, "note": null},
    "zur_lv_kontrolle": {"value": false, "note": null},
    "ki_beteiligung": {"value": true, "note": null}
  }
]
```

### Anlage‑2‑Konfiguration importieren/exportieren

Unter `/projects-admin/anlage2/config/` lässt sich zusätzlich die gesamte
Konfiguration sichern. Die exportierte JSON-Datei enthält zwei Listen:

```json
{
  "column_headings": [{"field_name": "technisch_vorhanden", "text": "Verfügbar?"}],
  "global_phrases": [{"phrase_type": "technisch_verfuegbar_true", "phrase_text": "ja"}]
}
```

Beim Import wird dieselbe Struktur erwartet. Fehlen einzelne Bereiche, werden
lediglich die vorhandenen Daten eingelesen.

Die Konfigurationsseite besitzt zwei Tabs: **Tabellen‑Parser** und
**Allgemein**. Hier lassen sich die Spaltenüberschriften und weitere Optionen
anpassen. Der frühere `parser_mode`-Schalter entfällt. 
Die Reihenfolge mehrerer Parser wird über das Feld `Parser-Reihenfolge`
bestimmt. Dabei können sowohl der Tabellenparser als auch der neue Textparser
aktiviert werden. Der Parser mit den meisten als technisch verfügbar erkannten
Funktionen liefert das Endergebnis.

Die Liste definiert gleichzeitig die Priorität. Schlagen frühere Parser fehl
oder liefern weniger Treffer, springt automatisch der nächste Parser ein.

Zusätzlich legt die Option **Parser-Priorität** fest, welcher Parser bei
aktiviertem Fallback zuerst ausgeführt wird. Standardmäßig besitzt der
Tabellenparser Vorrang.

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
Seit Version X werden die Software-Komponenten eines Projekts nicht mehr als
Komma-Liste gespeichert, sondern als eigene Objekte des Modells
``BVSoftware``. Zu einem ``BVProject`` geh\u00f6ren beliebig viele solcher
Eintr\u00e4ge.

### Seitenzahl von DOCX-Dateien ermitteln

Mit der Utility-Funktion `get_docx_page_count()` lässt sich die Seitenanzahl einer Word-Datei bestimmen. Gezählt werden sowohl eingefügte Seitenumbrüche als auch Abschnittswechsel. Ein Dokument besitzt dadurch immer mindestens eine Seite.

### Manuelle Review-Flags

Anlagen verfügen über zwei Statusfelder:
- `manual_reviewed` – kennzeichnet, dass die Datei manuell geprüft wurde.
- `verhandlungsfaehig` – markiert die Anlage als verhandlungsfähig.

Die Werte lassen sich in der Projektansicht per Button umschalten und auch in den Formularen bearbeiten.

### Bilder aus Anlagen extrahieren

Beim Hochladen einer DOCX-Datei werden alle eingebetteten Bilder mit `python-docx` extrahiert und im Upload-Verzeichnis gespeichert. Diese Dateien können anschließend vom Vision‑Modell ausgewertet werden.

### Vision-Modell

Das Vision-Modell kann im Admin-Bereich unter `/projects-admin/vision/` konfiguriert werden. Dort lassen sich die verfügbaren Modelle und deren Einstellungen verwalten. Die Konfiguration wird in der Datenbank gespeichert und kann jederzeit angepasst werden.
Standardmäßig nutzt NOESIS das Modell `gpt-4o`, das sowohl Texte als auch Bilder verarbeiten kann. Für den Betrieb muss die Umgebungsvariable `OPENAI_API_KEY` gesetzt sein. Alternativ kann ein Gemini-Modell über `GOOGLE_API_KEY` verwendet werden. Die verfügbaren Namen finden sich in `GOOGLE_AVAILABLE_MODELS` in `noesis/settings.py`.
