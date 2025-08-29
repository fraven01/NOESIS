from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_remove_check_anlage4_prompt"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="anlage4parserconfig",
            name="prompt_plausibility",
        ),
    ]