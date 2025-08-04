from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_merge_20250804_1603"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="funktionsergebnis",
            name="project",
        ),
    ]
