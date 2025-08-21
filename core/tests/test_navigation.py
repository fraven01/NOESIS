"""Tests für die Navigationsberechtigungen."""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse


class NavigationPermissionsTests(TestCase):
    """Überprüfung der Navigation abhängig von Benutzerrechten."""

    def setUp(self) -> None:
        """Initialisiert die benötigte Berechtigung."""
        self.permission = Permission.objects.get(codename="view_bvproject")

    def test_navigation_without_permission(self) -> None:
        """Ein Benutzer ohne Berechtigung sieht keinen Dashboard-Link."""
        user = User.objects.create_user(username="alice", password="password")
        self.client.login(username="alice", password="password")
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Dashboard")

    def test_navigation_with_permission(self) -> None:
        """Ein Benutzer mit Berechtigung sieht den Dashboard-Link."""
        user = User.objects.create_user(username="bob", password="password")
        user.user_permissions.add(self.permission)
        self.client.login(username="bob", password="password")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Dashboard")
