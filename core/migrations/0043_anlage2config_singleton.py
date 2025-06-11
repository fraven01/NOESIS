from django.db import migrations, models


def ensure_single_config(apps, schema_editor):
    Config = apps.get_model('core', 'Anlage2Config')
    configs = list(Config.objects.all())
    if configs:
        for cfg in configs[1:]:
            cfg.delete()
    else:
        Config.objects.create()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0042_add_alias_headings'),
    ]

    operations = [
        migrations.AddField(
            model_name='anlage2config',
            name='singleton_enforcer',
            field=models.BooleanField(default=True, unique=True, editable=False),
        ),
        migrations.RunPython(ensure_single_config, migrations.RunPython.noop),
    ]
