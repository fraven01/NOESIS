from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import TestCase

from .models import BVProject
from .workflow import change_project_status



class AdminProjectsTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("admin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="admin", password="pass")

        self.p1 = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.p2 = BVProject.objects.create(software_typen="B", beschreibung="y")

    def test_delete_selected_projects(self):
        url = reverse("admin_projects")
        resp = self.client.post(url, {"delete": [self.p1.id]})
        self.assertRedirects(resp, url)
        self.assertFalse(BVProject.objects.filter(id=self.p1.id).exists())
        self.assertTrue(BVProject.objects.filter(id=self.p2.id).exists())


class ProjectStatusTests(TestCase):
    def test_default_status(self):
        p = BVProject.objects.create(software_typen="X", beschreibung="")
        self.assertEqual(p.status, BVProject.NEW)

    def test_change_status_helper(self):
        p = BVProject.objects.create(software_typen="X", beschreibung="")
        change_project_status(p, BVProject.CLASSIFIED)
        p.refresh_from_db()
        self.assertEqual(p.status, BVProject.CLASSIFIED)


