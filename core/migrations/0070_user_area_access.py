from django.db import migrations, models
from django.conf import settings

class Migration(migrations.Migration):

    dependencies = [
        ("core", "0067_remove_tile_bereich_tile_areas_alter_area_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserAreaAccess",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("user", models.ForeignKey(on_delete=models.CASCADE, to=settings.AUTH_USER_MODEL)),
                ("area", models.ForeignKey(on_delete=models.CASCADE, to="core.area")),
            ],
            options={"unique_together": {("user", "area")}},
        ),
        migrations.AddField(
            model_name="area",
            name="users",
            field=models.ManyToManyField(blank=True, help_text="Benutzer mit Zugriff auf diesen Bereich.", related_name="areas", through="core.UserAreaAccess", to=settings.AUTH_USER_MODEL),
        ),
    ]
