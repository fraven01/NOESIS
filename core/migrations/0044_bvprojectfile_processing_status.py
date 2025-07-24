from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0043_bvprojectfile_versioning"),
    ]

    operations = [
        migrations.AddField(
            model_name="bvprojectfile",
            name="processing_status",
            field=models.CharField(
                default="PENDING",
                max_length=20,
                choices=[
                    ("PENDING", "Ausstehend"),
                    ("PROCESSING", "In Bearbeitung"),
                    ("COMPLETE", "Abgeschlossen"),
                    ("FAILED", "Fehlgeschlagen"),
                ],
            ),
        ),
    ]
