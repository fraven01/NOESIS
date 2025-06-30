from django.db import migrations, models


def forwards(apps, schema_editor):
    Config = apps.get_model('core', 'Anlage2Config')
    for cfg in Config.objects.all():
        order = []
        if getattr(cfg, 'default_parser', None):
            if cfg.default_parser:
                order.append(cfg.default_parser)
        if getattr(cfg, 'fallback_parser', None):
            if cfg.fallback_parser and cfg.fallback_parser not in order:
                order.append(cfg.fallback_parser)
        cfg.parser_order = order
        cfg.save(update_fields=['parser_order'])


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0079_add_parser_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='anlage2config',
            name='parser_order',
            field=models.JSONField(default=list, help_text='Reihenfolge der zu verwendenden Parser.'),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='anlage2config',
            name='default_parser',
        ),
        migrations.RemoveField(
            model_name='anlage2config',
            name='fallback_parser',
        ),
    ]
