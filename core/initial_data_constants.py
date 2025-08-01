"""Konstanten für das initiale Seeding."""

# 1. Bereiche und Kacheln für die Benutzeroberfläche

INITIAL_AREAS = {
    "work": {
        "name": "BV-Gutachten",
        "tiles": [
            {
                "slug": "new-bv-project",
                "name": "Neues Gutachten",
                "url_name": "projekt_create",
                "icon": "bi-folder-plus",
            },
            {
                "slug": "bv-project-list",
                "name": "Alle Gutachten",
                "url_name": "projekt_list",
                "icon": "bi-folder",
            },
            {
                "slug": "admin-dashboard",
                "name": "Admin",
                "url_name": "admin:index",
                "icon": "bi-gear",
            },
        ],
    },
    "personal": {
        "name": "Aufnahmen",
        "tiles": [
            {
                "slug": "recordings-list",
                "name": "Meine Aufnahmen",
                "url_name": "talkdiary_personal",
                "icon": "bi-mic",
            },
        ],
    },
}

# 2. Projekt-Status
INITIAL_PROJECT_STATUSES = [
    {"key": "new", "name": "Neu", "ordering": 10, "is_default": True},
    {"key": "in_progress", "name": "In Bearbeitung", "ordering": 20},
    {"key": "review", "name": "In Prüfung", "ordering": 30},
    {"key": "done", "name": "Abgeschlossen", "ordering": 40, "is_done_status": True},
    {"key": "archived", "name": "Archiviert", "ordering": 50},
]

# 3. LLM-Rollen (aus llm_roles.json)
INITIAL_LLM_ROLES = [
    {
        "name": "Gutachten",
        "role_prompt": "Du bist eine Expert:innen-KI für Arbeitsrecht und mit einem tiefen Sachverstand für technische Systeme mit Schwerpunkt auf Leistungs- und Verhaltenskontrolle.\r\nVermeide strikt jegliche konversationelle Einleitungen oder Füllwörter wie 'Gerne, hier ist...', 'Absolut, ...' oder 'Ich habe die Analyse durchgeführt und...'.\r\n\r\nDu sprichst den Anwender mit 'Du' an.\r\n\r\nDeine einzige Aufgabe ist es, die folgende Anweisung, die nach einer Trennlinie kommt, bestmöglich auszuführen.",
        "is_default": False,
    },
    {
        "name": "IT Experte",
        "role_prompt": "Du bist ein Experte für IT-Systeme und Software-Architektur.\r\nVermeide strikt jegliche konversationelle Einleitungen oder Füllwörter wie 'Gerne, hier ist...', 'Absolut, ...' oder 'Ich habe die Analyse durchgeführt und...'.\r\n\r\nDu sprichst den Anwender mit 'Du' an.\r\n\r\nDeine einzige Aufgabe ist es, die folgende Anweisung, die nach einer Trennlinie kommt, bestmöglich auszuführen.",
        "is_default": False,
    },
    {
        "name": "Standard",
        "role_prompt": "Du bist ein Fachexperte für die Prüfung von IT-Systemen im Kontext von Betriebsvereinbarungen \r\nDeine Antworten sind stets sachlich, präzise und direkt auf den Punkt. Vermeide strikt jegliche konversationelle Einleitungen oder Füllwörter wie 'Gerne, hier ist...', 'Absolut, ...' oder 'Ich habe die Analyse durchgeführt und...'.\r\n\r\nDu sprichst den Anwender mit 'Du' an.\r\n\r\nDeine einzige Aufgabe ist es, die folgende Anweisung, die nach einer Trennlinie kommt, bestmöglich auszuführen.",
        "is_default": True,
    },
]

# 4. Anlage 1 Fragen und Varianten (aus anlage1_questions.json)
INITIAL_ANLAGE1_QUESTIONS = [
    {
        "num": 1,
        "text": "Wo wird das System eingesetzt (Unternehmen)?",
        "variants": [
            "Wo wird das System eingesetzt (Unternehmen)?",
            "In welchen Gesellschaften/Betrieben soll die Software eingeführt werden?",
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 2,
        "text": "In welchen Fachbereichen soll das System genutzt werden?",
        "variants": [
            "In welchen Fachbereichen soll das System genutzt werden?",
            "In welchen Fachbereichen soll das System eingesetzt werden?:",
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 3,
        "text": "Wenn mehr als eine Software eingeführt wird: Welche Softwareanwendungen sind umfasst? (Hersteller und Produkte müssen benannt werden)",
        "variants": [
            "Wenn mehr als eine Software eingeführt wird: Welche Softwareanwendungen sind umfasst? (Hersteller und Produkte müssen benannt werden)",
            "Wenn mehr als eine Software eingeführt wird: Welche Softwareanwendungen sind umfasst?",
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 4,
        "text": "Cloudsoftware – SaaS, PaaS, IaaS?",
        "variants": [
            "Cloudsoftware – SaaS, PaaS, IaaS?",
            "Um welche Art von Cloudsoftware handelt es sich?: ",
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 5,
        "text": "Wofür wird das System eingesetzt?",
        "variants": ["Wofür wird das System eingesetzt?"],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 6,
        "text": "Anbieterseitige Informationen zum System internes Systemhandbuch (aktuelle Version), soweit vorhanden",
        "variants": [
            "Anbieterseitige Informationen zum System internes Systemhandbuch (aktuelle Version), soweit vorhanden",
            "Anbieterseitige Informationen zum System:",
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 7,
        "text": "Welche Systeme bekommen Daten von diesem System?",
        "variants": [
            "Welche Systeme bekommen Daten von diesem System?",
            "Findet ein Datenaustausch von personenbezogenen Mitarbeiterdaten zwischen verschiedenen Systemen statt?",
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 8,
        "text": "Wenn Altsysteme ersetzt werden: welche Systeme sind das?",
        "variants": [
            "Wenn Altsysteme ersetzt werden: welche Systeme sind das?",
            "Werden Altsysteme oder Funktionen von Altsystemen ersetzt?",
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
    {
        "num": 9,
        "text": "Wenn einzelne Funktionen ersetzt werden: welche einzelnen Funktionen sind das und aus welchem Altsystem kommen sie? ",
        "variants": [
            "Wenn einzelne Funktionen ersetzt werden: welche einzelnen Funktionen sind das und aus welchem Altsystem kommen sie? "
        ],
        "parser_enabled": True,
        "llm_enabled": False,
    },
]

# 5. Anlage 2 Funktionen und Unterfragen (aus anlage2_functions.json)
INITIAL_ANLAGE2_FUNCTIONS = [
    {"name": "Analyse-/Reportingfunktionen", "subquestions": []},
    {
        "name": "Anwesenheitsüberwachung",
        "subquestions": [
            "Werden die Anwesenheitsdaten von Mitarbeitenden automatisch protokolliert und gespeichert?",
            "Können Mitarbeiter ihre Anwesenheit manuell ein- und ausstempeln?",
            "Gibt es eine Möglichkeit, die Anwesenheit über mobile Geräte (z.B. Smartphones) zu kontrollieren?",
            "Können Fehlzeiten und Abwesenheitsgründe dokumentiert werden?",
            "Gibt es die Möglichkeit, Benachrichtigungen oder Alarme bei An-/ Abwesenheiten einzustellen?",
            "Können Berichte über Anwesenheitszeiten erstellt und exportiert werden?",
            "Ist die Anwesenheitsüberwachung in der Lage, Daten in andere Systeme zu übertragen (z. B. Gehaltsabrechnung, Zeiterfassung, BI-Tools)?",
            "Gibt es die Möglichkeit, sich Benachrichtigungen oder Alarme über Unstimmigkeiten zwischen den Daten aus der Anwesenheitsüberwachung und den Daten aus anderen Systemen einzustellen?",
            "Gibt es eine Möglichkeit, die Anwesenheitsdaten in Echtzeit zu visualisieren?",
        ],
    },
    {
        "name": "Aufzeichnung von Eingaben der User an Endgeräten",
        "subquestions": [
            "Werden Eingabedaten (Tastatureingaben, Mausbewegungen, Klicks) von Mitarbeitenden gespeichert? Wenn ja, weitere Fragen unten …",
            "Werden Zeitstempel für aufgezeichnete Eingabe erfasst?",
            "Können die Eingabedaten nach bestimmten Kriterien (z.B. Benutzer, Zeitraum, Gerät) gefiltert werden?",
            "Können die Eingabedaten in Echtzeit eingesehen und analysiert werden?",
            "Können die Eingabedaten historisch eingesehen und analysiert werden?",
            "Können die Eingabedaten exportiert?",
            "Können historische Eingabedaten für langfristige Analysen und Audits gespeichert werden?",
            "Ist es möglich, die Eingabedaten in ein zentrales Monitoring-System zu integrieren?",
        ],
    },
    {
        "name": "Automatisierte Entscheidung mit Mitarbeiterbezug bzw. mit Auswirkungen auf Mitarbeitende",
        "subquestions": [
            "Können die Zuweisungskriterien individuell angepasst und konfiguriert werden?",
            "Ist es möglich, Aufgaben basierend auf Fähigkeiten der Mitarbeitenden zuzuweisen?",
            "Ist es möglich, Aufgaben basierend auf Verfügbarkeit der Mitarbeitenden zuzuweisen?",
            "Ist es möglich, Aufgaben basierend auf bisherigen Leistungen der Mitarbeitenden zuzuweisen?",
            "Gibt es eine Funktion zur Priorisierung von Aufgaben bei der automatisierten Zuweisung?",
            "Können Mitarbeitende Aufgaben ablehnen?",
            "Werden historische Daten zur Optimierung zukünftiger Aufgabenverteilungen genutzt?",
            "Können Berichte über die Effektivität und Effizienz der automatisierten Aufgabenverteilung erstellt werden?",
            "Können automatisierte Zuweisungen nachträglich überprüft und manuell von TEF angepasst werden?",
        ],
    },
    {
        "name": "Automatisierungsfunktionen (z. B. roboterbasierte Prozessautomatisierung)",
        "subquestions": [
            "Werden oder sollen Aufgaben oder Tätigkeiten von RPA-Robotern übernommen werden? Wenn ja, welche?",
            "Werden die Ergebnisse der RPA-Automatisierung in Echtzeit überwacht und analysiert?",
            "Ist die RPA-Automatisierung in der Lage, komplexe Arbeitsabläufe oder Entscheidungsprozesse abzubilden?",
            "Ist es möglich, Berichte über die Effektivität und ROI (Return on Investment) der RPA-Automatisierung zu erstellen?",
            "Gibt es eine Möglichkeit, RPA-Roboter so zu trainieren, dass sie kontinuierlich lernen und sich an neue Prozesse anpassen?",
            "Gibt es Ersatzarbeit für die wegfallenden manuellen Prozesse? Wenn ja, welche?",
            "In welchen Fachbereichen wird automatisiert?",
        ],
    },
    {
        "name": "Berichtsfunktion über Aktivitäten von Mitarbeitenden",
        "subquestions": [
            "Können individuelle Berichte mit Mitarbeiterbezug nach spezifischen Kriterien (z.B. Projekte, Aufgaben, Zeiträume) gefiltert werden?",
            "Können Berichte in Echtzeit generiert und aktualisiert werden?",
            "Ist es möglich, Berichte in verschiedenen Formaten (z.B. PDF, Excel) zu exportieren?",
            "Können Aktivitäten, die außerhalb der regulären Arbeitszeiten stattfinden, separat ausgewiesen werden?",
        ],
    },
    {
        "name": "Bild-/ oder Tonaufzeichnungen (Kameras, Mikrofone, Screenshots etc.)",
        "subquestions": [
            "Können Bild- und Tonaufzeichnungen von Mitarbeitenden in Echtzeit überwacht werden?",
            "Können Aufzeichnungen automatisch gespeichert und archiviert werden?",
            "Gibt es eine Möglichkeit, bestimmte Ereignisse oder Aktionen als Auslöser für Bild- oder Tonaufzeichnungen zu definieren?",
            "Können die Aufzeichnungen nach bestimmten Kriterien (z.B. Zeitraum, Benutzer, Standort) gefiltert werden?",
            "Gibt es eine Möglichkeit, bestimmte Bereiche oder Räume von der Aufzeichnung auszuschließen?",
            "Können die Aufzeichnungen in andere Systeme (z.B. Sicherheitsmanagement, Zeitmanagement) integriert werden?",
            "Werden Benutzer über die Aufzeichnung von Bild- und Tondaten informiert?",
            "Gibt es Benachrichtigungen oder Alarme bei der Erfassung von Aktivitäten durch Bild- oder Tonaufzeichnungen?",
            "Können Live-Aufzeichnungen für Schulungen verwendet werden?",
            "Gibt es eine Möglichkeit, die Aufzeichnungen nachträglich zu analysieren?",
        ],
    },
    {
        "name": "Chatfunktion",
        "subquestions": [
            "Können an sich private Chats mit anderen geteilt werden?",
            "Soll die Chatfunktion dafür genutzt werden, um damit Arbeitsanweisungen auszusprechen?",
            "Kann der Chat überwacht werden?",
        ],
    },
    {
        "name": "Compliance-Überwachung",
        "subquestions": [
            "Welche spezifischen Compliance-Standards oder -Vorschriften unterstützt die Software (z.B. Datenschutz, Arbeitssicherheit)?",
            "Welche Compliance-Aspekte z.B. welche gesetzlichen Vorschriften oder Unternehmensrichtlinien) werden verwaltet?",
            "Werden mit der Software Compliance-Risiken (z.B. Fraud Prevention, Fraud Detection) detektiert?",
            "Ist die Software in der Lage, Echtzeit-Compliance-Daten und -Berichte bereitzustellen?",
            "Können Abweichungen von Compliance-Standards automatisch erkannt und gemeldet werden?",
            "Gibt es Funktionen zur automatischen Benachrichtigung bei Verstößen gegen Compliance-Richtlinien?",
        ],
    },
    {
        "name": "Ermittlung von Prozesslaufzeiten (sofern Beschäftigte in den Prozess integriert sind)",
        "subquestions": [
            "Kann die Software die Dauer einzelner Prozessschritte automatisch erfassen?",
            "Werden die Start- und/oder Endzeiten der Prozessschritte protokolliert?",
            "Können Prozesslaufzeiten für unterschiedliche Prozesse separat ermittelt und verglichen werden?",
            "Gibt es vordefinierte Berichte zur Analyse von Prozesslaufzeiten?",
            "Können die Prozesslaufzeiten in Echtzeit überwacht und visualisiert werden?",
            "Ist es möglich, Abweichungen von geplanten Prozesslaufzeiten automatisch zu erkennen und zu melden?",
            "Können historische Prozesslaufzeiten für die Analyse und Optimierung von Prozessen herangezogen werden?",
            "Gibt es eine Funktion zur Identifizierung von Engpässen oder Verzögerungen innerhalb eines Prozesses?",
            "Können die Prozesslaufzeiten mit anderen Systemen (z.B. ERP, Workflow-Management) verknüpft werden?",
            "Gibt es eine Möglichkeit, die Prozesslaufzeiten durch Simulationen oder Prognosen zu verbessern?",
        ],
    },
    {
        "name": "Ermittlung von produktiven und unproduktiven Zeiten von Mitarbeitern",
        "subquestions": [
            "Kann die Software zwischen produktiven und unproduktiven Zeiten automatisch unterscheiden?",
            "Welche Kriterien werden zur Klassifizierung von produktiven und unproduktiven Zeiten verwendet?",
            "Ist es möglich, produktive und unproduktive Zeiten nach bestimmten Aktivitäten oder Aufgaben zu filtern?",
            "Können Berichte über produktive und unproduktive Zeiten für einzelne Mitarbeiter oder Teams <5 erstellt werden?",
            "Können Visualisierungen der produktiven und unproduktiven Zeiten (z.B. in Form von Grafiken oder Diagrammen) erstellt werden?",
            "Können Echtzeit-Daten zur Produktivität abgerufen werden?",
            "Gibt es eine Möglichkeit, unproduktive Zeiten durch Benachrichtigungen oder Alarme zu minimieren?",
            "Können die erfassten Daten exportiert und in anderen Formaten (z.B. PDF, Excel) analysiert werden?",
            "Ist es möglich, die Ermittlung von produktiven und unproduktiven Zeiten mit anderen Systemen (z.B. Projektmanagement, Zeiterfassung) zu integrieren?",
            "Können Maßnahmen oder Empfehlungen zur Verbesserung der Produktivität direkt aus den Berichten abgeleitet werden?",
            "Werden Produktivdaten weiteren Systemen zur Verfügung gestellt und wenn ja, welchen?",
        ],
    },
    {
        "name": "Feedback- und Bewertungsfunktionen",
        "subquestions": [
            "Welches Feedback wird innerhalb der Software erfasst und verwaltet (z.B. Feedback von Vorgesetzten, Kollegen, Kunden)?",
            "Werden Feedback-Verläufe automatisch dokumentiert?",
            "Ist es möglich, Feedback in Echtzeit zu geben und zu empfangen?",
            "Werden Mitarbeiter benachrichtigt, wenn neues Feedback über sie verfügbar ist?",
            "Können Feedback-Eingaben direkt in die Leistungsbeurteilung oder Zielverfolgung integriert werden?",
            "Werden Feedbacks in andere Tools integriert, um Arbeitsabläufe bewerten zu können?",
            "Können Feedback-Eingaben nach verschiedenen Kriterien (z.B. Mitarbeiter, VO- Nummer, Zeitstempel, Themenbereich) gefiltert und sortiert werden?",
        ],
    },
    {
        "name": "Leistungsmessung und Zielverfolgung",
        "subquestions": [
            "Können individuelle Ziele und Teamziele innerhalb der Software verwaltet und verfolgt werden?",
            "Gibt es Funktionen zur Ermittlung von Schulungs- oder Entwicklungsbedarf?",
            "Gibt es eine Funktion zur automatischen Erinnerung an ausstehende Leistungsmessungen oder Zielüberprüfungen?",
            "Können historische Leistungsdaten für langfristige Analysen und Vergleiche verwendet werden?",
            "Ist die Software mit Skillmanagment-Systemen integrierbar, um Leistungsdaten mit Kompetenzen zu verknüpfen?",
            "Können Leistungsberichte und Bewertungen automatisch generiert werden?",
            "Ist die Software mit Personalentwicklungssystemen zu verknüpfen?",
            "Können Mitarbeitende selbstständig ihren Fortschritt bei der Zielverfolgung einsehen?",
            "Können Mitarbeitende selbstständig ihren Fortschritt bei der Zielverfolgung aktualisieren (eingeben)?",
            "Kann der Fortschritt von Mitarbeitenden bei der Erreichung von Zielen und KPIs überwacht und gemessen werden?",
            "Können Zielvorgaben automatisch mit den individuellen Leistungsplänen der Mitarbeitenden verknüpft werden?",
        ],
    },
    {
        "name": "Mitarbeiterbefragungen",
        "subquestions": [
            "Gibt es Funktionen zur Anonymisierung der Umfrageergebnisse?",
            "Werden Umfrageergebnisse in Echtzeit analysiert oder visualisiert?",
            "Haben Mitarbeiter Zugriff auf ihre Antworten?",
            "Bietet die Software die Möglichkeit die eigenen Antworten zu korrigieren?",
            "Können bei der Befragung erfasste Metadaten (z.B. Zeitstempel) ausgewertet werden?",
        ],
    },
    {
        "name": "Mobile App",
        "subquestions": [
            "Gibt es eine mobile App für das System?",
            "Sind alle Kernfunktionen des Systems über die mobile App verfügbar?",
            "Nutzt die mobile App die Benachrichtigungsfunktion des Systems?",
            "Werden Berechtigungen wie z. B. Zugriff auf die Kamera, das Mikrofon, Kontaktdaten, Anrufliste oder auf sonstige Daten vom System für die mobile App abgefragt?",
        ],
    },
    {
        "name": "Ortungsfunktion",
        "subquestions": [
            "Kann die Ortungsfunktion den aktuellen Standort eines Mitarbeiters bzw. eines vom Mitarbeiter bei sich geführten Geräts anzeigen?",
            "Werden historische Standortdaten gespeichert und können diese abgerufen werden?",
            "Kann die Ortungsfunktion genutzt werden, um Mitarbeiter innerhalb eines bestimmten Bereichs oder Gebäudes zu lokalisieren?",
            "Gibt es Benachrichtigungen oder Alarme, wenn ein Mitarbeiter einen definierten Bereich betritt oder verlässt?",
            "Ist die Ortungsfunktion in der Lage, standortbasierte (Aufenthaltsort des Mitarbeiters) Aufgaben oder Benachrichtigungen auszulösen?",
            "Gibt es eine Integration der Ortungsfunktion mit anderen Systemen (z.B. Zeiterfassung, Sicherheitsmanagement)?",
            "Gibt es eine Möglichkeit, die Ortungsdaten in Echtzeit zu visualisieren?",
        ],
    },
    {
        "name": "Protokollierung von Benutzeraktivitäten",
        "subquestions": [
            "Welche spezifischen Benutzeraktivitäten werden von der Software protokolliert?",
            "Werden Zeitstempel für personalisierte Aktivitäten erfasst?",
            "Können Protokolldaten in Echtzeit eingesehen und analysiert werden?",
            "Werden Protokolldaten für ein Data Warehouse oder BI Tools (PowerBI, Tableau, Grafana) zur Verfügung gestellt?",
        ],
    },
    {
        "name": "Risikomanagement und Frühwarnindikatoren",
        "subquestions": [
            "Enthält das System Risikomanagement- oder Frühwarnfunktionen?"
        ],
    },
    {
        "name": "Social-Media-Überwachung",
        "subquestions": [
            "Welche sozialen Medien werden von der Überwachungssoftware überwacht?",
            "Wie werden die Aktivitäten der Mitarbeitenden in sozialen Medien durch die Software erfasst und analysiert?",
            "Welche Arten von Aktivitäten werden überwacht (z.B. Posts, Kommentare, Likes)?",
            "Können spezifische Schlüsselwörter oder Themen überwacht werden?",
            "Ist auch eine Überwachung von privaten Accounts der Mitarbeitenden möglich?",
            "Gibt es eine Möglichkeit zur Echtzeit-Überwachung der Social-Media-Aktivitäten?",
            "Werden nur öffentliche oder auch private Inhalte der Mitarbeitenden in sozialen Medien überwacht?",
            "Gibt es eine automatische Benachrichtigung oder Alarmierung bei potenziell problematischen oder gegen Unternehmensrichtlinien verstoßenden Aktivitäten?",
            "Können Mitarbeitende Einsicht in ihre eigenen überwachten Daten erhalten?",
        ],
    },
    {
        "name": "Suchfunktion",
        "subquestions": [
            "Kann direkt nach Mitarbeitern (z.B. Name, VO-Nummer, NQ-Nummer etc.) gesucht werden?",
            "Können Performanceabfragen durch die Suchfunktion gemacht werden?",
            "Kann man Performanceabfragen nach zeitlichen Ergebnissen eingrenzen?",
        ],
    },
    {
        "name": "Technische Funktionen für Entwicklung und Weiterbildung von Mitarbeitenden",
        "subquestions": [
            "Können individuelle Entwicklungspläne für Mitarbeitende erstellt und verfolgt werden?",
            "Werden Weiterbildungsbedarfe automatisch ermittelt?",
            "Gibt es Funktionen zur Planung und Buchung von Weiterbildungsmaßnahmen innerhalb der Software?",
            "Können Mitarbeitende selbstständig Lernaktivitäten suchen und beantragen?",
            "Können Lernfortschritte und Zertifizierungen automatisch in Mitarbeiterprofile oder Personalakten integriert werden?",
            "Können Weiterbildungsbedarfe individuell ermittelt werden?",
        ],
    },
    {
        "name": "Verhaltensanalysen und Persönlichkeitsprofile",
        "subquestions": [
            "Welche Arten von Verhaltensanalysen können mit dem System durchgeführt werden (z.B. Kommunikationsanalysen, Zusammenarbeit)?",
            "Gibt es eine Möglichkeit, Persönlichkeitsprofile oder Verhaltensmuster der Mitarbeitenden zu erstellen?",
            "Können Verhaltensanalysen für individuelle Mitarbeitende oder für Teams durchgeführt werden?",
            "Gibt es Funktionen zur automatischen Generierung von Verhaltensprofilen oder -berichten?",
            "Gibt es Funktionen zur automatischen Benachrichtigung über signifikante Verhaltensänderungen oder Muster?",
        ],
    },
    {
        "name": "Zeiterfassung und Arbeitszeitmanagement",
        "subquestions": [
            "Welche Methoden der Zeiterfassung unterstützt die Software (z.B. Stempeluhr, mobile App, Webanwendung)?",
            "Gibt es eine Möglichkeit, Arbeitszeiten in Echtzeit zu überwachen und zu visualisieren (z.B. auf Dashboards)?",
            "Können Berichte über Arbeitszeiten und Arbeitszeitkonten automatisch generiert und exportiert werden?",
            "Gibt es Funktionen zur automatischen Erinnerung an ausstehende Zeiterfassungen oder Genehmigungen?",
            "Können Arbeitszeitdaten für langfristige Analysen und Berichte verwendet werden?",
        ],
    },
]

# 6. Anlage 2 Konfiguration (aus anlage2_config.json)
INITIAL_ANLAGE2_CONFIG = {
    "global_phrases": [
        {"phrase_type": "einsatz_telefonica_false", "phrase_text": ""},
        {"phrase_type": "einsatz_telefonica_true", "phrase_text": ""},
        {"phrase_type": "ki_beteiligung_false", "phrase_text": ""},
        {"phrase_type": "ki_beteiligung_true", "phrase_text": ""},
        {"phrase_type": "technisch_verfuegbar_false", "phrase_text": ""},
        {"phrase_type": "technisch_verfuegbar_true", "phrase_text": ""},
        {"phrase_type": "zur_lv_kontrolle_false", "phrase_text": ""},
        {"phrase_type": "zur_lv_kontrolle_true", "phrase_text": ""},
    ],
    "alias_headings": [
        {
            "field_name": "einsatz_bei_telefonica",
            "text": "Einsatzweise bei Telefónica: Soll die Funktion verwendet werden?  Ja/nein",
        },
        {
            "field_name": "technisch_vorhanden",
            "text": "steht technisch zur verfügung? \\n\\nja/nein",
        },
        {
            "field_name": "zur_lv_kontrolle",
            "text": "Einsatzweise bei Telefónica: Soll zur Überwachung von Leistung oder Verhalten verwendet werden?  Ja / nein",
        },
    ],
}

# --- Hauptfunktion der Migration ---


