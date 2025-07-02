from django.db import migrations

PROMPTS_TO_ADD = [
    {
        "name": "anlage2_ai_involvement_check",
        "text": (
            "Antworte ausschließlich mit 'Ja' oder 'Nein'. Frage: Beinhaltet die Funktion '{function_name}' der Software '{software_name}' typischerweise eine KI-Komponente? "
            "Eine KI-Komponente liegt vor, wenn die Funktion unstrukturierte Daten (Text, Bild, Ton) verarbeitet, Sentiment-Analysen durchführt oder nicht-deterministische, probabilistische Ergebnisse liefert."
        ),
    },
    {
        "name": "anlage2_ai_involvement_justification",
        "text": (
            "Gib eine kurze Begründung, warum die Funktion '{function_name}' der Software '{software_name}' eine KI-Komponente beinhaltet oder beinhalten kann, insbesondere im Hinblick auf die Verarbeitung unstrukturierter Daten oder nicht-deterministischer Ergebnisse."
        ),
    },
]

def forwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    for prompt_data in PROMPTS_TO_ADD:
        Prompt.objects.get_or_create(
            name=prompt_data["name"],
            defaults={"text": prompt_data["text"]},
        )

def reverse_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    names_to_delete = [p["name"] for p in PROMPTS_TO_ADD]
    Prompt.objects.filter(name__in=names_to_delete).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0062_remove_check_anlage2_prompt'),
    ]
    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
