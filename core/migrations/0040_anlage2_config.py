# Generated by Django 5.2.3 on 2025-06-11 09:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0039_merge_20250611_0953"),
    ]

    operations = [
        migrations.CreateModel(
            name="Anlage2Config",
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
                (
                    "col_technisch_vorhanden",
                    models.CharField(default="Technisch vorhanden", max_length=200),
                ),
                (
                    "col_einsatz_bei_telefonica",
                    models.CharField(default="Einsatz bei Telefónica", max_length=200),
                ),
                (
                    "col_zur_lv_kontrolle",
                    models.CharField(default="Zur LV-Kontrolle", max_length=200),
                ),
                (
                    "col_ki_beteiligung",
                    models.CharField(default="KI-Beteiligung", max_length=200),
                ),
            ],
            options={
                "verbose_name": "Anlage2 Konfiguration",
            },
        ),
    ]
