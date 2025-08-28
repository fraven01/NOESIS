from django.db import migrations


def delete_check_gutachten_functions_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(name="check_gutachten_functions").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_remove_check_anlage5_prompt"),
    ]

    operations = [
        migrations.RunPython(
            delete_check_gutachten_functions_prompt, migrations.RunPython.noop
        ),
    ]

