# Generated by Django 5.2.2 on 2025-06-05 19:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_add_notes_field"),
    ]

    operations = [
        migrations.CreateModel(
            name="BVProject",
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
                    "title",
                    models.CharField(
                        blank=True, max_length=50, unique=True, verbose_name="Titel"
                    ),
                ),
                (
                    "beschreibung",
                    models.TextField(blank=True, verbose_name="Beschreibung"),
                ),
                (
                    "software_typen",
                    models.CharField(
                        blank=True, max_length=200, verbose_name="Software-Typen"
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am"),
                ),
                (
                    "llm_geprueft",
                    models.BooleanField(default=False, verbose_name="LLM geprüft"),
                ),
                (
                    "llm_antwort",
                    models.TextField(blank=True, verbose_name="LLM-Antwort"),
                ),
                (
                    "llm_geprueft_am",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="LLM geprüft am"
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
