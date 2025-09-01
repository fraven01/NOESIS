from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_remove_anlage4config_prompt_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="bvprojectfile",
            name="gap_source_hash",
            field=models.CharField(
                default="",
                blank=True,
                max_length=64,
                help_text=(
                    "Fingerprint der Eingabedaten für den zuletzt gespeicherten "
                    "GAP-Bericht."
                ),
            ),
        ),
    ]

