from django.db import migrations

FIELD_RENAME = {
    "technisch_verfuegbar": "technisch_vorhanden",
    "einsatz_telefonica": "einsatz_bei_telefonica",
}

def _clean_item(item):
    if not isinstance(item, dict):
        return {}
    cleaned = {}
    for k, v in item.items():
        if isinstance(v, dict) and "value" in v:
            v = v["value"]
        cleaned[FIELD_RENAME.get(k, k)] = v
    subs = cleaned.get("subquestions")
    if isinstance(subs, list):
        new_subs = []
        for sub in subs:
            if not isinstance(sub, dict):
                continue
            sub_clean = {}
            for k, v in sub.items():
                if isinstance(v, dict) and "value" in v:
                    v = v["value"]
                sub_clean[FIELD_RENAME.get(k, k)] = v
            new_subs.append(sub_clean)
        cleaned["subquestions"] = new_subs
    return cleaned


def normalize_analysis_json(apps, schema_editor):
    BVProjectFile = apps.get_model("core", "BVProjectFile")
    for pf in BVProjectFile.objects.exclude(analysis_json__isnull=True):
        data = pf.analysis_json
        if not isinstance(data, dict):
            continue
        changed = False
        funcs = data.get("functions")
        if isinstance(funcs, dict) and "value" in funcs:
            funcs = funcs["value"]
            changed = True
        elif funcs is None and isinstance(data.get("table_functions"), dict):
            table = data.pop("table_functions")
            funcs = []
            for name, val in table.items():
                if isinstance(val, dict):
                    funcs.append({"name": name, **val})
            changed = True
        if not isinstance(funcs, list):
            funcs = []
        new_funcs = []
        for item in funcs:
            if not isinstance(item, dict):
                continue
            cleaned = _clean_item(item)
            new_funcs.append(cleaned)
            if cleaned != item:
                changed = True
        data["functions"] = new_funcs
        if "table_functions" in data:
            data.pop("table_functions", None)
            changed = True
        if changed:
            pf.analysis_json = data
            pf.save(update_fields=["analysis_json"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_delete_formatbparserrule"),
    ]

    operations = [
        migrations.RunPython(normalize_analysis_json, migrations.RunPython.noop),
    ]

