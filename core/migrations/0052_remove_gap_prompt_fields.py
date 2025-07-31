from django.db import migrations


def delete_gap_prompts(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.filter(
        name__in=["gap_summary_internal", "gap_communication_external"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0051_alter_anlage2config_parser_order_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="funktionsergebnis",
            name="gap_begruendung_intern",
        ),
        migrations.RemoveField(
            model_name="funktionsergebnis",
            name="gap_begruendung_extern",
        ),
        migrations.RunPython(
            delete_gap_prompts, reverse_code=migrations.RunPython.noop
        ),
    ]
