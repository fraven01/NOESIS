from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_bvprojectfile"),
    ]

    operations = [
        migrations.AddField(
            model_name="bvproject",
            name="status",
            field=models.CharField(
                choices=[
                    ("NEW", "Neu"),
                    ("CLASSIFIED", "Klassifiziert"),
                    ("GUTACHTEN_OK", "Gutachten OK"),
                ],
                default="NEW",
                max_length=20,
                verbose_name="Status",
            ),
        ),
    ]
