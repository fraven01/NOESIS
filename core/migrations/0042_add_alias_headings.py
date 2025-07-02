from django.db import migrations


def add_headings(apps, schema_editor):
    Config = apps.get_model('core', 'Anlage2Config')
    Heading = apps.get_model('core', 'Anlage2ColumnHeading')
    for cfg in Config.objects.all():
        Heading.objects.get_or_create(
            config=cfg,
            field_name='einsatz_bei_telefonica',
            text='einsatzweise bei telefónica: soll die funktion verwendet werden?'
        )
        Heading.objects.get_or_create(
            config=cfg,
            field_name='zur_lv_kontrolle',
            text='einsatzweise bei telefónica: soll zur überwachung von leistung oder verhalten verwendet werden?'
        )

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0041_anlage2columnheading'),
    ]

    operations = [
        migrations.RunPython(add_headings, migrations.RunPython.noop),
    ]
