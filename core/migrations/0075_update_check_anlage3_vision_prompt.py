from django.db import migrations

PROMPT_NAME = "check_anlage3_vision"
NEW_TEXT = "Dies ist eine Auswertung, die nach BetrVG 87 Abs. 1 Nr. 6 begutachtet werden soll. ..."
OLD_TEXT = (
    "Pr\u00fcfe die folgende Anlage auf Basis der Bilder. "
    "Gib ein JSON mit 'ok' und 'hinweis' zur\u00fcck:\n\n"
)

def forwards(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.update_or_create(
        name=PROMPT_NAME,
        defaults={"text": NEW_TEXT},
    )


def backwards(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    try:
        p = Prompt.objects.get(name=PROMPT_NAME)
        p.text = OLD_TEXT
        p.save(update_fields=["text"])
    except Prompt.DoesNotExist:
        Prompt.objects.create(name=PROMPT_NAME, text=OLD_TEXT)

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0074_add_anlage3visionresult"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
