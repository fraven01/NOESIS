from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from .test_general import NoesisTestCase, create_project
from ..models import BVProjectFile


class CompareVersionsAnlage1Tests(NoesisTestCase):
    """Tests für den Versionsvergleich von Anlage 1."""

    def setUp(self):
        self.client.login(username=self.superuser.username, password="pass")
        self.project = create_project(["A"], beschreibung="x")
        self.parent = BVProjectFile.objects.create(
            project=self.project,
            anlage_nr=1,
            upload=SimpleUploadedFile("alt.txt", b"data"),
            question_review={"1": {"hinweis": "H", "vorschlag": "V"}},
        )
        self.current = BVProjectFile.objects.create(
            project=self.project,
            anlage_nr=1,
            upload=SimpleUploadedFile("neu.txt", b"data"),
            parent=self.parent,
        )

    def test_add_gap_copies_notes(self):
        url = reverse("compare_versions", args=[self.current.pk])
        resp = self.client.post(url, {"action": "add_gap", "question": "1"})
        self.assertEqual(resp.status_code, 204)
        self.current.refresh_from_db()
        self.assertEqual(
            self.current.question_review["1"], {"hinweis": "H", "vorschlag": "V"}
        )

    def test_negotiable_sets_ok(self):
        url = reverse("compare_versions", args=[self.current.pk])
        resp = self.client.post(url, {"action": "negotiable", "question": "1"})
        self.assertEqual(resp.status_code, 204)
        self.current.refresh_from_db()
        self.assertTrue(self.current.question_review["1"]["ok"])
