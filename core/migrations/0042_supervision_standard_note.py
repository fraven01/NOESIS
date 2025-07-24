from django.db import migrations, models


def add_default_notes(apps, schema_editor):
    Note = apps.get_model('core', 'SupervisionStandardNote')
    defaults = [
        'Kein mitbest. relevanter Einsatz',
        'Lizenz-/kostenpflichtig',
        'Geplant, aber nicht aktiv',
    ]
    for order, text in enumerate(defaults, start=1):
        Note.objects.get_or_create(note_text=text, defaults={'display_order': order})


def remove_default_notes(apps, schema_editor):
    Note = apps.get_model('core', 'SupervisionStandardNote')
    Note.objects.filter(note_text__in=[
        'Kein mitbest. relevanter Einsatz',
        'Lizenz-/kostenpflichtig',
        'Geplant, aber nicht aktiv',
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0041_add_supervisor_notes'),
    ]

    operations = [
        migrations.CreateModel(
            name='SupervisionStandardNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('note_text', models.CharField(max_length=100, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('display_order', models.PositiveIntegerField(default=0)),
            ],
            options={
                'ordering': ['display_order', 'note_text'],
                'verbose_name': 'Standardnotiz Supervision',
                'verbose_name_plural': 'Standardnotizen Supervision',
            },
        ),
        migrations.RunPython(add_default_notes, reverse_code=remove_default_notes),
    ]
