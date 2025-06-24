from django.db import migrations

PROMPT_KEY = "initial_llm_check"
NEW_TEXT = (
    "Erstelle eine kurze, technisch korrekte Beschreibung für die Software '{name}'. "
    "Nutze Markdown mit Überschriften, Listen oder Fettdruck, um den Text zu strukturieren. "
    "Erläutere, was sie tut und wie sie typischerweise eingesetzt wird."
)


def forwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.update_or_create(
        name=PROMPT_KEY,
        defaults={'text': NEW_TEXT},
    )


def backwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    obj = Prompt.objects.filter(name=PROMPT_KEY).first()
    if obj:
        obj.text = (
            "Erstelle eine kurze, technisch korrekte Beschreibung für die Software '{name}'. "
            "Erläutere, was sie tut und wie sie typischerweise eingesetzt wird."
        )
        obj.save(update_fields=['text'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0068_alter_bvproject_software_typen'),
    ]

    operations = [
        migrations.RunPython(forwards_func, backwards_func),
    ]
