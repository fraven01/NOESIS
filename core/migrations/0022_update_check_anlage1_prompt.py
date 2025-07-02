from django.db import migrations


def update_prompt(apps, schema_editor):
    Prompt = apps.get_model("core", "Prompt")
    text = (
        "System: Du bist ein juristisch-technischer Prüf-Assistent für Systembeschreibungen.\n\n"
        "Frage 1: Extrahiere alle Unternehmen als Liste.\n"
        "Frage 2: Extrahiere alle Fachbereiche als Liste.\n"
        "IT-Landschaft: Fasse den Abschnitt zusammen, der die Einbettung in die IT-Landschaft beschreibt.\n"
        "Frage 3: Liste alle Hersteller und Produktnamen auf.\n"
        "Frage 4: Lege den Textblock als question4_raw ab.\n"
        "Frage 5: Fasse den Zweck des Systems in einem Satz.\n"
        "Frage 6: Extrahiere Web-URLs.\n"
        "Frage 7: Extrahiere ersetzte Systeme.\n"
        "Frage 8: Extrahiere Legacy-Funktionen.\n"
        "Frage 9: Lege den Text als question9_raw ab.\n"
        "Konsistenzprüfung und Stichworte. Gib ein JSON im vorgegebenen Schema zurück.\n\n"
    )
    obj, _ = Prompt.objects.get_or_create(name="check_anlage1")
    obj.text = text
    obj.save(update_fields=["text"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_bvprojectfile_question_review"),
    ]

    operations = [migrations.RunPython(update_prompt, migrations.RunPython.noop)]
