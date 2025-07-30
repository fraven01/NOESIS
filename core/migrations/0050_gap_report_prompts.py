from django.db import migrations



def add_prompts(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    prompts = [
        (
            'gap_report_anlage1',
            'Fasse alle Hinweise und Vorschl\u00e4ge aus Anlage 1 zu einem kurzen Text f\u00fcr den Fachbereich. Nutze {fragen} als Input.'
        ),
        (
            'gap_report_anlage2',
            'Fasse alle GAP-Notizen aus Anlage 2 f\u00fcr den Fachbereich zusammen. Nutze {funktionen} als Input.'
        ),
    ]
    for name, text in prompts:
        Prompt.objects.update_or_create(name=name, defaults={'text': text, 'use_system_role': True})


def remove_prompts(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.filter(name__in=['gap_report_anlage1', 'gap_report_anlage2']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0049_add_gap_fields_to_projectfile'),
    ]

    operations = [
        migrations.RunPython(add_prompts, reverse_code=remove_prompts),
    ]
