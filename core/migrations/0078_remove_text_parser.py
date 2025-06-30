from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0077_convert_text_phrase_strings"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="anlage2function",
            name="detection_phrases",
        ),
        migrations.RemoveField(
            model_name="anlage2subquestion",
            name="detection_phrases",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="parser_mode",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_technisch_verfuegbar_true",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_technisch_verfuegbar_false",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_einsatz_telefonica_true",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_einsatz_telefonica_false",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_zur_lv_kontrolle_true",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_zur_lv_kontrolle_false",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_ki_beteiligung_true",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="text_ki_beteiligung_false",
        ),
        migrations.DeleteModel(
            name="Anlage2GlobalPhrase",
        ),
    ]
