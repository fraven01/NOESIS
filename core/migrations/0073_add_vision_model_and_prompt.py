from django.db import migrations, models

PROMPT_NAME = "check_anlage3_vision"
PROMPT_TEXT = (
    "Pr\u00fcfe die folgende Anlage auf Basis der Bilder. "
    "Gib ein JSON mit 'ok' und 'hinweis' zur\u00fcck:\n\n"
)

def forwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.get_or_create(name=PROMPT_NAME, defaults={"text": PROMPT_TEXT})


def reverse_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.filter(name=PROMPT_NAME).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0072_add_review_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmconfig",
            name="vision_model",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.RunPython(forwards_func, reverse_func),
    ]
