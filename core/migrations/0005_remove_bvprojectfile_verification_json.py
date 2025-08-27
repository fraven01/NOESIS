from django.db import migrations


def migrate_verification_json(apps, schema_editor):
    BVProjectFile = apps.get_model("core", "BVProjectFile")
    FunktionsErgebnis = apps.get_model("core", "FunktionsErgebnis")
    Anlage2Function = apps.get_model("core", "Anlage2Function")
    Anlage2SubQuestion = apps.get_model("core", "Anlage2SubQuestion")
    for pf in BVProjectFile.objects.exclude(verification_json=None).exclude(verification_json={}):
        vjson = pf.verification_json or {}
        for key, entry in vjson.items():
            if not isinstance(entry, dict):
                continue
            func_name = key
            sub_text = None
            if ":" in key:
                func_name, sub_text = [p.strip() for p in key.split(":", 1)]
            funktion = Anlage2Function.objects.filter(name=func_name).first()
            if not funktion:
                continue
            subquestion = None
            if sub_text:
                subquestion = Anlage2SubQuestion.objects.filter(
                    funktion=funktion, frage_text=sub_text
                ).first()
            kwargs = {
                "anlage_datei": pf,
                "funktion": funktion,
                "quelle": "ki",
                "technisch_verfuegbar": entry.get("technisch_verfuegbar"),
                "einsatz_bei_telefonica": entry.get("einsatz_bei_telefonica"),
                "zur_lv_kontrolle": entry.get("zur_lv_kontrolle"),
                "ki_beteiligung": entry.get("ki_beteiligt"),
                "ki_beteiligt_begruendung": entry.get("ki_beteiligt_begruendung"),
                "begruendung": entry.get("ki_begruendung"),
            }
            if subquestion:
                kwargs["subquestion"] = subquestion
            FunktionsErgebnis.objects.create(**kwargs)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_remove_bvprojectfile_manual_analysis_json"),
    ]

    operations = [
        migrations.RunPython(migrate_verification_json, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="bvprojectfile",
            name="verification_json",
        ),
    ]
