
"""Seeding der initialen Daten per Management-Befehl."""

from django.core.management.base import BaseCommand
from django.apps import apps as django_apps
from django.contrib.auth.models import Group

from core.migrations.0002_seed_initial_data import (
    INITIAL_AREAS,
    INITIAL_PROJECT_STATUSES,
    INITIAL_LLM_ROLES,
    INITIAL_ANLAGE1_QUESTIONS,
    INITIAL_ANLAGE2_FUNCTIONS,
    INITIAL_ANLAGE2_CONFIG,
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
    FormatBParserRule = apps.get_model("core", "FormatBParserRule")
    ZweckKategorieA = apps.get_model("core", "ZweckKategorieA")
    Anlage3ParserRule = apps.get_model("core", "Anlage3ParserRule")
    Prompt = apps.get_model("core", "Prompt")
    SupervisionStandardNote = apps.get_model("core", "SupervisionStandardNote")
    User = apps.get_model("auth", "User")

    all_users = User.objects.all()

    users_group, _ = Group.objects.get_or_create(name="users")
    admin_group, _ = Group.objects.get_or_create(name="admin")

    for u in all_users:
        users_group.user_set.add(u)
        if u.is_superuser:
            admin_group.user_set.add(u)

    print("\n--- Start: Erstelle initiale Daten ---")

    # 1. Bereiche und Kacheln
    print("\n[1] Verarbeite Bereiche und Kacheln...")
    if not all_users.exists():
        print("WARNUNG: Keine Benutzer gefunden. Kacheln werden erstellt, aber niemandem zugewiesen.")
    for area_slug, area_data in INITIAL_AREAS.items():
        area, _ = Area.objects.update_or_create(slug=area_slug, defaults={"name": area_data["name"]})
        if area_slug == "work":
            allowed_users = list(users_group.user_set.all()) + list(admin_group.user_set.all())
        elif area_slug == "personal":
            allowed_users = list(admin_group.user_set.all())
        else:
            allowed_users = list(all_users)
        area.users.set(allowed_users)
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
            tile.users.add(*allowed_users)

    # 2. Projekt-Status
    print("\n[2] Verarbeite Projekt-Status...")
    for status_data in INITIAL_PROJECT_STATUSES:
        ProjectStatus.objects.update_or_create(key=status_data["key"], defaults=status_data)

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

    # 7. FormatBParserRule Defaults
    print("\n[7] Verarbeite FormatBParserRules...")
    format_rules = [
        {"key": "tv", "target_field": "technisch_verfuegbar", "ordering": 1},
        {"key": "tel", "target_field": "einsatz_telefonica", "ordering": 2},
        {"key": "lv", "target_field": "zur_lv_kontrolle", "ordering": 3},
        {"key": "ki", "target_field": "ki_beteiligung", "ordering": 4},
    ]
    for rule in format_rules:
        FormatBParserRule.objects.update_or_create(key=rule["key"], defaults=rule)

    # 8. ZweckKategorieA Defaults
    print("\n[8] Verarbeite ZweckKategorieA...")
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

    # 9. Anlage3ParserRule Defaults
    print("\n[9] Verarbeite Anlage3 Parser Regeln...")
    parser_rules = [
        {"field_name": "name", "aliases": ["name der auswertung", "name", "bezeichnung"], "ordering": 1},
        {"field_name": "beschreibung", "aliases": ["beschreibung", "kurzbeschreibung"], "ordering": 2},
        {"field_name": "zeitraum", "aliases": ["zeitraum", "auswertungszeitraum"], "ordering": 3},
        {"field_name": "art", "aliases": ["art der auswertung", "auswertungsart", "typ"], "ordering": 4},
    ]
    for rule in parser_rules:
        Anlage3ParserRule.objects.update_or_create(field_name=rule["field_name"], defaults=rule)

    # 10. Prompts
    print("\n[10] Verarbeite Prompts...")
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
            "Fasse alle Hinweise und Vorschläge aus Anlage 1 zu einem kurzen Text für den Fachbereich. Nutze {fragen} als Input.",
            True,
        ),
        (
            "gap_report_anlage2",
            "Fasse alle GAP-Notizen aus Anlage 2 für den Fachbereich zusammen. Nutze {funktionen} als Input.",
            True,
        ),
    ]
    for name, text, use_system_role in prompts:
        Prompt.objects.update_or_create(name=name, defaults={"text": text, "use_system_role": use_system_role})

    # 11. SupervisionStandardNote
    print("\n[11] Verarbeite SupervisionStandardNotes...")
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

    print("\n--- Ende: Initiale Daten erfolgreich erstellt. ---")


class Command(BaseCommand):
    """Führt das Seeding der Startdaten aus."""

    def handle(self, **options):
        create_initial_data(django_apps)
        self.stdout.write(self.style.SUCCESS("Initiale Daten wurden angelegt."))

