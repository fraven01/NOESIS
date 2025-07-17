from django.db import migrations


def add_prompts(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    prompts = [
        (
            'anlage2_subquestion_justification_check',
            " [SYSTEM]\nDu bist Fachautor*in für IT-Mitbestimmung (§87 Abs. 1 Nr. 6 BetrVG).\n"
            "Antworte Unterfrage prägnant in **maximal zwei Sätzen** (insgesamt ≤ 65 Wörter) und erfülle folgende Regeln :\n\n"
            "1. Starte Teil A mit „Typischer Zweck: …“  \n2. Starte Teil B mit „Kontrolle: Ja, …“ oder „Kontrolle: Nein, …“.  \n"
            "3. Nenne exakt die übergebene Funktion/Eigenschaft, erfinde nichts dazu.  \n"
            "4. Erkläre knapp *warum* mit der Funktion die Unterfrage (oder warum nicht) eine Leistungs- oder Verhaltenskontrolle möglich ist.  \n"
            "5. Verwende Alltagssprache, keine Marketing-Floskeln.\n\n"
            " [USER]\nSoftware: {{software_name}}  \nFunktion/Eigenschaft: {{function_name}}  \nUnterfrage: \"{{subquestion_text}}\""
        ),
        (
            'anlage2_ai_verification_prompt',
            "Gib eine kurze Begründung, warum die Funktion '{function_name}' (oder die Unterfrage '{subquestion_text}') der Software '{software_name}' eine KI-Komponente beinhaltet oder beinhalten kann, insbesondere im Hinblick auf die Verarbeitung unstrukturierter Daten oder nicht-deterministischer Ergebnisse."
        ),
    ]
    for name, text in prompts:
        Prompt.objects.update_or_create(name=name, defaults={'text': text})


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0026_anlage5review'),
    ]

    operations = [
        migrations.RunPython(add_prompts, reverse_code=migrations.RunPython.noop),
    ]
