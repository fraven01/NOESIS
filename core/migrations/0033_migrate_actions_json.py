from django.db import migrations


def forwards(apps, schema_editor):
    Rule = apps.get_model('core', 'AntwortErkennungsRegel')
    for rule in Rule.objects.all():
        if not rule.actions_json and getattr(rule, 'ziel_feld', None):
            rule.actions_json = {rule.ziel_feld: rule.wert}
            rule.save(update_fields=['actions_json'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0032_antworterkennungsregel_actions_json_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, noop),
        migrations.RemoveField(
            model_name='antworterkennungsregel',
            name='ziel_feld',
        ),
        migrations.RemoveField(
            model_name='antworterkennungsregel',
            name='wert',
        ),
    ]
