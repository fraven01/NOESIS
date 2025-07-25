# Generated by Django 5.2.3 on 2025-07-02 07:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_auto_20250701_2038"),
    ]

    operations = [
        migrations.CreateModel(
            name="FormatBParserRule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("key", models.CharField(max_length=20, unique=True)),
                (
                    "target_field",
                    models.CharField(
                        choices=[
                            ("technisch_verfuegbar", "Technisch verfügbar"),
                            ("einsatz_telefonica", "Einsatz Telefónica"),
                            ("zur_lv_kontrolle", "Zur LV-Kontrolle"),
                            ("ki_beteiligung", "KI-Beteiligung"),
                        ],
                        max_length=50,
                    ),
                ),
                ("ordering", models.PositiveIntegerField(default=0)),
            ],
            options={
                "ordering": ["ordering", "key"],
            },
        ),
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model("core", "FormatBParserRule").objects.bulk_create(
                [
                    apps.get_model("core", "FormatBParserRule")(key="tv", target_field="technisch_verfuegbar", ordering=1),
                    apps.get_model("core", "FormatBParserRule")(key="tel", target_field="einsatz_telefonica", ordering=2),
                    apps.get_model("core", "FormatBParserRule")(key="lv", target_field="zur_lv_kontrolle", ordering=3),
                    apps.get_model("core", "FormatBParserRule")(key="ki", target_field="ki_beteiligung", ordering=4),
                ]
            )
        ),
    ]
