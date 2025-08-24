
"""Seeding der initialen Daten per Management-Befehl."""

from django.core.management.base import BaseCommand
from django.apps import apps as django_apps
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
import secrets

from core.initial_data_constants import (
    INITIAL_AREAS,
    INITIAL_PROJECT_STATUSES,
    INITIAL_LLM_ROLES,
    INITIAL_ANLAGE1_QUESTIONS,
    INITIAL_ANLAGE2_FUNCTIONS,
    INITIAL_ANLAGE2_CONFIG,
    INITIAL_ANSWER_RULES,
)


PHRASE_FIELD_MAP = {
    "einsatz_telefonica_false": "text_einsatz_telefonica_false",
    "einsatz_telefonica_true": "text_einsatz_telefonica_true",
    "ki_beteiligung_false": "text_ki_beteiligung_false",
    "ki_beteiligung_true": "text_ki_beteiligung_true",
    "technisch_verfuegbar_false": "text_technisch_verfuegbar_false",
    "technisch_verfuegbar_true": "text_technisch_verfuegbar_true",
    "zur_lv_kontrolle_false": "text_zur_lv_kontrolle_false",
    "zur_lv_kontrolle_true": "text_zur_lv_kontrolle_true",
}


def create_initial_data(apps) -> None:
    """Legt alle Standardobjekte an oder aktualisiert sie."""
    Area = apps.get_model("core", "Area")
    Tile = apps.get_model("core", "Tile")
    ProjectStatus = apps.get_model("core", "ProjectStatus")
    LLMRole = apps.get_model("core", "LLMRole")
    Anlage1Question = apps.get_model("core", "Anlage1Question")
    Anlage1QuestionVariant = apps.get_model("core", "Anlage1QuestionVariant")
    Anlage2Function = apps.get_model("core", "Anlage2Function")
    Anlage2SubQuestion = apps.get_model("core", "Anlage2SubQuestion")
    Anlage2Config = apps.get_model("core", "Anlage2Config")
    Anlage2ColumnHeading = apps.get_model("core", "Anlage2ColumnHeading")
    ZweckKategorieA = apps.get_model("core", "ZweckKategorieA")
    Anlage3ParserRule = apps.get_model("core", "Anlage3ParserRule")
    AntwortErkennungsRegel = apps.get_model("core", "AntwortErkennungsRegel")
    Prompt = apps.get_model("core", "Prompt")
    SupervisionStandardNote = apps.get_model("core", "SupervisionStandardNote")

    # Bestehende Prompts aktualisieren: {funktionen} -> {gap_list}
    gap_prompt = Prompt.objects.filter(name="gap_report_anlage2").first()
    if gap_prompt and "{funktionen}" in gap_prompt.text:
        gap_prompt.text = gap_prompt.text.replace("{funktionen}", "{gap_list}")
        gap_prompt.save(update_fields=["text"])

    standard_group, _ = Group.objects.get_or_create(name="Standard-Benutzer")
    admin_group, _ = Group.objects.get_or_create(name="Projekt-Admins")

    print("\n--- Start: Erstelle initiale Daten ---")

    # 1. Bereiche und Kacheln
    print("\n[1] Verarbeite Bereiche und Kacheln...")
    for area_slug, area_data in INITIAL_AREAS.items():
        area, _ = Area.objects.update_or_create(slug=area_slug, defaults={"name": area_data["name"]})
        if area_slug == "work":
            allowed_groups = [standard_group, admin_group]
        elif area_slug == "personal":
            allowed_groups = [admin_group]
        else:
            allowed_groups = [standard_group, admin_group]
        area.groups.set(allowed_groups)
        for tile_data in area_data["tiles"]:
            tile, _ = Tile.objects.update_or_create(
                slug=tile_data["slug"],
                defaults={
                    "name": tile_data["name"],
                    "url_name": tile_data["url_name"],
                    "icon": tile_data["icon"],
                },
            )
            tile.areas.add(area)
            tile.groups.set(allowed_groups)

    # 2. Projekt-Status
    print("\n[2] Verarbeite Projekt-Status...")
    for status_data in INITIAL_PROJECT_STATUSES:
        ProjectStatus.objects.update_or_create(
            key__iexact=status_data["key"],
            defaults=status_data,
        )

    # 3. LLM-Rollen
    print("\n[3] Verarbeite LLM-Rollen...")
    for role_data in INITIAL_LLM_ROLES:
        LLMRole.objects.update_or_create(name=role_data["name"], defaults=role_data)

    # 4. Anlage 1 Fragen und Varianten
    print("\n[4] Verarbeite Anlage 1 Fragen...")
    for q_data in INITIAL_ANLAGE1_QUESTIONS:
        question, _ = Anlage1Question.objects.update_or_create(
            num=q_data["num"],
            defaults={
                "text": q_data["text"],
                "parser_enabled": q_data.get("parser_enabled", True),
                "llm_enabled": q_data.get("llm_enabled", True),
            },
        )
        variants_in_db = []
        for variant_text in q_data.get("variants", []):
            variant, _ = Anlage1QuestionVariant.objects.update_or_create(question=question, text=variant_text)
            variants_in_db.append(variant.id)
        Anlage1QuestionVariant.objects.filter(question=question).exclude(id__in=variants_in_db).delete()

    # 5. Anlage 2 Funktionen und Unterfragen
    print("\n[5] Verarbeite Anlage 2 Funktionen...")
    for func_data in INITIAL_ANLAGE2_FUNCTIONS:
        func, _ = Anlage2Function.objects.update_or_create(name=func_data["name"])
        subquestions_in_db = []
        for sub_q_text in func_data.get("subquestions", []):
            sub_q, _ = Anlage2SubQuestion.objects.update_or_create(funktion=func, frage_text=sub_q_text)
            subquestions_in_db.append(sub_q.id)
        Anlage2SubQuestion.objects.filter(funktion=func).exclude(id__in=subquestions_in_db).delete()

    # 6. Anlage 2 Konfiguration
    print("\n[6] Verarbeite Anlage 2 Konfiguration...")
    config, _ = Anlage2Config.objects.update_or_create(singleton_enforcer=True, defaults={"parser_mode": "auto"})
    for phrase_data in INITIAL_ANLAGE2_CONFIG["global_phrases"]:
        field = PHRASE_FIELD_MAP.get(phrase_data["phrase_type"])
        if not field:
            continue
        phrases = getattr(config, field)
        if phrase_data["phrase_text"] and phrase_data["phrase_text"] not in phrases:
            phrases.append(phrase_data["phrase_text"])
            setattr(config, field, phrases)
    for heading_data in INITIAL_ANLAGE2_CONFIG["alias_headings"]:
        Anlage2ColumnHeading.objects.update_or_create(
            config=config,
            field_name=heading_data["field_name"],
            defaults={"text": heading_data["text"]},
        )
    config.save()

    # 7. ZweckKategorieA Defaults
    print("\n[7] Verarbeite ZweckKategorieA...")
    zweck_liste = [
        "Leistungsvergleiche von Mitarbeitern oder Mitarbeitergruppen (wenn eine der Gruppen nicht größer als 5 Personen ist).",
        "Abgleich von Verhalten oder Leistung eines Mitarbeiters oder einer Mitarbeitergruppe (wenn eine der Gruppen nicht größer als 5 Personen ist) mit bestimmten Durchschnittsleistungen von Mitarbeitergruppen.",
        "Messung der Qualität oder Quantität der Leistung eines Mitarbeiters oder von Kenntnissen oder Fähigkeiten, um das Ergebnis der Messung mit einem Sollwert oder Vorgaben (z. B. betriebliche Ziele) abzugleichen.",
        "Messung der Auslastung von Mitarbeitern.",
        "Feststellung der vergangenheitsbezogenen Termine bzw. Erreichbarkeit oder persönlichen Verfügbarkeit eines Mitarbeiters.",
        "Feststellung der Termine bzw. Erreichbarkeit oder persönlichen Verfügbarkeit des Mitarbeiters in Echtzeit.",
        "Feststellung der zukünftigen Termine bzw. Erreichbarkeit oder persönlichen Verfügbarkeit des Mitarbeiters in Echtzeit.",
        "Erstellung von Bewertungen von Leistung oder Verhalten von Mitarbeitern (z. B. Zeugnisse, Scorecards etc.).",
        "Identifikation von Mitarbeitern nach bestimmten Skills (Kenntnisse, Fähigkeiten und Erfahrungen).",
        "Erstellung von Persönlichkeitsprofilen.",
        "Ermittlung des aktuellen Arbeitsortes/Aufenthaltsortes.",
    ]
    for beschreibung in zweck_liste:
        ZweckKategorieA.objects.update_or_create(beschreibung=beschreibung)

    # 8. Anlage3ParserRule Defaults
    print("\n[8] Verarbeite Anlage3 Parser Regeln...")
    parser_rules = [
        {"field_name": "name", "aliases": ["name der auswertung", "name", "bezeichnung"], "ordering": 1},
        {"field_name": "beschreibung", "aliases": ["beschreibung", "kurzbeschreibung"], "ordering": 2},
        {"field_name": "zeitraum", "aliases": ["zeitraum", "auswertungszeitraum"], "ordering": 3},
        {"field_name": "art", "aliases": ["art der auswertung", "auswertungsart", "typ"], "ordering": 4},
    ]
    for rule in parser_rules:
        Anlage3ParserRule.objects.update_or_create(field_name=rule["field_name"], defaults=rule)

    # 9. AntwortErkennungsRegeln
    print("\n[9] Verarbeite AntwortErkennungsRegeln...")
    for rule in INITIAL_ANSWER_RULES:
        AntwortErkennungsRegel.objects.update_or_create(
            regel_name=rule["regel_name"],
            defaults={
                "erkennungs_phrase": rule["erkennungs_phrase"],
                "actions_json": rule["actions"],
                "regel_anwendungsbereich": rule["regel_anwendungsbereich"],
                "prioritaet": rule["prioritaet"],
            },
        )

    # 10. Prompts
    print("\n[10] Verarbeite Prompts...")
    # Zusätzliche Prompt-Texte vorbereiten
    prompts = [
        (
            "anlage2_subquestion_justification_check",
            " [SYSTEM]\nDu bist Fachautor*in für IT-Mitbestimmung (§87 Abs. 1 Nr. 6 BetrVG).\n"
            "Antworte Unterfrage prägnant in **maximal zwei Sätzen** (insgesamt ≤ 65 Wörter) und erfülle folgende Regeln :\n\n"
            "1. Starte Teil A mit „Typischer Zweck: …“  \n2. Starte Teil B mit „Kontrolle: Ja, …“ oder „Kontrolle: Nein, …“.  \n"
            "3. Nenne exakt die übergebene Funktion/Eigenschaft, erfinde nichts dazu.  \n"
            "4. Erkläre knapp *warum* mit der Funktion die Unterfrage (oder warum nicht) eine Leistungs- oder Verhaltenskontrolle möglich ist.  \n"
            "5. Verwende Alltagssprache, keine Marketing-Floskeln.\n\n"
            " [USER]\nSoftware: {{software_name}}  \nFunktion/Eigenschaft: {{function_name}}  \nUnterfrage: \"{{subquestion_text}}\"",
            False,
        ),
        (
            "anlage2_ai_verification_prompt",
            "Gib eine kurze Begründung, warum die Funktion '{function_name}' (oder die Unterfrage '{subquestion_text}') der Software '{software_name}' eine KI-Komponente beinhaltet oder beinhalten kann, insbesondere im Hinblick auf die Verarbeitung unstrukturierter Daten oder nicht-deterministischer Ergebnisse.",
            False,
        ),
        (
            "anlage2_subquestion_possibility_check",
            "Im Kontext der Funktion '{function_name}' der Software '{software_name}': Ist die spezifische Anforderung '{subquestion_text}' technisch möglich? Antworte nur mit 'Ja', 'Nein' oder 'Unsicher'.",
            False,
        ),
        (
            "gap_summary_internal",
            "**INTERNE GAP-ANALYSE**\n\n**Funktion/Unterfrage:** \"{funktion} {unterfrage}\"\n\n**Konflikt:**\n- Dokumenten-Analyse: {dokument_wert}\n- KI-Einschätzung: {ki_wert}\n- Manuelle Bewertung durch Prüfer: {manueller_wert}\n\n**Ursprüngliche KI-Begründung:**\n{ki_begruendung}\n\n**Deine Aufgabe:**\nFormuliere eine prägnante, technische Zusammenfassung des Gaps für die interne Akte. Begründe den Kern des Konflikts zwischen den Bewertungen.",
            True,
        ),
        (
            "gap_communication_external",
            "**RÜCKFRAGE AN FACHBEREICH**\n\n**Funktion/Unterfrage:** \"{funktion}\"\n\n**Kontext der automatisierten Prüfung:**\nUnsere automatisierte Analyse der eingereichten Unterlagen hat für diese Funktion ein Gap ergeben. Eine automatisierte Einschätzung kommt zu dem Ergebnis \"{ki_wert}\".\n\n**Deine Aufgabe:**\nFormuliere eine freundliche und kollaborative Rückfrage an den Fachbereich. Erkläre höflich, dass es hier eine Abweichung zur manuellen Prüfung gibt und bitte um eine kurze Überprüfung oder zusätzliche Erläuterung der Funktion, um das Missverständnis aufzuklären. Füge keine einleitung oder abschlußworte hinzu.",
            True,
        ),
        (
            "gap_report_anlage1",
            (
                "Fasse alle Hinweise und Vorschläge aus Anlage 1 zu einem kurzen Text für den Fachbereich. "
                "Die folgenden Fragen dienen als Input:\n\n{fragen}"
            ),
            True,
        ),
        (
            "gap_report_anlage2",
            (
                "Fasse die folgenden GAP-Notizen aus Anlage 2 für den Fachbereich zusammen. "
                "Die Notizen enthalten interne und externe Anmerkungen. Formuliere eine professionelle "
                "Zusammenfassung, die für den Fachbereich geeignet ist.\n\n"
                "Hier sind die Gaps:\n"
                "{gap_list}"
            ),
            True,
        ),
    ]

    prompts.extend(
        [
            ("anlage1_email",
             "Formuliere eine freundliche E-Mail an den Fachbereich. Wir haben die Anlage 1 geprüft und noch folgende Vorschläge, bevor der Mitbestimmungsprozess weiter gehen kann. Bitte fasse die folgenden Vorschläge zusammen:\r\n\r\n",
             True),
            (
                "anlage2_ai_involvement_check",
                "Antworte ausschließlich mit 'Ja' oder 'Nein'. Frage: Beinhaltet die Funktion '{function_name}' der Software '{software_name}' typischerweise eine KI-Komponente? Eine KI-Komponente liegt vor, wenn die Funktion unstrukturierte Daten (Text, Bild, Ton) verarbeitet, Sentiment-Analysen durchführt oder nicht-deterministische, probabilistische Ergebnisse liefert.",
                True,
            ),
            (
                "anlage2_feature_justification",
                "Warum besitzt die Software '{software_name}' typischerweise die Funktion oder Eigenschaft '{function_name}'?   Ist es möglich mit der {function_name} eine Leistungskontrolle oder eine Verhaltenskontrolle  Ist damit eine Leistungskontrolle oder eine Verhaltenskontrolle im Sinne des §87 Abs. 1 Nr. 6 möglich? Wenn ja, wie?",
                True,
            ),
            (
                "anlage2_feature_verification",
                "Deine einzige Aufgabe ist es, die folgende Frage mit einem einzigen Wort zu beantworten. Deine Antwort darf AUSSCHLIESSLICH \"Ja\", \"Nein\" oder \"Unsicher\" sein. Gib keine Einleitung, keine Begründung und keine weiteren Erklärungen ab.\r\n\r\nFrage: Besitzt die Software '{software_name}' basierend auf allgemeinem Wissen typischerweise die Funktion oder Eigenschaft '{function_name}'?\n\n{gutachten}",
                False,
            ),
            (
                "check_anlage2_function",
                "Prüfe anhand des folgenden Textes, ob die genannte Funktion vorhanden ist. Gib ein JSON mit den Schlüsseln \"technisch_verfuegbar\", \"einsatz_telefonica\", \"zur_lv_kontrolle\" und \"ki_beteiligung\" zurück.\n\n",
                True,
            ),

            ("check_anlage5", "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n", True),
            ("classify_system", "Bitte klassifiziere das folgende Softwaresystem. Gib ein JSON mit den Schlüsseln 'kategorie' und 'begruendung' zurück.\n\n", True),
            ("generate_gutachten", "Erstelle ein technisches Gutachten basierend auf deinem Wissen:\n\n", True),
            ("initial_check_knowledge", "Kennst du die Software '{name}'? Antworte ausschließlich mit einem einzigen Wort: 'Ja' oder 'Nein'.", False),
            ("initial_check_knowledge_with_context", "Kennst du die Software '{name}'? Hier ist zusätzlicher Kontext, um sie zu identifizieren: \"{user_context}\". Antworte ausschließlich mit einem einigen Wort: 'Ja' oder 'Nein'.", True),
            ("initial_llm_check", "Erstelle eine kurze, technisch korrekte Beschreibung für die Software '{name}'. Nutze Markdown mit Überschriften, Listen oder Fettdruck, um den Text zu strukturieren. Erläutere, was sie tut und wie sie typischerweise eingesetzt wird.", True),
            ("check_anlage3_vision", "Prüfe die folgenden Bilder der Anlage. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n", True),
            ("anlage2_table", "Extrahiere die Funktionsnamen aus der folgenden Tabelle als JSON-Liste:\n\n", True),
            ("check_gutachten_functions", "Prüfe das folgende Gutachten auf weitere Funktionen, die nach § 87 Abs. 1 Nr. 6 mitbestimmungspflichtig sein könnten. Gib eine kurze Empfehlung als Text zurück.\n\n", True),
        ]
    )

    for q in INITIAL_ANLAGE1_QUESTIONS:
        prompts.append((f"anlage1_q{q['num']}", q["text"], True))
    for name, text, use_system_role in prompts:
        Prompt.objects.update_or_create(name=name, defaults={"text": text, "use_system_role": use_system_role})

    # 12. SupervisionStandardNote
    print("\n[12] Verarbeite SupervisionStandardNotes...")
    notes = [
        "Kein mitbest. relevanter Einsatz",
        "Lizenz-/kostenpflichtig",
        "Geplant, aber nicht aktiv",
    ]
    for order, text in enumerate(notes, start=1):
        SupervisionStandardNote.objects.update_or_create(
            note_text=text,
            defaults={"display_order": order, "is_active": True},
        )

    # 13. Standard-Benutzer
    print("\n[13] Erstelle Standard-Benutzer...")
    User = get_user_model()
    user, created = User.objects.get_or_create(username="frank")
    if created:
        password = secrets.token_urlsafe(12)
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()
        print(f"Benutzer 'frank' erstellt. Passwort: {password}")
    user.groups.add(standard_group, admin_group)

    print("\n--- Ende: Initiale Daten erfolgreich erstellt. ---")


class Command(BaseCommand):
    """Führt das Seeding der Startdaten aus."""

    def handle(self, **options):
        create_initial_data(django_apps)
        self.stdout.write(self.style.SUCCESS("Initiale Daten wurden angelegt."))

