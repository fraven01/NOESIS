from django.db import migrations


def delete_initial_check_with_context_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(name="initial_check_knowledge_with_context").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_remove_classify_system_prompt"),
    ]

    operations = [
        migrations.RunPython(
            delete_initial_check_with_context_prompt, migrations.RunPython.noop
        ),
    ]

