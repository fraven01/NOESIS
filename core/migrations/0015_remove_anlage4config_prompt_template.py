from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_remove_anlage4parserconfig_prompt_plausibility"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="anlage4config",
            name="prompt_template",
        ),
    ]

