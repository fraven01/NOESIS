from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_bvprojectfile_manual_comment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bvproject",
            name="status",
            field=models.CharField(
                "Status",
                max_length=20,
                choices=[
                    ("NEW", "Neu"),
                    ("CLASSIFIED", "Klassifiziert"),
                    ("GUTACHTEN_OK", "Gutachten OK"),
                    ("IN_PRUEFUNG_ANLAGE_X", "In Prüfung Anlage X"),
                    ("FB_IN_PRUEFUNG", "FB in Prüfung"),
                    ("ENDGEPRUEFT", "Endgeprüft"),
                ],
                default="NEW",
            ),
        ),
    ]
