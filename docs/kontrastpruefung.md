# Kontrastprüfung für neue Komponenten

Um sicherzustellen, dass neue oder geänderte Komponenten einen ausreichend hohen
Farbkontrast besitzen, kann folgendes Vorgehen verwendet werden:

1. Rendern des gewünschten Templates und Ausführen der automatischen Prüfung:

   ```bash
   npm --prefix theme/static_src run contrast -- <template>
   ```

   Ohne Angabe eines Templates wird `base.html` geprüft.

2. Pa11y rendert das Template mit Hilfe der Django-Einstellungen und überprüft
   den Inhalt mit dem Axe-Runner auf Barrierefreiheitsprobleme. Bei gefundenen
   Fehlern beendet sich der Prozess mit einem Fehlercode.

Behebe alle gemeldeten Probleme, bevor der Code committet wird.
