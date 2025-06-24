from django.db import migrations

def forwards(apps, schema_editor):
    BVProject = apps.get_model('core', 'BVProject')
    for projekt in BVProject.objects.all():
        data = projekt.software_typen
        if isinstance(data, str):
            cleaned = [s.strip() for s in data.split(',') if s.strip()]
        elif isinstance(data, list):
            cleaned = [s.strip() for s in data if str(s).strip()]
        else:
            cleaned = []
        projekt.software_typen = cleaned
        projekt.save(update_fields=['software_typen'])

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0066_delete_softwaretype'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
