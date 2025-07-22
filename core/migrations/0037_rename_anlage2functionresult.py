from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0036_add_funktions_ergebnis"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Anlage2FunctionResult",
            new_name="AnlagenFunktionsMetadaten",
        ),
        migrations.RenameField(
            model_name="anlagenfunktionsmetadaten",
            old_name="projekt",
            new_name="anlage_datei",
        ),
        migrations.AlterField(
            model_name="anlagenfunktionsmetadaten",
            name="anlage_datei",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="core.bvprojectfile"),
        ),
        migrations.RemoveField(
            model_name="anlagenfunktionsmetadaten",
            name="technisch_verfuegbar",
        ),
        migrations.RemoveField(
            model_name="anlagenfunktionsmetadaten",
            name="ki_beteiligung",
        ),
        migrations.RemoveField(
            model_name="anlagenfunktionsmetadaten",
            name="einsatz_bei_telefonica",
        ),
        migrations.RemoveField(
            model_name="anlagenfunktionsmetadaten",
            name="zur_lv_kontrolle",
        ),
        migrations.RemoveField(
            model_name="anlagenfunktionsmetadaten",
            name="source",
        ),
        migrations.RemoveField(
            model_name="anlagenfunktionsmetadaten",
            name="created_at",
        ),
        migrations.AlterUniqueTogether(
            name="anlagenfunktionsmetadaten",
            unique_together={("anlage_datei", "funktion", "subquestion")},
        ),
    ]
