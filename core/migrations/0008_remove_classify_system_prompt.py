from django.db import migrations


def delete_classify_system_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(name="classify_system").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_remove_check_gutachten_functions_prompt"),
    ]

    operations = [
        migrations.RunPython(delete_classify_system_prompt, migrations.RunPython.noop),
    ]

