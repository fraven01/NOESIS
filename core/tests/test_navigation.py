"""Tests für die Sidebar-Navigation."""

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from core.models import (
    Area,
    Tile,
    UserAreaAccess,
    UserTileAccess,
)


class NavigationSidebarTests(TestCase):
    """Überprüfung der sichtbaren Bereiche, Tiles und Admin-Links."""

    def setUp(self) -> None:
        """Legt Bereiche und Tiles für die Tests an."""

        self.area_work = Area.objects.create(slug="work", name="Arbeitsbereich")
        self.area_private = Area.objects.create(slug="personal", name="Privatbereich")

        self.tile_dashboard = Tile.objects.create(
            slug="dashboard", name="Dashboard", url_name="home"
        )
        self.tile_dashboard.areas.add(self.area_work)

        self.tile_account = Tile.objects.create(
            slug="account-tile", name="Privatkachel", url_name="account"
        )
        self.tile_account.areas.add(self.area_private)

        self.tile_hidden = Tile.objects.create(
            slug="hidden", name="Versteckt", url_name="home"
        )
        self.tile_hidden.areas.add(self.area_work)

    def _grant_access(self, user: User, areas: list[Area], tiles: list[Tile]) -> None:
        """Erteilt einem Benutzer Zugriff auf Bereiche und Tiles."""

        for area in areas:
            UserAreaAccess.objects.create(user=user, area=area)
        for tile in tiles:
            UserTileAccess.objects.create(user=user, tile=tile)

    def test_sidebar_single_area_tiles_only(self) -> None:
        """Bei genau einem Bereich werden nur die Tiles angezeigt."""

        user = User.objects.create_user("alice", password="pw")
        self._grant_access(user, [self.area_work], [self.tile_dashboard])
        self.client.login(username="alice", password="pw")

        response = self.client.get(reverse("account"))

        self.assertContains(response, "Dashboard")
        self.assertNotContains(response, self.area_work.name)
        self.assertNotContains(response, self.tile_account.name)
        self.assertNotContains(response, self.tile_hidden.name)

    def test_sidebar_multiple_areas(self) -> None:
        """Mehrere Bereiche werden mit Überschriften dargestellt."""

        user = User.objects.create_user("bob", password="pw")
        self._grant_access(
            user,
            [self.area_work, self.area_private],
            [self.tile_dashboard, self.tile_account],
        )
        self.client.login(username="bob", password="pw")

        response = self.client.get(reverse("account"))

        self.assertContains(response, self.area_work.name)
        self.assertContains(response, self.area_private.name)
        self.assertContains(response, "Dashboard")
        self.assertContains(response, "Privatkachel")
        self.assertNotContains(response, self.tile_hidden.name)

    def test_no_admin_links_for_regular_user(self) -> None:
        """Ohne Sonderrechte erscheinen keine Admin-Links."""

        user = User.objects.create_user("carol", password="pw")
        self._grant_access(user, [self.area_work], [self.tile_dashboard])
        self.client.login(username="carol", password="pw")

        response = self.client.get(reverse("account"))

        self.assertNotContains(response, "Projekt-Admin")
        self.assertNotContains(response, "System-Admin")

    def test_project_admin_link_for_admin_group(self) -> None:
        """Mitglied der Admin-Gruppe sieht Projekt-Admin-Link."""

        admin_group = Group.objects.create(name="Admin")
        user = User.objects.create_user("dave", password="pw")
        user.groups.add(admin_group)
        self._grant_access(user, [self.area_work], [self.tile_dashboard])
        self.client.login(username="dave", password="pw")

        response = self.client.get(reverse("account"))

        self.assertContains(response, "Projekt-Admin")
        self.assertNotContains(response, "System-Admin")

    def test_system_admin_link_for_superuser(self) -> None:
        """Superuser sieht Projekt- und System-Admin-Link."""

        user = User.objects.create_superuser("eve", "eve@example.com", "pw")
        self._grant_access(user, [self.area_work], [self.tile_dashboard])
        self.client.login(username="eve", password="pw")

        response = self.client.get(reverse("account"))

        self.assertContains(response, "Projekt-Admin")
        self.assertContains(response, "System-Admin")

