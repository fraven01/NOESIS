from django.contrib.auth.models import Group, User
from django.urls import reverse

from .test_general import NoesisTestCase
from ..models import Area, Tile, UserTileAccess


class AdminNavigationTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("navuser", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="navuser", password="pass")
        area, _ = Area.objects.get_or_create(slug="work", defaults={"name": "Work"})
        self.tile = Tile.objects.create(slug="admin_projects", name="Proj", url_name="admin_projects")
        self.tile.areas.add(area)

    def test_link_hidden_without_tile(self):
        resp = self.client.get(reverse("admin_projects"))
        self.assertNotContains(resp, "Projekt-Liste")

    def test_link_visible_with_tile(self):
        UserTileAccess.objects.create(user=self.user, tile=self.tile)
        resp = self.client.get(reverse("admin_projects"))
        self.assertContains(resp, "Projekt-Liste")

