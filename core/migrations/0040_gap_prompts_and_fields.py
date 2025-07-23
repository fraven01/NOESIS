from django.db import migrations, models


def add_gap_prompts(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    prompts = [
        (
            'gap_summary_internal',
            '**INTERNE GAP-ANALYSE**\n\n**Funktion/Unterfrage:** "{funktion} {unterfrage}"\n\n**Konflikt:**\n- Dokumenten-Analyse: {dokument_wert}\n- KI-Einschätzung: {ki_wert}\n- Manuelle Bewertung durch Prüfer: {manueller_wert}\n\n**Ursprüngliche KI-Begründung:**\n{ki_begruendung}\n\n**Deine Aufgabe:**\nFormuliere eine prägnante, technische Zusammenfassung des Gaps für die interne Akte. Begründe den Kern des Konflikts zwischen den Bewertungen.'
        ),
        (
            'gap_communication_external',
            '**RÜCKFRAGE AN FACHBEREICH**\n\n**Funktion/Unterfrage:** "{funktion}"\n\n**Kontext der automatisierten Prüfung:**\nUnsere automatisierte Analyse der eingereichten Unterlagen hat für diese Funktion ein Gap ergeben. Eine automatisierte Einschätzung kommt zu dem Ergebnis "{ki_wert}".\n\n**Deine Aufgabe:**\nFormuliere eine freundliche und kollaborative Rückfrage an den Fachbereich. Erkläre höflich, dass es hier eine Abweichung zur manuellen Prüfung gibt und bitte um eine kurze Überprüfung oder zusätzliche Erläuterung der Funktion, um das Missverständnis aufzuklären. Füge keine einleitung oder abschlußworte hinzu.'
        ),
    ]
    for name, text in prompts:
        Prompt.objects.update_or_create(name=name, defaults={'text': text, 'use_system_role': True})


def remove_gap_prompts(apps, schema_editor):
    Prompt = apps.get_model('core', 'Prompt')
    Prompt.objects.filter(name__in=['gap_summary_internal', 'gap_communication_external']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_alter_anlage2config_parser_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='funktionsergebnis',
            name='gap_begruendung_intern',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='funktionsergebnis',
            name='gap_begruendung_extern',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.RunPython(add_gap_prompts, reverse_code=remove_gap_prompts),
    ]
