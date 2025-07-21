from django.db import migrations


def add_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.update_or_create(
        name="anlage2_subquestion_possibility_check",
        defaults={
            "text": (
                "Im Kontext der Funktion '{function_name}' der Software '{software_name}': "
                "Ist die spezifische Anforderung '{subquestion_text}' technisch möglich? "
                "Antworte nur mit 'Ja', 'Nein' oder 'Unsicher'."
            ),
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0033_migrate_actions_json"),
    ]

    operations = [
        migrations.RunPython(add_prompt, reverse_code=migrations.RunPython.noop),
    ]
