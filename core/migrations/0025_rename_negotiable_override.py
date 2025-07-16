from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0024_anlage2functionresult_is_negotiable_override"),
    ]

    operations = [
        migrations.RenameField(
            model_name="anlage2functionresult",
            old_name="is_negotiable_override",
            new_name="is_negotiable_manual_override",
        ),
    ]
