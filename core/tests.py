from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import TestCase


from django.apps import apps
from .models import (
    BVProject,
    BVProjectFile,
    Prompt,
    LLMConfig,
    Tile,
    UserTileAccess,
)
from .docx_utils import extract_text
from pathlib import Path
from tempfile import NamedTemporaryFile
from docx import Document

from django.core.files.uploadedfile import SimpleUploadedFile
from .workflow import set_project_status
from .llm_tasks import (
    classify_system,
    check_anlage1,
    check_anlage2,
    get_prompt,
    generate_gutachten,
)
from .reporting import generate_gap_analysis, generate_management_summary
from unittest.mock import patch
from django.test import override_settings
import json





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

    def test_delete_single_project(self):
        url = reverse("admin_project_delete", args=[self.p2.id])
        resp = self.client.post(url)
        self.assertRedirects(resp, reverse("admin_projects"))
        self.assertFalse(BVProject.objects.filter(id=self.p2.id).exists())

    def test_delete_single_requires_post(self):
        url = reverse("admin_project_delete", args=[self.p1.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(BVProject.objects.filter(id=self.p1.id).exists())



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
        self.assertEqual(projekt.classification_json["kategorie"]["value"], "X")
        self.assertEqual(projekt.status, BVProject.STATUS_CLASSIFIED)
        self.assertEqual(data["kategorie"]["value"], "X")

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
        self.assertTrue(file_obj.analysis_json["ok"]["value"])
        self.assertTrue(data["ok"]["value"])

    def test_check_anlage1_new_schema(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )
        expected = {
            "task": "check_anlage1",
            "version": 1,
            "anlage": 1,
            "companies": {"value": ["ACME"], "editable": True},
            "departments": {"value": ["IT"], "editable": True},
            "it_integration_summary": {"value": "Summe", "editable": True},
            "vendors": {"value": [], "editable": True},
            "question4_raw": {"value": "raw", "editable": False},
            "purpose_summary": {"value": "Zweck", "editable": True},
            "purpose_missing": {"value": False, "editable": True},
            "documentation_links": {"value": [], "editable": True},
            "replaced_systems": {"value": [], "editable": True},
            "legacy_functions": {"value": [], "editable": True},
            "question9_raw": {"value": "", "editable": True},
            "inconsistencies": {"value": [], "editable": True},
            "keywords": {"value": [], "editable": True},
            "plausibility_score": {"value": 0.5, "editable": True},
            "manual_comments": {"value": {}, "editable": True},
        }
        reply = json.dumps(expected)
        with patch("core.llm_tasks.query_llm", return_value=reply):
            data = check_anlage1(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=1)
        self.assertEqual(file_obj.analysis_json, expected)
        self.assertEqual(data, expected)

    def test_generate_gutachten_twice_replaces_file(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        first = generate_gutachten(projekt.pk, text="Alt")
        second = generate_gutachten(projekt.pk, text="Neu")
        try:
            self.assertTrue(second.exists())
            self.assertNotEqual(first, second)
            self.assertFalse(first.exists())
        finally:
            second.unlink(missing_ok=True)


class PromptTests(TestCase):
    def test_get_prompt_returns_default(self):
        self.assertEqual(get_prompt("unknown", "foo"), "foo")

    def test_get_prompt_returns_db_value(self):
        p, _ = Prompt.objects.get_or_create(name="classify_system", defaults={"text": "orig"})
        p.text = "DB"
        p.save()
        self.assertEqual(get_prompt("classify_system", "x"), "DB")


class AdminPromptsViewTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("padmin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="padmin", password="pass")
        self.prompt = Prompt.objects.create(name="p1", text="orig")

    def test_update_prompt(self):
        url = reverse("admin_prompts")
        resp = self.client.post(url, {"pk": self.prompt.id, "text": "neu", "action": "save"})
        self.assertRedirects(resp, url)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.text, "neu")

    def test_delete_prompt(self):
        url = reverse("admin_prompts")
        resp = self.client.post(url, {"pk": self.prompt.id, "action": "delete"})
        self.assertRedirects(resp, url)
        self.assertFalse(Prompt.objects.filter(id=self.prompt.id).exists())


class ReportingTests(TestCase):
    def test_gap_analysis_file_created(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testtext",
            analysis_json={"ok": {"value": True, "editable": True}},
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
            analysis_json={"foo": {"value": "orig", "editable": True}},
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


class ProjektFileCheckViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user2", password="pass")
        self.client.login(username="user2", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )

    def test_file_check_endpoint_saves_json(self):
        url = reverse("projekt_file_check", args=[self.projekt.pk, 1])
        expected = {"task": "check_anlage1"}
        with patch("core.llm_tasks.query_llm", return_value=json.dumps(expected)):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        file_obj = self.projekt.anlagen.get(anlage_nr=1)
        self.assertEqual(file_obj.analysis_json, expected)

    def test_file_check_pk_endpoint_saves_json(self):
        file_obj = self.projekt.anlagen.get(anlage_nr=1)
        url = reverse("projekt_file_check_pk", args=[file_obj.pk])
        expected = {"task": "check_anlage1"}
        with patch("core.llm_tasks.query_llm", return_value=json.dumps(expected)):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        file_obj.refresh_from_db()
        self.assertEqual(file_obj.analysis_json, expected)


class ProjektFileJSONEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user3", password="pass")
        self.client.login(username="user3", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
            analysis_json={"old": {"value": True, "editable": True}},
        )

    def test_edit_json_updates_and_reports(self):
        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.post(
            url,
            {
                "analysis_json": "{\"new\": 1}",
                "manual_analysis_json": "{\"manual\": 2}",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.file.refresh_from_db()
        self.assertEqual(self.file.analysis_json["new"], 1)
        self.assertEqual(self.file.manual_analysis_json["manual"], 2)
        path = generate_gap_analysis(self.projekt)
        try:
            doc = Document(path)
            text = "\n".join(p.text for p in doc.paragraphs)
            self.assertIn('"manual": 2', text)
            self.assertNotIn('"old": true', text.lower())
        finally:
            path.unlink(missing_ok=True)

    def test_invalid_json_shows_error(self):
        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.post(
            url,
            {"analysis_json": "{", "manual_analysis_json": "{}"},
        )
        self.assertEqual(resp.status_code, 200)
        self.file.refresh_from_db()
        self.assertEqual(self.file.analysis_json, {"old": {"value": True, "editable": True}})


class ProjektGutachtenViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("guser", password="pass")
        self.client.login(username="guser", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )

    def test_gutachten_view_creates_file(self):
        url = reverse("projekt_gutachten", args=[self.projekt.pk])
        with patch("core.views.query_llm", return_value="Gutachtentext"):
            resp = self.client.post(url, {"prompt": "foo"})
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        self.projekt.refresh_from_db()
        self.assertTrue(self.projekt.gutachten_file.name)
        self.assertEqual(self.projekt.status, BVProject.STATUS_GUTACHTEN_OK)
        Path(self.projekt.gutachten_file.path).unlink(missing_ok=True)


class GutachtenEditDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("euser", password="pass")
        self.client.login(username="euser", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        doc.add_paragraph("Alt")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            self.projekt.gutachten_file.save("g.docx", SimpleUploadedFile("g.docx", fh.read()))
        Path(tmp.name).unlink(missing_ok=True)

    def test_view_shows_content(self):
        url = reverse("gutachten_view", args=[self.projekt.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "Alt")

    def test_edit_replaces_file(self):
        old_path = Path(self.projekt.gutachten_file.path)
        url = reverse("gutachten_edit", args=[self.projekt.pk])
        resp = self.client.post(url, {"text": "Neu"})
        self.assertRedirects(resp, reverse("gutachten_view", args=[self.projekt.pk]))
        self.projekt.refresh_from_db()
        new_path = Path(self.projekt.gutachten_file.path)
        self.assertNotEqual(old_path, new_path)
        self.assertTrue(new_path.exists())
        text = extract_text(new_path)
        self.assertIn("Neu", text)
        self.assertFalse(old_path.exists())

    def test_delete_removes_file(self):
        path = Path(self.projekt.gutachten_file.path)
        url = reverse("gutachten_delete", args=[self.projekt.pk])
        resp = self.client.post(url)
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        self.projekt.refresh_from_db()
        self.assertEqual(self.projekt.gutachten_file.name, "")
        self.assertFalse(path.exists())


class ProjektFileCheckResultTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("vuser", password="pass")
        self.client.login(username="vuser", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )

    def test_get_runs_check_and_shows_form(self):
        url = reverse("projekt_file_check_view", args=[self.file.pk])
        expected = {"task": "check_anlage1"}
        with patch("core.llm_tasks.query_llm", return_value=json.dumps(expected)):
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.file.refresh_from_db()
        self.assertEqual(self.file.analysis_json, expected)
        self.assertContains(resp, "name=\"analysis_json\"")

    def test_post_updates_and_redirects(self):
        url = reverse("projekt_file_check_view", args=[self.file.pk])
        resp = self.client.post(url, {"analysis_json": "{}", "manual_analysis_json": "{}"})
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))




class LLMConfigTests(TestCase):
    @override_settings(GOOGLE_API_KEY="x")
    @patch("google.generativeai.list_models")
    @patch("google.generativeai.configure")
    def test_ready_populates_models(self, mock_conf, mock_list):
        mock_list.return_value = [type("M", (), {"name": "m1"})(), type("M", (), {"name": "m2"})()]
        apps.get_app_config("core").ready()
        cfg = LLMConfig.objects.first()
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.available_models, ["m1", "m2"])
        self.assertTrue(cfg.models_changed)

    @override_settings(GOOGLE_API_KEY="x")
    @patch("google.generativeai.list_models")
    @patch("google.generativeai.configure")
    def test_ready_updates_models(self, mock_conf, mock_list):
        LLMConfig.objects.create(available_models=["old"])
        mock_list.return_value = [type("M", (), {"name": "new"})()]
        apps.get_app_config("core").ready()
        cfg = LLMConfig.objects.first()
        self.assertEqual(cfg.available_models, ["new"])
        self.assertTrue(cfg.models_changed)


class AdminModelsViewTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("amodel", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="amodel", password="pass")
        self.cfg = LLMConfig.objects.create(
            default_model="a",
            gutachten_model="a",
            anlagen_model="a",
            available_models=["a", "b"],
        )

    def test_update_models(self):
        url = reverse("admin_models")
        resp = self.client.post(
            url,
            {
                "default_model": "b",
                "gutachten_model": "b",
                "anlagen_model": "b",
            },
        )
        self.assertRedirects(resp, url)
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.default_model, "b")
        self.assertEqual(self.cfg.gutachten_model, "b")
        self.assertEqual(self.cfg.anlagen_model, "b")


class TileVisibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("tileuser", password="pass")
        self.talkdiary = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "bereich": Tile.PERSONAL,
                "url_name": "talkdiary_personal",
            },
        )[0]
        self.projekt = Tile.objects.get_or_create(
            slug="projektverwaltung",
            defaults={
                "name": "Projektverwaltung",
                "bereich": Tile.WORK,
                "url_name": "projekt_list",
            },
        )[0]
        self.client.login(username="tileuser", password="pass")

    def test_personal_without_access(self):
        resp = self.client.get(reverse("personal"))
        self.assertNotContains(resp, "TalkDiary")

    def test_personal_with_access(self):
        UserTileAccess.objects.create(user=self.user, tile=self.talkdiary)
        resp = self.client.get(reverse("personal"))
        self.assertContains(resp, "TalkDiary")

    def test_work_with_projekt_access(self):
        UserTileAccess.objects.create(user=self.user, tile=self.projekt)
        resp = self.client.get(reverse("work"))
        self.assertContains(resp, "Projektverwaltung")
        self.assertNotContains(resp, "TalkDiary")
