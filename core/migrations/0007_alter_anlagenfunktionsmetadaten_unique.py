from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_alter_anlagenfunktionsmetadaten_anlage_datei"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="anlagenfunktionsmetadaten",
            unique_together={("anlage_datei", "funktion", "subquestion")},
        ),
    ]
