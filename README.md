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
   Selbst für die Test-Suite wird Selenium benötigt, das über
   `requirements-dev.txt` installiert wird.
   Diese Version nutzt **Django-Q2** (>=1.8.0) für Hintergrundprozesse.
4. Installiere zusätzliche Systempakete wie `pandoc`, damit der Export nach
   DOCX funktioniert. Unter Debian/Ubuntu lautet der Befehl beispielsweise
   `sudo apt-get install pandoc`.

## Entwickler-Setup

Bevor Tests ausgeführt werden, sollten zusätzlich die Entwicklungsabhängigkeiten
installiert werden:

```bash
pip install -r requirements-dev.txt
```

## Dependencies for Tests

Installiere vor jedem Testlauf **alle** Abhängigkeiten aus beiden
Anforderungsdateien, sonst schlagen `python manage.py makemigrations --check`
und `python manage.py test` fehl:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```
Selenium für die Browser-Tests wird durch diese zweite Datei installiert.

Alternativ kann `./setup_env.sh` die gesamte Einrichtung übernehmen.

Für alle Django-Managementbefehle muss die Umgebungsvariable
`DJANGO_SECRET_KEY` gesetzt sein. Beim Aufruf von
`python manage.py test` wird automatisch `dummy_test_key` verwendet,
falls keine Variable vorhanden ist.

## Tests und Checks

Vor jedem Commit **muss** laut `AGENTS.md` folgender Befehl erfolgreich laufen:

```bash
python manage.py makemigrations --check
```

Im Anschluss empfiehlt es sich, noch `python manage.py migrate`,
`python manage.py seed_initial_data` und `python manage.py test`
auszuführen.

### Commit-Richtlinien

- Verwende Präfixe wie `feat:`, `fix:` oder `docs:` in Commit-Botschaften.
- Die erste Zeile besteht aus einer kurzen Zusammenfassung, gefolgt von einer
  Leerzeile und einer optionalen genaueren Beschreibung.

## Logging

Alle Debug-Ausgaben des Projekts werden zusätzlich in `debug.log` im Projektverzeichnis gespeichert. Diese Datei ist über `.gitignore` vom Versionskontrollsystem ausgenommen.
Parserbezogene Informationen zu Anlage 2 landen in `anlage2-debug.log`. Dieses Log vermerkt detailliert jeden Verarbeitungsschritt.
Eine kompakte Zusammenfassung der finalen Ergebnisse befindet sich in `anlage2-ergebnis.log`.
Während der Entwicklung schreibt jede Anlage ihr eigenes Debug-Log. Die Dateien
`anlage1-debug.log` bis `anlage5-debug.log` enthalten detaillierte Meldungen der
jeweiligen Analysefunktionen. Durch den Eintrag `*.log` im `.gitignore` werden
diese Protokolle nicht ins Repository aufgenommen. Das Log für Anlage&nbsp;4
heißt `anlage4-debug.log` und befindet sich wie die anderen Logs im
Projektwurzelverzeichnis (`BASE_DIR`). Existiert die Datei nicht, kann sie
einfach als leere Datei angelegt werden, sofern Schreibrechte im
Projektordner bestehen.

## Datenbankmigrationen

Führe nach dem Einspielen neuer Code-Änderungen immer `python manage.py migrate` aus. Damit werden Datenbankanpassungen, wie etwa das Entfernen von Unique-Constraints, wirksam. Anschließend legt `python manage.py seed_initial_data` die Standarddaten erneut an. Mit

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

### GAP-Berichts-Assistent

1. Sobald in Anlage 1 oder Anlage 2 GAPs vorliegen, erscheint in der Projekt-Detailansicht der Button **GAP-Bericht f\u00fcr Fachbereich erstellen**.
2. Nach dem Klick erzeugt das LLM zwei Zusammenfassungen der offenen Punkte aus beiden Anlagen.
3. Die Texte lassen sich bearbeiten und werden beim Speichern in den jeweiligen Anlagen hinterlegt.

### Anlage 1 prüfen

Der Aufruf

```bash
python manage.py check_anlage1 <file_id>
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

### Anlage 5 prüfen

Mit

```bash
python manage.py check_anlage5 42
```

wird das hochgeladene Dokument der Anlage 5 nach allen Standardzwecken durchsucht.
Enthält es alle Zwecke aus der Datenbank und keine sonstigen Zwecke,
setzt das System die Anlage automatisch auf verhandlungsfähig.

### Anlage 2 analysieren

Beim Hochladen einer Anlage 2 startet automatisch die KI‑Prüfung.
Der Parser geht inzwischen datenbankorientiert vor: Er lädt zunächst
den vollständigen Funktionskatalog aus der Datenbank und sucht dann im
Dokument nach passenden Stellen. Anschließend bewertet das LLM jede
einzelne Funktion. Dadurch erhält jede Funktion einen Eintrag im
Ergebnis, selbst wenn sie im Dokument gar nicht vorkommt. Die
gesammelten Resultate landen kompakt in `anlage2-ergebnis.log`.

In der Projektübersicht stehen zwei Schaltflächen bereit. Über **Prüfen** wird
der Parser erneut ausgeführt, um aktualisierte Dateien einzulesen. Mit
**Analyse bearbeiten** lässt sich die erzeugte JSON‑Struktur manuell anpassen.

Wird im Projekt der Prompt geändert, setzt dies den KI‑Check zurück und führt
ihn beim nächsten Speichern erneut aus.


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

### Admin-Bereiche

NOESIS unterscheidet zwei Verwaltungsoberflächen:

* **Projekt-Admin** unter `/projects-admin/` – hier werden projektspezifische
  Daten wie Funktionskatalog oder Parser-Regeln bearbeitet.
* **System-Admin** unter `/admin/` – das klassische Django-Admin für globale
  Einstellungen, Benutzer und Gruppen.

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

Alle vorhandenen Regeln lassen sich im Admin-Menü unter
`/projects-admin/parser-rules/` übersichtlich verwalten. Für ein Backup
oder den Umzug auf ein anderes System können die Regeln zudem über den
Konfigurations-Export gesammelt heruntergeladen und wieder importiert
werden.


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

### Anlage 4 Parser konfigurieren

Der optionale Parser für die vierte Anlage arbeitet ohne LLM-Extraktion. Er
durchsucht den Freitext anhand konfigurierbarer Phrasen, die unter
`/projects-admin/anlage4/config/` angepasst werden können. Folgende Felder bestimmen das Parsing:

- `delimiter_phrase`: Regulärer Ausdruck, der den Beginn einer neuen Auswertung markiert.
- `gesellschaften_phrase`: Phrase, die den Wert für „Gesellschaften“ einleitet.
- `fachbereiche_phrase`: Phrase, die den Wert für „Fachbereiche“ einleitet.

Der Parser füllt die genannten Felder automatisch aus und überspringt den
früheren LLM-Schritt zur Extraktion.

Die anschließende Plausibilitätsprüfung läuft asynchron. Die
geparsten Werte stehen sofort bereit und die LLM-Ergebnisse werden
nach und nach in `analysis_json` ergänzt.


### Anlage‑2‑Konfiguration importieren/exportieren

Im Admin-Bereich steht unter `/projects-admin/anlage2/config/` ein eigener
Dialog bereit, um die gesamte Konfiguration zu speichern oder wieder
einzulesen. Die Links **Exportieren** und **Importieren** verweisen auf
`/projects-admin/anlage2-config/export/` beziehungsweise
`/projects-admin/anlage2-config/import/`.

Die exportierte JSON-Datei enthält alle bearbeitbaren Bereiche, darunter auch
die definierten Parserregeln:

```json
{
  "config": {"parser_order": ["table"]},
  "alias_headings": [{"field_name": "technisch_vorhanden", "text": "Verfügbar?"}],
  "answer_rules": [{
    "regel_name": "Standard",
    "erkennungs_phrase": "ja",
    "actions": {"technisch_verfuegbar": true},
    "prioritaet": 0
  }],
  "a4_parser": {"delimiter_phrase": "Name der"}
}
```

Jede Antwortregel besitzt die Schlüssel `regel_name`, `erkennungs_phrase`,
`actions` und `prioritaet`. Beim Import wird die Liste nach der angegebenen
Priorität sortiert und die Einträge werden entsprechend neu angelegt oder
aktualisiert.

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
Prompt `anlage2_feature_justification` auf. Dieser ermittelt, warum die Software
die Funktion üblicherweise besitzt und ob sich damit eine Leistungs- oder
Verhaltenskontrolle nach §87 Abs. 1 Nr. 6 BetrVG durchführen lässt. Für
Unterfragen nutzt das System den gesonderten Prompt
`anlage2_subquestion_justification_check`. Das Ergebnis wird als
`ki_begruendung` gespeichert und im Review-Formular neben dem Funktionsnamen als
Info-Symbol angezeigt. Ein Mouseover blendet den Text als Tooltip ein.

### Zweistufige KI‑Beteiligungsprüfung

In der Review-Ansicht von Anlage 2 lässt sich für jede Funktion eine
"KI‑Prüfung starten". Der Prozess arbeitet in zwei Stufen. Zunächst wird mit
einem spezifischen Prompt geklärt, ob die Funktion beziehungsweise Unterfrage
technisch möglich ist. Nur bei einem positiven Ergebnis folgt Stufe 2 mit der
Einschätzung, ob üblicherweise eine KI‑Beteiligung vorliegt. Beide Ergebnisse
erscheinen anschließend direkt in der Tabelle, wobei die jeweilige Begründung
über einen Info‑Link abrufbar ist.

Die Antwort auf die KI-Frage wird unter `ki_beteiligt` gespeichert. Gibt das
Modell "Ja" zurück, folgt zudem eine kurze Erläuterung, die im Feld
`ki_beteiligt_begruendung` landet.
Über das ℹ️-Symbol in der Tabelle gelangt man zur Detailansicht, in der sich
die Begründung bearbeiten lässt.

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

## Weitere Dokumentation

Eine ausführliche Spezifikation für den Anlage-2-Workflow findet sich in [docs/anlage2_workflow_final.md](docs/anlage2_workflow_final.md).
