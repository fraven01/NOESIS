from django.db import migrations, models


def forwards(apps, schema_editor):
    Rule = apps.get_model('core', 'AntwortErkennungsRegel')
    for rule in Rule.objects.all():
        data = rule.actions_json
        if isinstance(data, dict):
            rule.actions_json = [{"field": k, "value": v} for k, v in data.items()]
            rule.save(update_fields=['actions_json'])


def backwards(apps, schema_editor):
    Rule = apps.get_model('core', 'AntwortErkennungsRegel')
    for rule in Rule.objects.all():
        data = rule.actions_json
        if isinstance(data, list):
            out = {}
            for obj in data:
                field = obj.get('field')
                if not field:
                    continue
                out[field] = obj.get('value')
            rule.actions_json = out
            rule.save(update_fields=['actions_json'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_add_subquestion_possibility_prompt'),
    ]

    operations = [
        migrations.AlterField(
            model_name='antworterkennungsregel',
            name='actions_json',
            field=models.JSONField(default=list, blank=True, help_text='Aktionen als Liste von Objekten.'),
        ),
        migrations.RunPython(forwards, backwards),
    ]
