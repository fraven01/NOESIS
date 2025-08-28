from django.db import migrations


def delete_anlage3_prompts(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(name__in=["check_anlage3", "check_anlage3_vision"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_remove_anlage1_q_prompts_and_check_anlage1_prompt"),
    ]

    operations = [
        migrations.RunPython(delete_anlage3_prompts, migrations.RunPython.noop),
    ]

