from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import TestCase
from django.core.files.base import ContentFile
from unittest.mock import patch

from .models import BVProject, BVProjectFile
from .llm_tasks import classify_system



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

    @patch("core.llm_tasks.query_llm")
    def test_classify_system(self, mock_query):
        mock_query.return_value = '{"type": "test"}'
        pf = BVProjectFile.objects.create(
            project=self.p1,
            category="anlage1",
            file=ContentFile("demo", name="a1.txt"),
        )
        result = classify_system(self.p1.id)
        self.assertEqual(result["type"], "test")
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.system_classification["type"], "test")


