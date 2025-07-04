from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_anlage4_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="Anlage4ParserConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("table_columns", models.JSONField(default=list, blank=True)),
                ("text_rules", models.JSONField(default=list, blank=True)),
                ("prompt_extraction", models.TextField(blank=True)),
                ("prompt_plausibility", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Anlage4 Parser Konfiguration",
            },
        ),
        migrations.AddField(
            model_name="bvprojectfile",
            name="anlage4_parser_config",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.anlage4parserconfig"),
        ),
    ]
