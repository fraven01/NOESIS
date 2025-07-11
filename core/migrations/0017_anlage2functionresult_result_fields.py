from django.db import migrations, models

def copy_to_manual(apps, schema_editor):
    Result = apps.get_model('core', 'Anlage2FunctionResult')
    for res in Result.objects.all():
        res.manual_result = {
            'technisch_vorhanden': res.technisch_verfuegbar,
            'ki_beteiligung': res.ki_beteiligung,
        }
        res.save(update_fields=['manual_result'])

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_merge_20250711_1208'),
    ]

    operations = [
        migrations.AddField(
            model_name='anlage2functionresult',
            name='doc_result',
            field=models.JSONField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='anlage2functionresult',
            name='ai_result',
            field=models.JSONField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='anlage2functionresult',
            name='manual_result',
            field=models.JSONField(null=True, blank=True),
        ),
        migrations.RunPython(copy_to_manual, reverse_code=noop),
    ]
