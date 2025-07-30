from .test_general import *
from django.core.files.uploadedfile import SimpleUploadedFile

class GapNotesSaveTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("gapuser", password="pass")
        self.client.login(username="gapuser", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")

    def _create_file(self, nr):
        return BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=nr,
            upload=SimpleUploadedFile("a.docx", b"x"),
            text_content="",
        )

    def _post_and_check(self, url, pf, extra=None):
        data = {"gap_summary": "Ext", "gap_notiz": "Int"}
        if extra:
            data.update(extra)
        resp = self.client.post(url, data)
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        pf.refresh_from_db()
        self.assertEqual(pf.gap_summary, "Ext")
        self.assertEqual(pf.gap_notiz, "Int")

    def test_anlage1_gap_notes(self):
        pf = self._create_file(1)
        url = reverse("projekt_file_edit_json", args=[pf.pk])
        self._post_and_check(url, pf)

    def test_anlage2_gap_notes(self):
        pf = self._create_file(2)
        url = reverse("projekt_file_edit_json", args=[pf.pk])
        self._post_and_check(url, pf)

    def test_anlage3_gap_notes(self):
        pf = self._create_file(3)
        url = reverse("anlage3_file_review", args=[pf.pk])
        self._post_and_check(url, pf)

    def test_anlage4_gap_notes(self):
        pf = self._create_file(4)
        url = reverse("anlage4_review", args=[pf.pk])
        self._post_and_check(url, pf)

    def test_anlage5_gap_notes(self):
        ZweckKategorieA.objects.create(beschreibung="A")
        pf = self._create_file(5)
        url = reverse("anlage5_review", args=[pf.pk])
        self._post_and_check(url, pf)

    def test_anlage6_gap_notes(self):
        pf = self._create_file(6)
        url = reverse("anlage6_review", args=[pf.pk])
        self._post_and_check(url, pf, {"manual_reviewed": "on"})
