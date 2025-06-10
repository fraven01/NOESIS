from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import TestCase
from django.http import QueryDict


from django.apps import apps
from .models import (
    BVProject,
    BVProjectFile,
    Recording,
    Prompt,
    LLMConfig,
    Tile,
    UserTileAccess,
    Anlage1Question,
    Anlage1Config,
    Area,
    Anlage2Function,
    Anlage2FunctionResult,
)
from .docx_utils import extract_text
from pathlib import Path
from tempfile import NamedTemporaryFile
from docx import Document

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .forms import BVProjectForm, BVProjectUploadForm
from .workflow import set_project_status
from .llm_tasks import (
    classify_system,
    check_anlage1,
    check_anlage2,
    analyse_anlage2,
    check_anlage2_functions,
    get_prompt,
    generate_gutachten,
    parse_anlage1_questions,
    _parse_anlage2,
)
from .reporting import generate_gap_analysis, generate_management_summary
from unittest.mock import patch, ANY
from django.core.management import call_command
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


class AdminProjectCleanupTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("admin2", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="admin2", password="pass")

        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )

    def test_delete_file(self):
        path = Path(self.file.upload.path)
        url = reverse("admin_project_cleanup", args=[self.projekt.pk])
        resp = self.client.post(url, {"action": "delete_file", "file_id": self.file.id})
        self.assertRedirects(resp, url)
        self.assertFalse(BVProjectFile.objects.filter(id=self.file.id).exists())
        self.assertFalse(path.exists())

    def test_delete_gutachten(self):
        gpath = generate_gutachten(self.projekt.pk, text="foo")
        url = reverse("admin_project_cleanup", args=[self.projekt.pk])
        resp = self.client.post(url, {"action": "delete_gutachten"})
        self.assertRedirects(resp, url)
        self.projekt.refresh_from_db()
        self.assertEqual(self.projekt.gutachten_file.name, "")
        self.assertFalse(gpath.exists())

    def test_delete_classification(self):
        self.projekt.classification_json = {"a": 1}
        self.projekt.save()
        url = reverse("admin_project_cleanup", args=[self.projekt.pk])
        resp = self.client.post(url, {"action": "delete_classification"})
        self.assertRedirects(resp, url)
        self.projekt.refresh_from_db()
        self.assertIsNone(self.projekt.classification_json)

    def test_delete_summary(self):
        self.projekt.llm_initial_output = "x"
        self.projekt.llm_antwort = "y"
        self.projekt.llm_geprueft = True
        self.projekt.llm_geprueft_am = timezone.now()
        self.projekt.llm_validated = True
        self.projekt.save()
        url = reverse("admin_project_cleanup", args=[self.projekt.pk])
        resp = self.client.post(url, {"action": "delete_summary"})
        self.assertRedirects(resp, url)
        self.projekt.refresh_from_db()
        self.assertEqual(self.projekt.llm_initial_output, "")
        self.assertEqual(self.projekt.llm_antwort, "")
        self.assertFalse(self.projekt.llm_geprueft)
        self.assertIsNone(self.projekt.llm_geprueft_am)
        self.assertFalse(self.projekt.llm_validated)



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


class BVProjectFormTests(TestCase):
    def test_project_form_docx_validation(self):
        data = QueryDict(mutable=True)
        data.update({
            "title": "",
            "beschreibung": "",
        })
        data.setlist("software", ["A"])
        valid = BVProjectForm(data, {"docx_file": SimpleUploadedFile("t.docx", b"d")})
        self.assertTrue(valid.is_valid())
        invalid = BVProjectForm(data, {"docx_file": SimpleUploadedFile("t.txt", b"d")})
        self.assertFalse(invalid.is_valid())

    def test_upload_form_docx_validation(self):
        valid = BVProjectUploadForm({}, {"docx_file": SimpleUploadedFile("t.docx", b"d")})
        self.assertTrue(valid.is_valid())
        invalid = BVProjectUploadForm({}, {"docx_file": SimpleUploadedFile("t.txt", b"d")})
        self.assertFalse(invalid.is_valid())

    def test_form_saves_title(self):
        data = QueryDict(mutable=True)
        data.update({
            "title": "Mein Projekt",
            "beschreibung": "",
        })
        data.setlist("software", ["A"])
        form = BVProjectForm(data)
        self.assertTrue(form.is_valid())
        projekt = form.save()
        self.assertEqual(projekt.title, "Mein Projekt")
        self.assertEqual(projekt.status, BVProject.STATUS_NEW)

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


class BVProjectModelTests(TestCase):
    def test_title_auto_set_from_software(self):
        projekt = BVProject.objects.create(software_typen="A, B", beschreibung="x")
        self.assertEqual(projekt.title, "A, B")

    def test_title_preserved_when_set(self):
        projekt = BVProject.objects.create(title="X", software_typen="A", beschreibung="x")
        self.assertEqual(projekt.title, "X")


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

    def test_status_history_created(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.assertEqual(projekt.status_history.count(), 1)
        set_project_status(projekt, BVProject.STATUS_CLASSIFIED)
        self.assertEqual(projekt.status_history.count(), 2)


class LLMTasksTests(TestCase):
    maxDiff = None
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

    def test_check_anlage2_llm_receives_text(self):
        """Der LLM-Prompt enthält den bekannten Text."""
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testinhalt Anlage2",
        )
        with patch("core.llm_tasks.query_llm", return_value='{"ok": true}') as mock_q:
            data = check_anlage2(projekt.pk)
        self.assertIn("Testinhalt Anlage2", mock_q.call_args_list[0].args[0])
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertTrue(file_obj.analysis_json["ok"]["value"])
        self.assertTrue(data["ok"]["value"])

    def test_check_anlage2_prompt_contains_text(self):
        """Der Prompt enth\u00E4lt den gesamten Anlagentext."""
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testinhalt Anlage2",
        )
        with patch("core.llm_tasks.query_llm", return_value='{"ok": true}') as mock_q:
            data = check_anlage2(projekt.pk)
        prompt = mock_q.call_args_list[0].args[0]
        self.assertIn("Testinhalt Anlage2", prompt)
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertTrue(file_obj.analysis_json["ok"]["value"])
        self.assertTrue(data["ok"]["value"])

    def test_analyse_anlage2(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="b")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text A1",
        )
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("b.txt", b"data"),
            text_content="- Login",
        )
        llm_reply = json.dumps([
            {
                "funktion": "Login",
                "technisch_vorhanden": True,
                "einsatz_bei_telefonica": False,
                "zur_lv_kontrolle": True,
                "ki_beteiligung": True,
            }
        ])
        with patch("core.llm_tasks.query_llm", return_value=llm_reply):
            data = analyse_anlage2(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertEqual(data["missing"]["value"], [])
        self.assertEqual(file_obj.analysis_json["additional"]["value"], [])

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
        llm_reply = json.dumps({**expected, "questions": {}})
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch("core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply] * 9):
            data = check_anlage1(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=1)
        answers = [["ACME"], ["IT"], "leer", "raw", "Zweck", "leer", "leer", "leer", "leer"]
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected["questions"] = {
            str(i): {
                "answer": answers[i - 1],
                "status": "ok",
                "hinweis": "",
                "vorschlag": "",
            }
            for i in nums
        }
        self.assertEqual(file_obj.analysis_json, expected)
        self.assertEqual(data, expected)

    def test_check_anlage1_parser(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        text = (
            "Frage 1: Extrahiere alle Unternehmen als Liste.\u00b6A1\u00b6"
            "Frage 2: Extrahiere alle Fachbereiche als Liste.\u00b6A2"
        )
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content=text,
        )
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch("core.llm_tasks.query_llm", side_effect=[eval_reply] * 9):
            data = check_anlage1(projekt.pk)
        answers = {
            "1": "A1",
            "2": "A2",
        }
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected_questions = {
            str(i): {
                "answer": answers.get(str(i), "leer"),
                "status": "ok",
                "hinweis": "",
                "vorschlag": "",
            }
            for i in nums
        }
        file_obj = projekt.anlagen.get(anlage_nr=1)
        self.assertEqual(data["source"], "parser")
        self.assertEqual(data["questions"]["1"]["answer"], "A1")
        self.assertEqual(data["questions"]["2"]["answer"], "A2")
        self.assertEqual(file_obj.analysis_json, data)

    def test_parse_anlage1_questions_extra(self):
        Anlage1Question.objects.create(
            num=10,
            text="Frage 10: Test?",
            enabled=True,
            parser_enabled=True,
            llm_enabled=True,
        )
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        text = (
            "Frage 1: Extrahiere alle Unternehmen als Liste.\u00b6A1\u00b6"
            "Frage 10: Test?\u00b6A10"
        )
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content=text,
        )
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        with patch("core.llm_tasks.query_llm", side_effect=[eval_reply] * len(nums)):
            data = check_anlage1(projekt.pk)
        q_data = data["questions"]
        self.assertEqual(q_data["10"]["answer"], "A10")

    def test_parse_anlage1_questions_without_numbers(self):
        """Prüft die Extraktion ohne nummerierte Fragen."""
        # Frage-Texte ohne Präfix "Frage X:" speichern
        q1 = Anlage1Question.objects.get(num=1)
        q2 = Anlage1Question.objects.get(num=2)
        q1.text = q1.text.split(": ", 1)[1]
        q2.text = q2.text.split(": ", 1)[1]
        q1.save(update_fields=["text"])
        q2.save(update_fields=["text"])
        v1 = q1.variants.first()
        v2 = q2.variants.first()
        v1.text = q1.text
        v2.text = q2.text
        v1.save()
        v2.save()

        text = f"{q1.text}\u00b6A1\u00b6{q2.text}\u00b6A2"
        parsed = parse_anlage1_questions(text)
        self.assertEqual(
            parsed,
            {"1": {"answer": "A1", "found_num": None}, "2": {"answer": "A2", "found_num": None}},
        )

    def test_parse_anlage1_questions_with_variant(self):
        q1 = Anlage1Question.objects.get(num=1)
        q1.variants.create(text="Alternative Frage 1?")
        text = "Alternative Frage 1?\u00b6A1"
        parsed = parse_anlage1_questions(text)
        self.assertEqual(parsed, {"1": {"answer": "A1", "found_num": "1"}})

    def test_parse_anlage1_questions_with_newlines(self):
        """Extraktion funktioniert trotz Zeilenumbr\u00fcche."""
        text = (
            "Frage 1:\nExtrahiere alle Unternehmen als Liste.\nA1\n"
            "Frage 2:\nExtrahiere alle Fachbereiche als Liste.\nA2"
        )
        parsed = parse_anlage1_questions(text)
        self.assertEqual(
            parsed,
            {"1": {"answer": "A1", "found_num": "1"}, "2": {"answer": "A2", "found_num": "2"}},
        )

    def test_parse_anlage1_questions_respects_parser_enabled(self):
        q2 = Anlage1Question.objects.get(num=2)
        q2.parser_enabled = False
        q2.save(update_fields=["parser_enabled"])
        text = "Frage 1: Extrahiere alle Unternehmen als Liste.\u00b6A1"
        parsed = parse_anlage1_questions(text)
        self.assertEqual(parsed, {"1": {"answer": "A1", "found_num": "1"}})

    def test_wrong_question_number_sets_hint(self):
        """Hinweis wird gesetzt, wenn die Nummer nicht passt."""
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        text = "Frage 1.2: Extrahiere alle Unternehmen als Liste.\u00b6A1"
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content=text,
        )
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch("core.llm_tasks.query_llm", side_effect=[eval_reply] * 9):
            analysis = check_anlage1(projekt.pk)
        hint = analysis["questions"]["1"]["hinweis"]
        self.assertIn("Frage 1.2 statt 1", hint)

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

    def test_check_anlage1_ignores_disabled_questions(self):
        Anlage1Config.objects.create()  # Standardwerte
        q1 = Anlage1Question.objects.get(num=1)
        q1.llm_enabled = False
        q1.save(update_fields=["llm_enabled"])
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        enabled_count = Anlage1Question.objects.filter(llm_enabled=True).count()
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["{\"task\": \"check_anlage1\"}"]
            + [eval_reply] * enabled_count,
        ) as mock_q:
            data = check_anlage1(projekt.pk)
        prompt = mock_q.call_args_list[0].args[0]
        self.assertNotIn("Frage 1", prompt)
        self.assertIn("1", data["questions"])
        self.assertIsNone(data["questions"]["1"]["status"])

    def test_parse_anlage2_question_list(self):
        text = "Welche Funktionen bietet das System?\u00b6- Login\u00b6- Suche"
        parsed = _parse_anlage2(text)
        self.assertEqual(parsed, ["Login", "Suche"])

    def test_parse_anlage2_table_llm(self):
        text = "Funktion | Beschreibung\u00b6Login | a\u00b6Suche | b"
        with patch("core.llm_tasks.query_llm", return_value='["Login", "Suche"]') as mock_q:
            parsed = _parse_anlage2(text)
        mock_q.assert_called_once()
        self.assertEqual(parsed, ["Login", "Suche"])


class PromptTests(TestCase):
    def test_get_prompt_returns_default(self):
        self.assertEqual(get_prompt("unknown", "foo"), "foo")

    def test_get_prompt_returns_db_value(self):
        p, _ = Prompt.objects.get_or_create(name="classify_system", defaults={"text": "orig"})
        p.text = "DB"
        p.save()
        self.assertEqual(get_prompt("classify_system", "x"), "DB")

    def test_check_anlage1_prompt_text(self):
        p = Prompt.objects.get(name="check_anlage1")
        expected = (
            "System: Du bist ein juristisch-technischer Prüf-Assistent für Systembeschreibungen.\n\n"
            "Frage 1: Extrahiere alle Unternehmen als Liste.\n"
            "Frage 2: Extrahiere alle Fachbereiche als Liste.\n"
            "IT-Landschaft: Fasse den Abschnitt zusammen, der die Einbettung in die IT-Landschaft beschreibt.\n"
            "Frage 3: Liste alle Hersteller und Produktnamen auf.\n"
            "Frage 4: Lege den Textblock als question4_raw ab.\n"
            "Frage 5: Fasse den Zweck des Systems in einem Satz.\n"
            "Frage 6: Extrahiere Web-URLs.\n"
            "Frage 7: Extrahiere ersetzte Systeme.\n"
            "Frage 8: Extrahiere Legacy-Funktionen.\n"
            "Frage 9: Lege den Text als question9_raw ab.\n"
            "Konsistenzprüfung und Stichworte. Gib ein JSON im vorgegebenen Schema zurück.\n\n"
        )
        self.assertEqual(p.text, expected)


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
        expected = {
            "task": "check_anlage1",
        }
        llm_reply = json.dumps({"companies": None, "departments": None, "vendors": None, "question4_raw": None, "purpose_summary": None, "documentation_links": None, "replaced_systems": None, "legacy_functions": None, "question9_raw": None})
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch("core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply]*9):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        file_obj = self.projekt.anlagen.get(anlage_nr=1)
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected["questions"] = {str(i): {"answer": "leer", "status": "ok", "hinweis": "", "vorschlag": ""} for i in nums}
        self.assertEqual(file_obj.analysis_json, expected)

    def test_file_check_pk_endpoint_saves_json(self):
        file_obj = self.projekt.anlagen.get(anlage_nr=1)
        url = reverse("projekt_file_check_pk", args=[file_obj.pk])
        expected = {"task": "check_anlage1"}
        llm_reply = json.dumps({"companies": None, "departments": None, "vendors": None, "question4_raw": None, "purpose_summary": None, "documentation_links": None, "replaced_systems": None, "legacy_functions": None, "question9_raw": None})
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch("core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply]*9):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        file_obj.refresh_from_db()
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected["questions"] = {str(i): {"answer": "leer", "status": "ok", "hinweis": "", "vorschlag": ""} for i in nums}
        self.assertEqual(file_obj.analysis_json, expected)


class ProjektFileJSONEditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("user3", password="pass")
        self.client.login(username="user3", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
            analysis_json={"old": {"value": True, "editable": True}},
        )
        self.anlage1 = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("b.txt", b"data"),
            text_content="Text",
            analysis_json={
                "questions": {
                    "1": {"answer": "foo", "status": None, "hinweis": "", "vorschlag": ""}
                }
            },
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

    def test_question_review_saved(self):
        url = reverse("projekt_file_edit_json", args=[self.anlage1.pk])
        resp = self.client.post(
            url,
            {"q1_ok": "on", "q1_note": "Hinweis"},
        )
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        self.anlage1.refresh_from_db()
        self.assertTrue(self.anlage1.question_review["1"]["ok"])
        self.assertEqual(self.anlage1.question_review["1"]["note"], "Hinweis")

    def test_question_review_extended_fields_saved(self):
        url = reverse("projekt_file_edit_json", args=[self.anlage1.pk])
        resp = self.client.post(
            url,
            {
                "q1_status": "unvollst\u00e4ndig",
                "q1_hinweis": "Fehlt",
                "q1_vorschlag": "Mehr Infos",
            },
        )
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        self.anlage1.refresh_from_db()
        data = self.anlage1.question_review["1"]
        self.assertEqual(data["status"], "unvollst\u00e4ndig")
        self.assertEqual(data["hinweis"], "Fehlt")
        self.assertEqual(data["vorschlag"], "Mehr Infos")


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
        llm_reply = json.dumps({"companies": None, "departments": None, "vendors": None, "question4_raw": None, "purpose_summary": None, "documentation_links": None, "replaced_systems": None, "legacy_functions": None, "question9_raw": None})
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch("core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply]*9):
            resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.file.refresh_from_db()
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected["questions"] = {str(i): {"answer": "leer", "status": "ok", "hinweis": "", "vorschlag": ""} for i in nums}
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


class Anlage1EmailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("emailer", password="pass")
        self.client.login(username="emailer", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            question_review={"1": {"vorschlag": "Text"}},
        )

    def test_generate_email(self):
        url = reverse("anlage1_generate_email", args=[self.file.pk])
        with patch("core.views.query_llm", return_value="Mail"):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["text"], "Mail")



class TileVisibilityTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("tileuser", password="pass")
        self.user.groups.add(admin_group)
        work = Area.objects.get_or_create(slug="work", defaults={"name": "Work"})[0]
        self.personal = Area.objects.get_or_create(slug="personal", defaults={"name": "Personal"})[0]
        self.talkdiary = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "bereich": self.personal,
                "url_name": "talkdiary_personal",
            },
        )[0]
        self.projekt = Tile.objects.get_or_create(
            slug="projektverwaltung",
            defaults={
                "name": "Projektverwaltung",
                "bereich": work,
                "url_name": "projekt_list",
            },
        )[0]
        self.cfg = LLMConfig.objects.first() or LLMConfig.objects.create(models_changed=False)
        self.client.login(username="tileuser", password="pass")

    def test_personal_without_access(self):
        resp = self.client.get(reverse("personal"))
        self.assertNotContains(resp, "TalkDiary")

    def test_personal_with_access(self):
        UserTileAccess.objects.create(user=self.user, tile=self.talkdiary)
        resp = self.client.get(reverse("personal"))
        self.assertContains(resp, "TalkDiary")

    def test_personal_with_image(self):
        UserTileAccess.objects.create(user=self.user, tile=self.talkdiary)
        self.talkdiary.image.save(
            "img.png",
            SimpleUploadedFile("img.png", b"data"),
            save=True,
        )
        resp = self.client.get(reverse("personal"))
        self.assertContains(resp, "<img", html=False)

    def test_work_with_projekt_access(self):
        UserTileAccess.objects.create(user=self.user, tile=self.projekt)
        resp = self.client.get(reverse("work"))
        self.assertContains(resp, "Projektverwaltung")
        self.assertNotContains(resp, "TalkDiary")

    def test_flag_reset_on_get(self):
        self.cfg.models_changed = True
        self.cfg.save(update_fields=["models_changed"])
        url = reverse("admin_models")
        self.client.get(url)
        self.cfg.refresh_from_db()
        self.assertFalse(self.cfg.models_changed)


class TileAccessTests(TestCase):
    def setUp(self):
        work = Area.objects.get_or_create(slug="work", defaults={"name": "Work"})[0]
        personal = Area.objects.get_or_create(slug="personal", defaults={"name": "Personal"})[0]
        self.talkdiary = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "bereich": personal,
                "url_name": "talkdiary_personal",
            },
        )[0]
        self.projekt = Tile.objects.get_or_create(
            slug="projektverwaltung",
            defaults={
                "name": "Projektverwaltung",
                "bereich": work,
                "url_name": "projekt_list",
            },
        )[0]

    def _login(self, name: str) -> User:
        """Erzeugt einen Benutzer und loggt ihn ein."""
        user = User.objects.create_user(name, password="pass")
        self.client.login(username=name, password="pass")
        return user

    def test_talkdiary_access_denied_without_tile(self):
        self._login("nodiac")
        resp = self.client.get(reverse("personal"))
        self.assertNotContains(resp, "TalkDiary")
        resp = self.client.get(reverse("talkdiary_personal"))
        self.assertEqual(resp.status_code, 403)

    def test_talkdiary_access_allowed_with_tile(self):
        user = self._login("withdia")
        UserTileAccess.objects.create(user=user, tile=self.talkdiary)
        resp = self.client.get(reverse("personal"))
        self.assertContains(resp, "TalkDiary")
        resp = self.client.get(reverse("talkdiary_personal"))
        self.assertEqual(resp.status_code, 200)

    def test_projekt_access_denied_without_tile(self):
        self._login("noproj")
        resp = self.client.get(reverse("work"))
        self.assertNotContains(resp, "Projektverwaltung")
        resp = self.client.get(reverse("projekt_list"))
        self.assertEqual(resp.status_code, 403)

    def test_projekt_access_allowed_with_tile(self):
        user = self._login("withproj")
        UserTileAccess.objects.create(user=user, tile=self.projekt)
        resp = self.client.get(reverse("work"))
        self.assertContains(resp, "Projektverwaltung")
        resp = self.client.get(reverse("projekt_list"))
        self.assertEqual(resp.status_code, 200)


class LLMConfigNoticeMiddlewareTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("llmadmin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="llmadmin", password="pass")
        LLMConfig.objects.create(models_changed=True)

    def test_message_shown(self):
        resp = self.client.get(reverse("home"))
        msgs = [m.message for m in resp.context["messages"]]
        self.assertTrue(any("LLM-Einstellungen" in m for m in msgs))



class HomeRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("redir", password="pass")
        personal = Area.objects.get_or_create(slug="personal", defaults={"name": "Personal"})[0]
        tile = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "bereich": personal,
                "url_name": "talkdiary_personal",
            },
        )[0]
        UserTileAccess.objects.create(user=self.user, tile=tile)
        self.client.login(username="redir", password="pass")

    def test_redirect_personal(self):
        resp = self.client.get(reverse("home"))
        self.assertRedirects(resp, reverse("personal"))

class AreaImageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("areauser", password="pass")
        self.client.login(username="areauser", password="pass")

    def test_home_without_images(self):
        Area.objects.get_or_create(slug="work", defaults={"name": "Work"})
        Area.objects.get_or_create(slug="personal", defaults={"name": "Personal"})
        resp = self.client.get(reverse("home"))
        self.assertNotContains(resp, 'alt="Work"', html=False)
        self.assertNotContains(resp, 'alt="Personal"', html=False)

    def test_home_with_images(self):
        work, _ = Area.objects.get_or_create(slug="work", defaults={"name": "Work"})
        personal, _ = Area.objects.get_or_create(slug="personal", defaults={"name": "Personal"})
        work.image.save("w.png", SimpleUploadedFile("w.png", b"d"), save=True)
        personal.image.save("p.png", SimpleUploadedFile("p.png", b"d"), save=True)
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, f'alt="{work.name}"', html=False)
        self.assertContains(resp, f'alt="{personal.name}"', html=False)




class RecordingDeleteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("recuser", password="pass")
        self.client.login(username="recuser", password="pass")
        self.personal = Area.objects.get_or_create(slug="personal", defaults={"name": "Personal"})[0]
        self.tile = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "bereich": self.personal,
                "url_name": "talkdiary_personal",
            },
        )[0]
        UserTileAccess.objects.create(user=self.user, tile=self.tile)
        audio = SimpleUploadedFile("a.wav", b"data")
        transcript = SimpleUploadedFile("a.md", b"text")
        self.rec = Recording.objects.create(
            user=self.user,
            bereich=self.personal,
            audio_file=audio,
            transcript_file=transcript,
        )
        self.audio_path = Path(self.rec.audio_file.path)
        self.trans_path = Path(self.rec.transcript_file.path)

    def test_delete_own_recording(self):
        url = reverse("recording_delete", args=[self.rec.pk])
        resp = self.client.post(url)
        self.assertRedirects(resp, reverse("talkdiary_personal"))
        self.assertFalse(Recording.objects.filter(pk=self.rec.pk).exists())
        self.assertFalse(self.audio_path.exists())
        self.assertFalse(self.trans_path.exists())

    def test_delete_requires_post(self):
        url = reverse("recording_delete", args=[self.rec.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(Recording.objects.filter(pk=self.rec.pk).exists())

    def test_delete_other_user_recording(self):
        other = User.objects.create_user("other", password="pass")
        rec = Recording.objects.create(
            user=other,
            bereich=self.personal,
            audio_file=SimpleUploadedFile("b.wav", b"d"),
            transcript_file=SimpleUploadedFile("b.md", b"t"),
        )
        url = reverse("recording_delete", args=[rec.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Recording.objects.filter(pk=rec.pk).exists())

class AdminAnlage1ViewTests(TestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("a1admin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="a1admin", password="pass")

    def test_delete_question(self):
        url = reverse("admin_anlage1")
        questions = list(Anlage1Question.objects.all())
        q = questions[0]
        data = {}
        for question in questions:
            if question.id == q.id:
                data[f"delete{question.id}"] = "on"
            if question.parser_enabled:
                data[f"parser_enabled{question.id}"] = "on"
            if question.llm_enabled:
                data[f"llm_enabled{question.id}"] = "on"
            data[f"text{question.id}"] = question.text
        resp = self.client.post(url, data)
        self.assertRedirects(resp, url)
        self.assertFalse(Anlage1Question.objects.filter(id=q.id).exists())
        self.assertEqual(Anlage1Question.objects.count(), len(questions) - 1)

    def _build_post_data(self, *, new=False, parser=True, llm=True):
        """Hilfsfunktion zum Erstellen der POST-Daten."""
        data = {}
        for q in Anlage1Question.objects.all():
            if q.parser_enabled:
                data[f"parser_enabled{q.id}"] = "on"
            if q.llm_enabled:
                data[f"llm_enabled{q.id}"] = "on"
            data[f"text{q.id}"] = q.text
        if new:
            data["new_text"] = "Neue Frage?"
            if parser:
                data["new_parser_enabled"] = "on"
            if llm:
                data["new_llm_enabled"] = "on"
        return data

    def test_add_new_question_with_flags(self):
        url = reverse("admin_anlage1")
        count = Anlage1Question.objects.count()
        resp = self.client.post(url, self._build_post_data(new=True, parser=True, llm=False))
        self.assertRedirects(resp, url)
        self.assertEqual(Anlage1Question.objects.count(), count + 1)
        q = Anlage1Question.objects.order_by("-num").first()
        self.assertEqual(q.text, "Neue Frage?")
        self.assertTrue(q.parser_enabled)
        self.assertFalse(q.llm_enabled)

    def test_add_new_question_unchecked(self):
        url = reverse("admin_anlage1")
        count = Anlage1Question.objects.count()
        resp = self.client.post(url, self._build_post_data(new=True, parser=False, llm=False))
        self.assertRedirects(resp, url)
        self.assertEqual(Anlage1Question.objects.count(), count + 1)
        q = Anlage1Question.objects.order_by("-num").first()
        self.assertFalse(q.parser_enabled)
        self.assertFalse(q.llm_enabled)


class ModelSelectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("modeluser", password="pass")
        self.client.login(username="modeluser", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )
        LLMConfig.objects.create(
            default_model="d",
            gutachten_model="g",
            anlagen_model="a",
        )

    def test_projekt_check_uses_category(self):
        url = reverse("projekt_check", args=[self.projekt.pk])
        with patch("core.views.query_llm", return_value="ok") as mock_q:
            resp = self.client.post(url, {"model_category": "gutachten"})
        self.assertEqual(resp.status_code, 200)
        mock_q.assert_called_with(ANY, model_name="g", model_type="default")

    def test_file_check_uses_category(self):
        url = reverse("projekt_file_check", args=[self.projekt.pk, 1])
        with patch("core.views.check_anlage1") as mock_func:
            mock_func.return_value = {"task": "check_anlage1"}
            resp = self.client.post(url, {"model_category": "anlagen"})
        self.assertEqual(resp.status_code, 200)
        mock_func.assert_called_with(self.projekt.pk, model_name="a")

    def test_forms_show_categories(self):
        edit_url = reverse("projekt_edit", args=[self.projekt.pk])
        resp = self.client.get(edit_url)
        self.assertContains(resp, "Standard")
        self.assertContains(resp, "Gutachten")
        self.assertContains(resp, "Anlagen")

        view_url = reverse("projekt_file_check_view", args=[self.projekt.anlagen.first().pk])
        with patch("core.views.check_anlage1") as mock_func:
            mock_func.return_value = {"task": "check_anlage1"}
            resp = self.client.get(view_url)
        self.assertContains(resp, "Standard")
        self.assertContains(resp, "Gutachten")
        self.assertContains(resp, "Anlagen")

        gutachten_url = reverse("projekt_gutachten", args=[self.projekt.pk])
        resp = self.client.get(gutachten_url)
        self.assertContains(resp, "Standard")
        self.assertContains(resp, "Gutachten")
        self.assertContains(resp, "Anlagen")

    def test_functions_check_uses_model(self):
        url = reverse("projekt_functions_check", args=[self.projekt.pk])
        with patch("core.views.check_anlage2_functions") as mock_func:
            mock_func.return_value = []
            resp = self.client.post(url, {"model": "mf"})
        self.assertEqual(resp.status_code, 200)
        mock_func.assert_called_with(self.projekt.pk, model_name="mf")


class CommandModelTests(TestCase):
    def test_command_passes_model(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"d"),
            text_content="Text",
        )
        with patch("core.management.commands.check_anlage2.check_anlage2") as mock_func:
            mock_func.return_value = {"ok": True}
            call_command("check_anlage2", str(projekt.pk), "--model", "m3")
        mock_func.assert_called_with(projekt.pk, model_name="m3")

    def test_analyse_command_passes_model(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("b.txt", b"d"),
            text_content="- Login",
        )
        with patch("core.management.commands.analyse_anlage2.analyse_anlage2") as mock_func:
            mock_func.return_value = {"missing": [], "additional": []}
            call_command("analyse_anlage2", str(projekt.pk), "--model", "m4")
        mock_func.assert_called_with(projekt.pk, model_name="m4")


class Anlage2FunctionTests(TestCase):
    def test_check_anlage2_functions_creates_result(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        func = Anlage2Function.objects.create(name="Login")
        llm_reply = json.dumps({
            "technisch_verfuegbar": True,
            "einsatz_telefonica": False,
            "zur_lv_kontrolle": True,
            "ki_beteiligung": False,
        })
        with patch("core.llm_tasks.query_llm", return_value=llm_reply):
            data = check_anlage2_functions(projekt.pk)
        res = Anlage2FunctionResult.objects.get(projekt=projekt, funktion=func)
        self.assertTrue(res.technisch_verfuegbar)
        self.assertFalse(res.einsatz_telefonica)
        self.assertTrue(res.zur_lv_kontrolle)
        self.assertEqual(data[0]["technisch_verfuegbar"], True)


class CommandFunctionsTests(TestCase):
    def test_functions_command_passes_model(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        Anlage2Function.objects.create(name="Login")
        with patch(
            "core.management.commands.check_anlage2_functions.check_anlage2_functions"
        ) as mock_func:
            mock_func.return_value = []
            call_command("check_anlage2_functions", str(projekt.pk), "--model", "m5")
        mock_func.assert_called_with(projekt.pk, model_name="m5")



