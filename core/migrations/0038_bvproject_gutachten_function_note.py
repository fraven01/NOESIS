from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_add_source_to_functionresult"),
    ]

    operations = [
        migrations.AddField(
            model_name="bvproject",
            name="gutachten_function_note",
            field=models.TextField(blank=True, verbose_name="LLM-Hinweis Gutachten"),
        ),
    ]
