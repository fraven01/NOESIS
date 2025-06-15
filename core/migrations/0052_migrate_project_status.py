from django.db import migrations, models


# Neue Status-Tabelle einführen und bestehende Daten migrieren


def create_statuses(apps, schema_editor):
    ProjectStatus = apps.get_model('core', 'ProjectStatus')
    statuses = [
        ('NEW', 'Neu', True, False),
        ('CLASSIFIED', 'Klassifiziert', False, False),
        ('GUTACHTEN_OK', 'Gutachten OK', False, False),
        ('GUTACHTEN_FREIGEGEBEN', 'Gutachten freigegeben', False, False),
        ('IN_PRUEFUNG_ANLAGE_X', 'In Prüfung Anlage X', False, False),
        ('FB_IN_PRUEFUNG', 'FB in Prüfung', False, False),
        ('ENDGEPRUEFT', 'Endgeprüft', False, True),
    ]
    for idx, (key, name, is_default, is_done) in enumerate(statuses, start=1):
        ProjectStatus.objects.create(
            name=name,
            key=key,
            ordering=idx,
            is_default=is_default,
            is_done_status=is_done,
        )


def migrate_data(apps, schema_editor):
    ProjectStatus = apps.get_model('core', 'ProjectStatus')
    BVProject = apps.get_model('core', 'BVProject')
    History = apps.get_model('core', 'BVProjectStatusHistory')
    status_map = {s.key: s for s in ProjectStatus.objects.all()}
    for projekt in BVProject.objects.all():
        if isinstance(projekt.status, str):
            projekt.status = status_map.get(projekt.status)
            projekt.save(update_fields=['status'])
    for entry in History.objects.all():
        if isinstance(entry.status, str):
            entry.status = status_map.get(entry.status)
            entry.save(update_fields=['status'])


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0051_merge_20250613_2352'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('key', models.CharField(max_length=50, unique=True)),
                ('ordering', models.PositiveIntegerField(default=0)),
                ('is_default', models.BooleanField(default=False)),
                ('is_done_status', models.BooleanField(default=False)),
            ],
            options={'ordering': ['ordering', 'name']},
        ),
        migrations.AddField(
            model_name='bvproject',
            name='status_new',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name='projects', to='core.projectstatus'),
        ),
        migrations.AddField(
            model_name='bvprojectstatushistory',
            name='status_new',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, to='core.projectstatus'),
        ),
        migrations.RunPython(create_statuses, migrations.RunPython.noop),
        migrations.RunPython(migrate_data, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='bvproject',
            name='status',
        ),
        migrations.RemoveField(
            model_name='bvprojectstatushistory',
            name='status',
        ),
        migrations.RenameField(
            model_name='bvproject',
            old_name='status_new',
            new_name='status',
        ),
        migrations.RenameField(
            model_name='bvprojectstatushistory',
            old_name='status_new',
            new_name='status',
        ),
    ]

