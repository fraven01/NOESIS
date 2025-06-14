# Generated by Django 5.2.3 on 2025-06-15 22:10

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0054_remove_bvproject_status_old_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="bvproject",
            name="llm_antwort",
        ),
        migrations.RemoveField(
            model_name="bvproject",
            name="llm_geprueft",
        ),
        migrations.RemoveField(
            model_name="bvproject",
            name="llm_geprueft_am",
        ),
        migrations.RemoveField(
            model_name="bvproject",
            name="llm_initial_output",
        ),
        migrations.RemoveField(
            model_name="bvproject",
            name="llm_validated",
        ),
        migrations.CreateModel(
            name="SoftwareKnowledge",
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
                ("software_name", models.CharField(max_length=100)),
                ("is_known_by_llm", models.BooleanField(default=False)),
                ("description", models.TextField(blank=True)),
                ("last_checked", models.DateTimeField(blank=True, null=True)),
                (
                    "projekt",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="softwareknowledge",
                        to="core.bvproject",
                    ),
                ),
            ],
            options={
                "ordering": ["software_name"],
                "unique_together": {("projekt", "software_name")},
            },
        ),
    ]
