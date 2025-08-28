from django.db import migrations


def delete_check_anlage4_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(name="check_anlage4").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_remove_anlage3_prompts"),
    ]

    operations = [
        migrations.RunPython(delete_check_anlage4_prompt, migrations.RunPython.noop),
    ]


