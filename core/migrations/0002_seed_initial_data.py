# In der Datei: core/migrations/0002_seed_initial_data.py

from django.db import migrations

# Die Daten, die wir erstellen wollen.
# Sie können diese Liste jederzeit erweitern!
INITIAL_AREAS = {
    "work": {
        "name": "BV-Gutachten",
        "tiles": [
            {
                "slug": "new-bv-project",
                "name": "Neues Gutachten",
                "url_name": "new_bv_project",
                "icon": "bi-folder-plus",
            },
            {
                "slug": "bv-project-list",
                "name": "Alle Gutachten",
                "url_name": "bv_project_list",
                "icon": "bi-folder",
            },
            {
                "slug": "admin-dashboard",
                "name": "Admin",
                "url_name": "admin:index",
                "icon": "bi-gear",
            },
        ],
    },
    "personal": {
        "name": "Aufnahmen",
        "tiles": [
            {
                "slug": "recordings-list",
                "name": "Meine Aufnahmen",
                "url_name": "recordings_list",
                "icon": "bi-mic",
            },
        ],
    },
}


def create_initial_data(apps, schema_editor):
    """Erstellt die initialen Bereiche (Areas) und Kacheln (Tiles)."""
    # Wir holen uns die Modelle aus der Migration, nicht per direktem Import.
    Area = apps.get_model("core", "Area")
    Tile = apps.get_model("core", "Tile")
    User = apps.get_model("auth", "User")

    # Alle Benutzer abrufen, um ihnen Zugriff zu geben.
    all_users = User.objects.all()
    if not all_users.exists():
        print(
            "\nWARNUNG: Es wurden keine Benutzer gefunden. Kacheln werden erstellt, aber niemandem zugewiesen."
        )

    print("\n")  # Leerzeile für bessere Lesbarkeit
    for area_slug, area_data in INITIAL_AREAS.items():
        # Erstelle den Bereich oder hole ihn, falls er schon existiert.
        area, created = Area.objects.update_or_create(
            slug=area_slug, defaults={"name": area_data["name"]}
        )
        if created:
            print(f"  -> Bereich '{area.name}' wurde erstellt.")
        else:
            print(f"  -> Bereich '{area.name}' existierte bereits.")

        # Gib allen Benutzern Zugriff auf diesen Bereich.
        area.users.add(*all_users)

        # Erstelle die Kacheln für diesen Bereich.
        for tile_data in area_data["tiles"]:
            tile, created = Tile.objects.update_or_create(
                slug=tile_data["slug"],
                defaults={
                    "name": tile_data["name"],
                    "url_name": tile_data["url_name"],
                    "icon": tile_data["icon"],
                },
            )
            # Weise die Kachel dem aktuellen Bereich zu.
            tile.areas.add(area)
            # Gib allen Benutzern Zugriff auf diese Kachel.
            tile.users.add(*all_users)

            if created:
                print(f"    -> Kachel '{tile.name}' wurde erstellt.")
            else:
                print(f"    -> Kachel '{tile.name}' existierte bereits.")


class Migration(migrations.Migration):
    # Diese Migration muss nach der initialen Migration laufen.
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        # Hier rufen wir unsere Funktion auf.
        migrations.RunPython(create_initial_data),
    ]
