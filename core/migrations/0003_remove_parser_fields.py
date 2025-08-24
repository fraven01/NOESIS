from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_delete_formatbparserrule"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="anlage2config",
            name="parser_mode",
        ),
        migrations.RemoveField(
            model_name="anlage2config",
            name="parser_order",
        ),
        migrations.RemoveField(
            model_name="bvprojectfile",
            name="parser_mode",
        ),
        migrations.RemoveField(
            model_name="bvprojectfile",
            name="parser_order",
        ),
        migrations.AddField(
            model_name="anlage2config",
            name="default_parser",
            field=models.CharField(
                choices=[("exact", "ExactParser"), ("table", "TableParser")],
                default="exact",
                max_length=20,
            ),
        ),
    ]
