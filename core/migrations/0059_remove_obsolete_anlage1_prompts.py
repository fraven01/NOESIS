from django.db import migrations


def forwards_func(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.filter(name__startswith='anlage1_q').delete()


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0058_llmrole_prompt_role'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
