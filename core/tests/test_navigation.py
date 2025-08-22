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

    @staticmethod
    def _grant_access(user: User, areas: list[Area], tiles: list[Tile]) -> None:
        """Erteilt einem Benutzer Zugriff auf Bereiche und Tiles."""

        for area in areas:
            UserAreaAccess.objects.create(user=user, area=area)
        for tile in tiles:
            UserTileAccess.objects.create(user=user, tile=tile)

    @classmethod
    def setUpTestData(cls) -> None:
        """Legt Bereiche, Tiles und Nutzer für die Tests an."""

        cls.area_work = Area.objects.create(slug="work", name="Arbeitsbereich")
        cls.area_private = Area.objects.create(
            slug="personal", name="Privatbereich"
        )

        cls.tile_dashboard = Tile.objects.create(
            slug="dashboard", name="Dashboard", url_name="home"
        )
        cls.tile_dashboard.areas.add(cls.area_work)

        cls.tile_account = Tile.objects.create(
            slug="account-tile", name="Privatkachel", url_name="account"
        )
        cls.tile_account.areas.add(cls.area_private)

        cls.tile_hidden = Tile.objects.create(
            slug="hidden", name="Versteckt", url_name="home"
        )
        cls.tile_hidden.areas.add(cls.area_work)

        cls.user_alice = User.objects.create_user("alice", password="pw")
        cls._grant_access(cls.user_alice, [cls.area_work], [cls.tile_dashboard])

        cls.user_bob = User.objects.create_user("bob", password="pw")
        cls._grant_access(
            cls.user_bob,
            [cls.area_work, cls.area_private],
            [cls.tile_dashboard, cls.tile_account],
        )

        cls.user_carol = User.objects.create_user("carol", password="pw")
        cls._grant_access(cls.user_carol, [cls.area_work], [cls.tile_dashboard])

        cls.admin_group = Group.objects.create(name="Admin")
        cls.user_dave = User.objects.create_user("dave", password="pw")
        cls.user_dave.groups.add(cls.admin_group)
        cls._grant_access(cls.user_dave, [cls.area_work], [cls.tile_dashboard])

        cls.user_eve = User.objects.create_superuser("eve", "eve@example.com", "pw")
        cls._grant_access(cls.user_eve, [cls.area_work], [cls.tile_dashboard])

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

