# Generated by Django 5.2 on 2025-06-07 17:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_llmconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmconfig",
            name="models_changed",
            field=models.BooleanField(default=False),
        ),
    ]
