import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ..base import NoesisTestCase
from ...models import BVProject, BVProjectFile

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("seed_db")]


class GapReportParentTests(NoesisTestCase):
    """Tests für den GAP-Bericht bei Anlage 1 ohne bzw. mit Vorgänger."""

    def setUp(self) -> None:  # noqa: D401
        super().setUp()
        self.user = User.objects.create_user("gapparent", password="pass")
        self.client.login(username="gapparent", password="pass")
        self.project = BVProject.objects.create(software_typen="A", beschreibung="x")

    def _create_file(self, parent=None, gap_summary=""):
        return BVProjectFile.objects.create(
            project=self.project,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.docx", b"data"),
            parent=parent,
            gap_summary=gap_summary,
        )

    def test_review_with_parent_renders_gap_section_without_edit_buttons(self):
        parent = self._create_file(gap_summary="Alt")
        child = self._create_file(parent=parent)
        url = reverse("projekt_file_edit_json", args=[child.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.context["gap_text"], "Alt")
        self.assertTrue(resp.context["has_parent"])
        soup = BeautifulSoup(resp.content, "html.parser")
        details = soup.find("details")
        self.assertIsNotNone(details)
        self.assertIn("GAP‑Bericht (Vorversion)", details.text)
        self.assertFalse(details.find_all("form"))
        self.assertFalse(details.find_all("button"))

    def test_review_without_parent_hides_gap_section(self):
        file = self._create_file()
        url = reverse("projekt_file_edit_json", args=[file.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.context["gap_text"], "")
        self.assertFalse(resp.context["has_parent"])
        soup = BeautifulSoup(resp.content, "html.parser")
        self.assertIsNone(soup.find("details"))
