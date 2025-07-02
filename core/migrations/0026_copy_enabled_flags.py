from django.db import migrations


def copy_enabled(apps, schema_editor):
    Question = apps.get_model('core', 'Anlage1Question')
    for q in Question.objects.all():
        q.parser_enabled = q.enabled
        q.llm_enabled = q.enabled
        q.save(update_fields=['parser_enabled', 'llm_enabled'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_anlage1question_llm_enabled_and_more'),
    ]

    operations = [
        migrations.RunPython(copy_enabled, migrations.RunPython.noop),
    ]

