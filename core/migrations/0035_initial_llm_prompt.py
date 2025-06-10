from django.db import migrations


def create_prompt(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.get_or_create(
        name='initial_llm_check',
        defaults={
            'text': (
                'Do you know software {name}? Provide a short, technically correct '
                'description of what it does and how it is typically used.'
            )
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_anlage2_functions'),
    ]

    operations = [
        migrations.RunPython(create_prompt, migrations.RunPython.noop),
    ]
