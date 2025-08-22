"""Tests für die Sidebar-Navigation."""

from django.contrib.auth.models import Group, User
from django.urls import reverse

from .base import NoesisTestCase

from core.models import (
    Area,
    Tile,
    UserAreaAccess,
    UserTileAccess,
)
from ..views import get_user_tiles


class NavigationSidebarTests(NoesisTestCase):
    """Überprüfung der sichtbaren Bereiche, Tiles und Admin-Links."""

    @staticmethod
    def _grant_access(user: User, areas: list[Area], tiles: list[Tile]) -> None:
        """Erteilt einem Benutzer Zugriff auf Bereiche und Tiles."""

        for area in areas:
            UserAreaAccess.objects.create(user=user, area=area)
        for tile in tiles:
            UserTileAccess.objects.create(user=user, tile=tile)

    def setUp(self) -> None:
        """Legt Bereiche, Tiles und Nutzer für die Tests an."""
        self.area_work = Area.objects.create(slug="work-test", name="Arbeitsbereich")
        self.area_private = Area.objects.create(
            slug="personal-test", name="Privatbereich"
        )

        self.tile_dashboard = Tile.objects.create(
            slug="dashboard-test", name="Dashboard", url_name="home"
        )
        self.tile_dashboard.areas.add(self.area_work)
        self.tile_account = Tile.objects.create(
            slug="account-tile-test", name="Privatkachel", url_name="account"
        )
        self.tile_account.areas.add(self.area_private)

        self.tile_hidden = Tile.objects.create(
            slug="hidden-test", name="Versteckt", url_name="home"
        )
        self.tile_hidden.areas.add(self.area_work)

        self.user_alice = User.objects.create_user("alice", password="pw")
        self._grant_access(self.user_alice, [self.area_work], [self.tile_dashboard])

        self.user_bob = User.objects.create_user("bob", password="pw")
        self._grant_access(
            self.user_bob,
            [self.area_work, self.area_private],
            [self.tile_dashboard, self.tile_account],
        )

        self.user_carol = User.objects.create_user("carol", password="pw")
        self._grant_access(self.user_carol, [self.area_work], [self.tile_dashboard])

        self.admin_group = Group.objects.create(name="admin")
        self.user_dave = User.objects.create_user("dave", password="pw")
        self.user_dave.groups.add(self.admin_group)
        self._grant_access(self.user_dave, [self.area_work], [self.tile_dashboard])

        self.user_eve = User.objects.create_superuser("eve", "eve@example.com", "pw")
        self._grant_access(self.user_eve, [self.area_work], [self.tile_dashboard])

    def test_get_user_tiles(self) -> None:
        """Gibt die zugänglichen Bereiche und Tiles zurück."""

        areas, tiles = get_user_tiles(self.user_bob, self.area_work.slug)

        self.assertEqual(len(areas), 2)
        self.assertCountEqual(areas, [self.area_work, self.area_private])
        self.assertEqual(len(tiles), 1)
        self.assertListEqual(tiles, [self.tile_dashboard])

    def test_sidebar_single_area_tiles_only(self) -> None:
        """Bei genau einem Bereich werden nur die Tiles angezeigt."""

        self.client.force_login(self.user_alice)

        response = self.client.get(reverse("account"))

        self.assertContains(response, "Dashboard")
        self.assertNotContains(response, self.area_work.name)
        self.assertNotContains(response, self.tile_account.name)
        self.assertNotContains(response, self.tile_hidden.name)

    def test_sidebar_multiple_areas(self) -> None:
        """Mehrere Bereiche werden mit Überschriften dargestellt."""

        self.client.force_login(self.user_bob)

        response = self.client.get(reverse("account"))

        self.assertContains(response, self.area_work.name)
        self.assertContains(response, self.area_private.name)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Privatkachel")
        self.assertNotContains(response, self.tile_hidden.name)

    def test_no_admin_links_for_regular_user(self) -> None:
        """Ohne Sonderrechte erscheinen keine Admin-Links."""

        self.client.force_login(self.user_carol)

        response = self.client.get(reverse("account"))

        self.assertNotContains(response, "Projekt-Admin")
        self.assertNotContains(response, "System-Admin")

    def test_project_admin_link_for_admin_group(self) -> None:
        """Mitglied der Admin-Gruppe sieht Projekt-Admin-Link."""

        self.client.force_login(self.user_dave)

        response = self.client.get(reverse("account"))

        self.assertContains(response, "Projekt-Admin")
        self.assertNotContains(response, "System-Admin")

    def test_system_admin_link_for_superuser(self) -> None:
        """Superuser sieht Projekt- und System-Admin-Link."""

        self.client.force_login(self.user_eve)

        response = self.client.get(reverse("account"))

        self.assertContains(response, "Projekt-Admin")
        self.assertContains(response, "System-Admin")
        self.assertContains(response, reverse("admin:auth_user_changelist"))
        self.assertContains(response, reverse("admin:auth_group_changelist"))

