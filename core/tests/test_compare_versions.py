from .base import NoesisTestCase
from .test_general import *
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
import pytest

pytestmark = pytest.mark.usefixtures("seed_db")


class CompareVersionsAnlage1Tests(NoesisTestCase):
    def test_gap_and_diff_display(self):
        user = User.objects.create_user("u1", password="pass")
        self.client.login(username="u1", password="pass")
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        parent = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("p.txt", b"data"),
            analysis_json={"questions": {"1": {"answer": "alt"}}},
            question_review={"1": {"hinweis": "H"}},
        )
        current = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("c.txt", b"data"),
            parent=parent,
            analysis_json={"questions": {"1": {"answer": "neu"}}},
        )
        url = reverse("compare_versions", args=[current.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hinweis: H")
        self.assertContains(resp, "bg-warning/20")
        self.client.post(url, {"action": "negotiate"})
        current.refresh_from_db()
        self.assertTrue(current.verhandlungsfaehig)
