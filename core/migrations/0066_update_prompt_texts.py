from django.db import migrations

PROMPTS = [
    {
        "name": "analyse_anlage2",
        "text": "Analysiere den folgenden Text und gib eine JSON-Liste von Objekten mit den Schlüsseln 'funktion', 'technisch_vorhanden', 'einsatz_bei_telefonica', 'zur_lv_kontrolle' und 'ki_beteiligung' zur\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "anlage1_email",
        "text": "Formuliere eine freundliche E-Mail an den Fachbereich. Wir haben die Anlage 1 geprüft und noch folgende Vorschläge, bevor der Mitbestimmungsprozess weiter gehen kann. Bitte fasse die folgenden Vorschläge zusammen:\r\n\r\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "anlage2_ai_involvement_check",
        "text": "Antworte ausschließlich mit 'Ja' oder 'Nein'. Frage: Beinhaltet die Funktion '{function_name}' der Software '{software_name}' typischerweise eine KI-Komponente? Eine KI-Komponente liegt vor, wenn die Funktion unstrukturierte Daten (Text, Bild, Ton) verarbeitet, Sentiment-Analysen durchführt oder nicht-deterministische, probabilistische Ergebnisse liefert.",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "anlage2_ai_involvement_justification",
        "text": "Gib eine kurze Begründung, warum die Funktion '{function_name}' der Software '{software_name}' eine KI-Komponente beinhaltet oder beinhalten kann, insbesondere im Hinblick auf die Verarbeitung unstrukturierter Daten oder nicht-deterministischer Ergebnisse.",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "anlage2_feature_justification",
        "text": "Warum besitzt die Software '{software_name}' typischerweise die Funktion oder Eigenschaft '{function_name}'?   Ist es möglich mit der {function_name} eine Leistungskontrolle oder eine Verhaltenskontrolle  Ist damit eine Leistungskontrolle oder eine Verhaltenskontrolle im Sinne des §87 Abs. 1 Nr. 6 möglich? Wenn ja, wie?",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "anlage2_feature_verification",
        "text": "Deine einzige Aufgabe ist es, die folgende Frage mit einem einzigen Wort zu beantworten. Deine Antwort darf AUSSCHLIESSLICH \"Ja\", \"Nein\", oder \"Unsicher\" sein. Gib keine Einleitung, keine Begründung und keine weiteren Erklärungen ab.\r\n\r\nFrage: Besitzt die Software '{software_name}' basierend auf allgemeinem Wissen typischerweise die Funktion oder Eigenschaft '{function_name}'?",
        "role_id": 3,
        "use_system_role": False,
    },
    {
        "name": "check_anlage1",
        "text": "System: Du bist ein juristisch-technischer Prüf-Assistent für Systembeschreibungen.\n\nFrage 1: Extrahiere alle Unternehmen als Liste.\nFrage 2: Extrahiere alle Fachbereiche als Liste.\nIT-Landschaft: Fasse den Abschnitt zusammen, der die Einbettung in die IT-Landschaft beschreibt.\nFrage 3: Liste alle Hersteller und Produktnamen auf.\nFrage 4: Lege den Textblock als question4_raw ab.\nFrage 5: Fasse den Zweck des Systems in einem Satz.\nFrage 6: Extrahiere Web-URLs.\nFrage 7: Extrahiere ersetzte Systeme.\nFrage 8: Extrahiere Legacy-Funktionen.\nFrage 9: Lege den Text als question9_raw ab.\nKonsistenzprüfung und Stichworte. Gib ein JSON im vorgegebenen Schema zurück.\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "check_anlage2_function",
        "text": "Prüfe anhand des folgenden Textes, ob die genannte Funktion vorhanden ist. Gib ein JSON mit den Schlüsseln \"technisch_verfuegbar\", \"einsatz_telefonica\", \"zur_lv_kontrolle\" und \"ki_beteiligung\" zurück.\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "check_anlage3",
        "text": "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "check_anlage4",
        "text": "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "check_anlage5",
        "text": "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "check_anlage6",
        "text": "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "classify_system",
        "text": "Bitte klassifiziere das folgende Softwaresystem. Gib ein JSON mit den Schlüsseln 'kategorie' und 'begruendung' zurück.\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "generate_gutachten",
        "text": "Erstelle ein tiefgehendes Gutachten zu der Software im Sinne des § 87 Abs. 1 Nr. 6 BetrVG. Richte das Gutachten ausschließlich an Betriebsräte und überspringe allgemeine Erläuterungen zu DSGVO oder Datenschutzrecht ebenso musst du nicht erläutern, wann Mitbestimmungsrechte nach §87 (1) Nr. 6 gelten.\n\nDein Gutachten soll folgende Punkte abdecken: \n\n1. **Mitbestimmungspflichtige Funktionen**   \n- Liste alleFeatures auf, die der Leistungs- oder Verhaltenskontrolle dienen (z. B. Analyse von Nutzungshistorien, App- und Kommunikationsauswertung, Dateizugriffsprotokolle).\n- Erläutere kurz, warum jede einzelne Funktion unter § 87 1 Nr. 6 BetrVG fällt. \n\n2. **Eingriffsintensität aus Mitarbeitersicht**   \n   - Beschreibe, wie stark jede dieser Funktionen in den Arbeitsablauf eingreift und welche Verhaltensaspekte sie überwacht (z. B. Häufigkeit von App-Nutzung, Kommunikationsverhalten, Standortdaten).   \n   - Nutze eine Skala (gering – mittel – hoch) und begründe die Einstufung anhand typischer Betriebsabläufe in einem Telekommunikationsunternehmen. \n\n3. **Betroffene Leistungs- und Verhaltensaspekte**   \n   - Identifiziere konkret, welche Leistungskennzahlen (z. B. Aktivitätszeiten, App-Nutzungsdauer) und Verhaltensmuster (z. B. Kommunikationshäufigkeit, Datenübertragung) erfasst und ausgewertet werden.   \n   - Schätze ab, wie umfassend und detailliert die Auswertung jeweils ausfällt. \n\n4. **Handlungsbedarf für den Betriebsrat**   \n   - Fasse zusammen, bei welchen Funktionen und Einsatzszenarien eine Betriebsvereinbarung zwingend erforderlich ist. \n\n5. **Weitere Mitbestimmungsrechte (Kurzhinweise)**   \n   - Wenn offensichtlich erkennbar ist, dass andere relevante Mitbestimmungsrechte nach BetrVG (z. B. §§ 80 ff. zur Informationspflicht) berührt sind, bewerte kurz, warum diese Software dieses Recht des Betriebsrats berühren könnte. \n\nArbeite strukturiert mit klaren Überschriften und Bullet-Points. Wo sinnvoll, nutze kurze Tabellen oder Zusammenfassungen zur Übersicht. \n. Antworte auf deutsch.\nSoftware: \n",
        "role_id": 1,
        "use_system_role": True,
    },
    {
        "name": "initial_check_knowledge",
        "text": "Kennst du die Software '{name}'? Antworte ausschließlich mit einem einzigen Wort: 'Ja' oder 'Nein'.",
        "role_id": None,
        "use_system_role": False,
    },
    {
        "name": "initial_check_knowledge_with_context",
        "text": "Kennst du die Software '{name}'? Hier ist zusätzlicher Kontext, um sie zu identifizieren: \"{user_context}\". Antworte ausschließlich mit einem einigen Wort: 'Ja' oder 'Nein'.",
        "role_id": None,
        "use_system_role": True,
    },
    {
        "name": "initial_llm_check",
        "text": "Erstelle eine kurze, technisch korrekte Beschreibung für die Software '{name}'. Nutze Markdown mit Überschriften, Listen oder Fettdruck, um den Text zu strukturieren. Erläutere, was sie tut und wie sie typischerweise eingesetzt wird.",
        "role_id": 1,
        "use_system_role": True,
    },
]

OLD_DATA = {
    "anlage1_email": {
        "text": "Formuliere eine freundliche E-Mail an den Fachbereich. Bitte fasse die folgenden Vorschläge zusammen:\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    "anlage2_feature_justification": {
        "text": "Warum besitzt die Software '{software_name}' typischerweise die Funktion oder Eigenschaft '{function_name}'?",
        "role_id": None,
        "use_system_role": True,
    },
    "anlage2_feature_verification": {
        "text": "Du bist ein Experte für IT-Systeme und Software-Architektur. Bewerte die folgende Aussage ausschließlich basierend auf deinem allgemeinen Wissen über die Software '{software_name}'. Antworte NUR mit \"Ja\", \"Nein\" oder \"Unsicher\". Aussage: Besitzt die Software '{software_name}' typischerweise die Funktion oder Eigenschaft '{function_name}'?",
        "role_id": None,
        "use_system_role": False,
    },
    "generate_gutachten": {
        "text": "Erstelle ein kurzes Gutachten basierend auf diesen Unterlagen:\n\n",
        "role_id": None,
        "use_system_role": True,
    },
    "initial_llm_check": {
        "text": "Erstelle eine kurze, technisch korrekte Beschreibung für die Software '{name}'. Erläutere, was sie tut und wie sie typischerweise eingesetzt wird.",
        "role_id": None,
        "use_system_role": True,
    },
}


def forwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    LLMRole = apps.get_model('core', 'LLMRole')
    for data in PROMPTS:
        role_id = data["role_id"]
        if role_id is not None and not LLMRole.objects.filter(pk=role_id).exists():
            role_id = None
        Prompt.objects.update_or_create(
            name=data["name"],
            defaults={
                "text": data["text"],
                "role_id": role_id,
                "use_system_role": data["use_system_role"],
            },
        )


def reverse_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    for name, data in OLD_DATA.items():
        Prompt.objects.filter(name=name).update(
            text=data["text"],
            role_id=data["role_id"],
            use_system_role=data["use_system_role"],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0065_add_context_knowledge_prompt"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
