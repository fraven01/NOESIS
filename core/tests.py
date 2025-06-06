from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import TestCase


from .models import BVProject
from .docx_utils import extract_text
from pathlib import Path
from tempfile import NamedTemporaryFile
from docx import Document

from django.core.files.uploadedfile import SimpleUploadedFile
from .models import BVProject, BVProjectFile
from .workflow import set_project_status
from .llm_tasks import classify_system, check_anlage2
from .reporting import generate_gap_analysis, generate_management_summary
from unittest.mock import patch




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



class DocxExtractTests(TestCase):
    def test_extract_text(self):
        doc = Document()
        doc.add_paragraph("Das ist ein Test")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        try:
            text = extract_text(Path(tmp.name))
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        self.assertIn("Das ist ein Test", text)

class BVProjectFileTests(TestCase):
    def test_create_project_with_files(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        for i in range(1, 4):
            f = SimpleUploadedFile(f"f{i}.txt", b"data")
            BVProjectFile.objects.create(
                projekt=projekt,
                anlage_nr=i,
                upload=f,
                text_content="data",
            )
        self.assertEqual(projekt.anlagen.count(), 3)
        self.assertListEqual(list(projekt.anlagen.values_list("anlage_nr", flat=True)), [1, 2, 3])


class ProjektFileUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user", password="pass")
        self.client.login(username="user", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")

    def test_docx_upload_extracts_text(self):
        doc = Document()
        doc.add_paragraph("Docx Inhalt")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("t.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)

        url = reverse("projekt_file_upload", args=[self.projekt.pk])
        resp = self.client.post(
            url,
            {"anlage_nr": 1, "upload": upload, "manual_comment": ""},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 302)
        file_obj = self.projekt.anlagen.first()
        self.assertIsNotNone(file_obj)
        self.assertIn("Docx Inhalt", file_obj.text_content)


class WorkflowTests(TestCase):
    def test_default_status(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.assertEqual(projekt.status, BVProject.STATUS_NEW)

    def test_set_project_status(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        set_project_status(projekt, BVProject.STATUS_CLASSIFIED)
        projekt.refresh_from_db()
        self.assertEqual(projekt.status, BVProject.STATUS_CLASSIFIED)

    def test_invalid_status(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        with self.assertRaises(ValueError):
            set_project_status(projekt, "XXX")

    def test_set_project_status_new_states(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        for status in [
            BVProject.STATUS_IN_PRUEFUNG_ANLAGE_X,
            BVProject.STATUS_FB_IN_PRUEFUNG,
            BVProject.STATUS_ENDGEPRUEFT,
        ]:
            set_project_status(projekt, status)
            projekt.refresh_from_db()
            self.assertEqual(projekt.status, status)


class LLMTasksTests(TestCase):
    def test_classify_system(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testtext",
        )
        with patch("core.llm_tasks.query_llm", return_value='{"kategorie":"X","begruendung":"ok"}'):
            data = classify_system(projekt.pk)
        projekt.refresh_from_db()
        self.assertEqual(projekt.classification_json["kategorie"], "X")
        self.assertEqual(projekt.status, BVProject.STATUS_CLASSIFIED)
        self.assertEqual(data["kategorie"], "X")

    def test_check_anlage2(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Anlagetext",
        )
        with patch("core.llm_tasks.query_llm", return_value='{"ok": true}'):
            data = check_anlage2(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertTrue(file_obj.analysis_json["ok"])
        self.assertTrue(data["ok"])


class ReportingTests(TestCase):
    def test_gap_analysis_file_created(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testtext",
            analysis_json={"ok": True},
        )
        path = generate_gap_analysis(projekt)
        try:
            self.assertTrue(path.exists())
        finally:
            path.unlink(missing_ok=True)

    def test_management_summary_includes_comment(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testtext",
            manual_comment="Hinweis",
        )
        path = generate_management_summary(projekt)
        try:
            doc = Document(path)
            text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn("Hinweis", text)
        finally:
            path.unlink(missing_ok=True)

    def test_manual_analysis_overrides(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testtext",
            analysis_json={"foo": "orig"},
            manual_analysis_json={"foo": "manual"},
        )
        path1 = generate_gap_analysis(projekt)
        try:
            doc = Document(path1)
            text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn('"foo": "manual"', text)
            self.assertNotIn('"foo": "orig"', text)
        finally:
            path1.unlink(missing_ok=True)

        path2 = generate_management_summary(projekt)
        try:
            doc = Document(path2)
            text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn('"foo": "manual"', text)
            self.assertNotIn('"foo": "orig"', text)
        finally:
            path2.unlink(missing_ok=True)



