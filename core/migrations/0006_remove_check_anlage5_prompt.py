from django.db import migrations


def delete_check_anlage5_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(name="check_anlage5").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_remove_bvprojectfile_verification_json"),
    ]

    operations = [
        migrations.RunPython(delete_check_anlage5_prompt, migrations.RunPython.noop),
    ]

