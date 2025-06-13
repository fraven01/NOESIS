from django.db import migrations


def create_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    Prompt.objects.get_or_create(
        name="anlage2_feature_justification",
        defaults={
            "text": (
                "Du bist ein Experte f\u00fcr IT-Systeme und Software-Architektur. "
                "Begr\u00fcnde in ein bis zwei S\u00e4tzen, ob und warum die Software "
                "'{software_name}' typischerweise die Funktion oder Eigenschaft "
                "'{function_name}' besitzt."
            )
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0049_anlage2config_enforce_subquestion_override"),
    ]

    operations = [
        migrations.RunPython(create_prompt, migrations.RunPython.noop),
    ]
