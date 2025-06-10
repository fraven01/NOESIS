from django.db import migrations, models


def create_prompt(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.get_or_create(
        name='check_anlage2_function',
        defaults={'text': 'Pr\u00fcfe anhand des folgenden Textes, ob die genannte Funktion vorhanden ist. Gib ein JSON mit den Schl\u00fcsseln "technisch_verfuegbar", "einsatz_telefonica", "zur_lv_kontrolle" und "ki_beteiligung" zur\u00fcck.\n\n'}
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0033_analyse_anlage2_prompt'),
    ]

    operations = [
        migrations.CreateModel(
            name='Anlage2Function',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Anlage2FunctionResult',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('technisch_verfuegbar', models.BooleanField(null=True)),
                ('einsatz_telefonica', models.BooleanField(null=True)),
                ('zur_lv_kontrolle', models.BooleanField(null=True)),
                ('ki_beteiligung', models.BooleanField(null=True)),
                ('raw_json', models.JSONField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('funktion', models.ForeignKey(on_delete=models.deletion.CASCADE, to='core.anlage2function')),
                ('projekt', models.ForeignKey(on_delete=models.deletion.CASCADE, to='core.bvproject')),
            ],
            options={'ordering': ['funktion__name'], 'unique_together': {('projekt', 'funktion')}},
        ),
        migrations.RunPython(create_prompt, migrations.RunPython.noop),
    ]
