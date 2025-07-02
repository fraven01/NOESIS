from django.db import migrations


def forwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.filter(name='anlage2_feature_verification').update(use_system_role=False)


def reverse_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.filter(name='anlage2_feature_verification').update(use_system_role=True)


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0063_add_ai_involvement_prompts'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
