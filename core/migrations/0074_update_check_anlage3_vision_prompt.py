from django.db import migrations

PROMPT_NAME = "check_anlage3_vision"
OLD_TEXT = (
    "Pr\u00fcfe die folgende Anlage auf Basis der Bilder. "
    "Gib ein JSON mit 'ok' und 'hinweis' zur\u00fcck:\n\n"
)
NEW_TEXT = (
    "Pr\u00fcfe die folgenden Bilder der Anlage. "
    "Gib ein JSON mit 'ok' und 'hinweis' zur\u00fcck:\n\n"
)

def forwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.update_or_create(
        name=PROMPT_NAME,
        defaults={"text": NEW_TEXT},
    )


def reverse_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.update_or_create(
        name=PROMPT_NAME,
        defaults={"text": OLD_TEXT},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0073_add_vision_model_and_prompt"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
