"""Tests für die Sidebar-Navigation."""

from django.urls import reverse
from django.contrib.auth.models import Group

import pytest

from core.models import Area, Tile, UserAreaAccess, UserTileAccess
from ...views import get_user_tiles

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def navigation_setup(user_factory, area_factory, tile_factory):
    """Erzeugt Bereiche, Tiles und Nutzer mit Zugriffsrechten."""

    area_work = area_factory(slug="work-test", name="Arbeitsbereich")
    area_private = area_factory(slug="personal-test", name="Privatbereich")

    tile_dashboard = tile_factory(
        slug="dashboard-test", name="Dashboard", url_name="home", areas=[area_work]
    )
    tile_account = tile_factory(
        slug="account-tile-test",
        name="Privatkachel",
        url_name="account",
        areas=[area_private],
    )
    tile_hidden = tile_factory(
        slug="hidden-test", name="Versteckt", url_name="home", areas=[area_work]
    )

    def grant_access(user, areas, tiles):
        for area in areas:
            UserAreaAccess.objects.create(user=user, area=area)
        for tile in tiles:
            UserTileAccess.objects.create(user=user, tile=tile)

    user_alice = user_factory(username="alice")
    grant_access(user_alice, [area_work], [tile_dashboard])

    user_bob = user_factory(username="bob")
    grant_access(user_bob, [area_work, area_private], [tile_dashboard, tile_account])

    user_carol = user_factory(username="carol")
    grant_access(user_carol, [area_work], [tile_dashboard])

    admin_group = Group.objects.create(name="admin")
    user_dave = user_factory(username="dave")
    user_dave.groups.add(admin_group)
    grant_access(user_dave, [area_work], [tile_dashboard])

    user_eve = user_factory(username="eve", is_superuser=True, is_staff=True)
    grant_access(user_eve, [area_work], [tile_dashboard])

    return {
        "area_work": area_work,
        "area_private": area_private,
        "tile_dashboard": tile_dashboard,
        "tile_account": tile_account,
        "tile_hidden": tile_hidden,
        "user_alice": user_alice,
        "user_bob": user_bob,
        "user_carol": user_carol,
        "user_dave": user_dave,
        "user_eve": user_eve,
    }


def test_get_user_tiles(navigation_setup):
    """Gibt die zugänglichen Bereiche und Tiles zurück."""

    area_work = navigation_setup["area_work"]
    area_private = navigation_setup["area_private"]
    tile_dashboard = navigation_setup["tile_dashboard"]
    user_bob = navigation_setup["user_bob"]

    areas, tiles = get_user_tiles(user_bob, area_work.slug)

    assert len(areas) == 2
    assert set(areas) == {area_work, area_private}
    assert len(tiles) == 1
    assert tiles == [tile_dashboard]


def test_sidebar_single_area_tiles_only(client, navigation_setup):
    """Bei genau einem Bereich werden nur die Tiles angezeigt."""

    client.force_login(navigation_setup["user_alice"])

    response = client.get(reverse("account"))
    content = response.content.decode()

    assert "Dashboard" in content
    assert navigation_setup["area_work"].name not in content
    assert navigation_setup["tile_account"].name not in content
    assert navigation_setup["tile_hidden"].name not in content


def test_sidebar_multiple_areas(client, navigation_setup):
    """Mehrere Bereiche werden mit Überschriften dargestellt."""

    client.force_login(navigation_setup["user_bob"])

    response = client.get(reverse("account"))
    content = response.content.decode()

    assert navigation_setup["area_work"].name in content
    assert navigation_setup["area_private"].name in content
    assert "Dashboard" in content
    assert "Privatkachel" in content
    assert navigation_setup["tile_hidden"].name not in content


def test_no_admin_links_for_regular_user(client, navigation_setup):
    """Ohne Sonderrechte erscheinen keine Admin-Links."""

    client.force_login(navigation_setup["user_carol"])

    response = client.get(reverse("account"))
    content = response.content.decode()

    assert "Projekt-Admin" not in content
    assert "System-Admin" not in content


def test_project_admin_link_for_admin_group(client, navigation_setup):
    """Mitglied der Admin-Gruppe sieht Projekt-Admin-Link."""

    client.force_login(navigation_setup["user_dave"])

    response = client.get(reverse("account"))
    content = response.content.decode()

    assert "Projekt-Admin" in content
    assert "System-Admin" not in content


def test_system_admin_link_for_superuser(client, navigation_setup):
    """Superuser sieht Projekt- und System-Admin-Link."""

    client.force_login(navigation_setup["user_eve"])

    response = client.get(reverse("account"))
    content = response.content.decode()

    assert "Projekt-Admin" in content
    assert "System-Admin" in content
    assert reverse("admin:auth_user_changelist") in content
    assert reverse("admin:auth_group_changelist") in content
