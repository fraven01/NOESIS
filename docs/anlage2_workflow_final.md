# Finale Gesamt-Spezifikation für den Anlage-2-Workflow

Diese Datei beschreibt die konsolidierten Anforderungen für den Prüfprozess der Anlage 2. Sie fasst die korrekte Logik zur GAP-Erkennung, die Tooltip-Anzeige und die "Toggle"-Interaktion zum Setzen oder Zurücksetzen manueller Änderungen zusammen.

## Kernlogik 1: GAP-Identifikation für die Supervisions-Ansicht

1. **Fall 1: Ein manueller Eintrag existiert**
   - Ein GAP liegt vor, wenn der manuelle Wert vom Parser-Wert abweicht (`Manuell ≠ Parser`).
2. **Fall 2: Kein manueller Eintrag existiert**
   - Ein GAP liegt vor, wenn der Parser-Wert vom KI-Wert abweicht (`Parser ≠ KI`).

## Kernlogik 2: UI-Verhalten in der Review-Ansicht

- **Anzeigepriorität**: Standardmäßig gilt Manuell > KI > Parser. Für die Spalten „Einsatz bei Telefónica“ und „Zur LV-Kontrolle“ wird der KI-Wert ignoriert, hier lautet die Reihenfolge Manuell > Parser.
- **Tooltip**: Zeigt immer Werte aus allen drei Quellen (Dokument, KI-Check, Manuell). Die Zeile "Manuell" wird hervorgehoben, sobald dort ein Wert vorhanden ist.

## Kernlogik 3: Interaktion & Reset-Funktion als "Toggle"

- Die Klick-Funktion des Status-Buttons prüft, ob bereits ein manueller Eintrag existiert.
  - **Wenn ja**: Der manuelle Eintrag wird gelöscht (Reset).
  - **Wenn nein**: Es wird ein neuer manueller Eintrag mit dem entgegengesetzten Statuswert gespeichert (z. B. automatischer Wert `True`, manueller Wert `False`).
- Anschließend wird die Tabellenzeile neu gerendert.

## Ziel

Der Prüfer erhält damit einen vollständigen und intuitiven Workflow. Die GAP-Erkennung erfolgt korrekt, der Tooltip liefert volle Transparenz und die manuelle Bearbeitung wird durch den "Toggle" vereinfacht.
