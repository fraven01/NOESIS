from django.db import migrations


def delete_anlage1_email_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(name="anlage1_email").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_remove_initial_check_knowledge_with_context_prompt"),
    ]

    operations = [
        migrations.RunPython(
            delete_anlage1_email_prompt, migrations.RunPython.noop
        ),
    ]

