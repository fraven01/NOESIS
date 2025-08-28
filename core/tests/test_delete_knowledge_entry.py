from django.contrib.auth import get_user_model
from django.urls import reverse

from .base import NoesisTestCase
from ..models import BVProject, SoftwareKnowledge, ProjectStatus


class DeleteKnowledgeEntryTests(NoesisTestCase):
    """Tests für das Löschen eines SoftwareKnowledge-Eintrags."""

    def setUp(self):
        """Legt ein Projekt, einen Benutzer und einen Knowledge-Eintrag an."""
        self.status = ProjectStatus.objects.create(
            name="Offen", key="offen", ordering=0, is_default=True
        )
        self.project = BVProject.objects.create(title="P1", status=self.status)
        self.user = get_user_model().objects.create_user(
            username="user", password="pass", is_staff=True
        )
        self.knowledge = SoftwareKnowledge.objects.create(
            project=self.project, software_name="Tool"
        )

    def test_delete_entry_removes_object(self):
        """Berechtigter Benutzer kann einen Knowledge-Eintrag löschen."""
        self.client.login(username="user", password="pass")
        url = reverse("delete_knowledge_entry", args=[self.knowledge.pk])
        response = self.client.post(url)
        self.assertRedirects(
            response,
            reverse("projekt_detail", args=[self.project.pk]),
        )
        self.assertFalse(
            SoftwareKnowledge.objects.filter(pk=self.knowledge.pk).exists()
        )

    def test_delete_entry_requires_permission(self):
        """Unberechtigter Benutzer erhält einen 403-Status."""
        other = get_user_model().objects.create_user(username="other", password="pass")
        self.client.login(username="other", password="pass")
        url = reverse("delete_knowledge_entry", args=[self.knowledge.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            SoftwareKnowledge.objects.filter(pk=self.knowledge.pk).exists()
        )
