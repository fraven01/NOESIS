# Generated by Django 5.2.4 on 2025-07-11 06:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_remove_anlage4parserconfig_prompt_extraction"),
    ]

    operations = [
        migrations.AddField(
            model_name="bvproject",
            name="project_prompt",
            field=models.TextField(blank=True, verbose_name="Projekt-Prompt"),
        ),
    ]
