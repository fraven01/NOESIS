from django.db import migrations


def delete_anlage1_prompts(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    # Entfernt anlage1_q1 .. anlage1_q9 sowie ggf. veralteten check_anlage1-Prompt
    Prompt.objects.filter(name__startswith="anlage1_q").delete()
    Prompt.objects.filter(name="check_anlage1").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_remove_anlage1_email_prompt"),
    ]

    operations = [
        migrations.RunPython(delete_anlage1_prompts, migrations.RunPython.noop),
    ]

