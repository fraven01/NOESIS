from django.db import migrations


def add_initial_check_prompts(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.get_or_create(
        name='initial_check_knowledge',
        defaults={
            'text': "Kennst du die Software '{name}'? Antworte ausschließlich mit einem einzigen Wort: 'Ja' oder 'Nein'.",
            'use_system_role': False,
        },
    )
    obj, _ = Prompt.objects.get_or_create(name='initial_llm_check')
    obj.text = (
        "Erstelle eine kurze, technisch korrekte Beschreibung für die Software '{name}'. "
        "Erläutere, was sie tut und wie sie typischerweise eingesetzt wird."
    )
    obj.save(update_fields=['text'])


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0060_prompt_use_system_role'),
    ]

    operations = [
        migrations.RunPython(add_initial_check_prompts, migrations.RunPython.noop),
    ]
