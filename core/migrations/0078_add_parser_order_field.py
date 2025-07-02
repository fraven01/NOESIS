from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0077_convert_text_phrase_strings"),
        ("core", "0077_alter_anlage2function_detection_phrases_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="anlage2config",
            name="parser_order",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("table_first", "Zuerst Tabelle"),
                    ("text_first", "Zuerst Text"),
                ],
                default="table_first",
            ),
        ),
    ]
