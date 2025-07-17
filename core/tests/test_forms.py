from .test_general import *
from ..forms import Anlage5ReviewForm
from ..models import ZweckKategorieA

class BVProjectFormTests(NoesisTestCase):
    def test_project_form_docx_validation(self):
        data = QueryDict(mutable=True)
        data.update(
            {
                "title": "",
            }
        )
        data.setlist("software", ["A"])
        form = BVProjectForm(data)
        self.assertTrue(form.is_valid())
        self.assertNotIn("docx_file", form.fields)

    def test_upload_form_docx_validation(self):
        valid = BVProjectUploadForm(
            {}, {"docx_file": SimpleUploadedFile("t.docx", b"d")}
        )
        self.assertTrue(valid.is_valid())
        invalid = BVProjectUploadForm(
            {}, {"docx_file": SimpleUploadedFile("t.txt", b"d")}
        )
        self.assertFalse(invalid.is_valid())


class Anlage2ConfigFormTests(NoesisTestCase):
    def test_parser_order_field(self):
        cfg = Anlage2Config.get_instance()
        form = Anlage2ConfigForm({"parser_order": ["table"]}, instance=cfg)
        self.assertTrue(form.is_valid())
        inst = form.save()
        self.assertEqual(inst.parser_order, ["table"])


class ProjektFileJSONEditTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("user3", password="pass")
        self.client.login(username="user3", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=4,
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
                    "1": {
                        "answer": "foo",
                        "status": None,
                        "hinweis": "",
                        "vorschlag": "",
                    }
                }
            },
        )

    def test_edit_json_updates_and_reports(self):
        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.post(
            url,
            {
                "analysis_json": '{"new": 1}',
                "manual_analysis_json": '{"manual": 2}',
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
        self.assertEqual(
            self.file.analysis_json, {"old": {"value": True, "editable": True}}
        )

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

    def test_question_review_prefill_from_analysis(self):
        """Initialwerte stammen aus der automatischen Analyse."""
        self.anlage1.question_review = None
        self.anlage1.analysis_json = {
            "questions": {
                "1": {
                    "answer": "A",
                    "status": "ok",
                    "hinweis": "H",
                    "vorschlag": "V",
                }
            }
        }
        self.anlage1.save()

        url = reverse("projekt_file_edit_json", args=[self.anlage1.pk])
        resp = self.client.get(url)
        form = resp.context["form"]
        self.assertEqual(form.initial["q1_status"], "ok")
        self.assertEqual(form.initial["q1_hinweis"], "H")
        self.assertEqual(form.initial["q1_vorschlag"], "V")

    def test_edit_page_has_mde(self):
        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "easymde.min.css")


class GutachtenEditDeleteTests(NoesisTestCase):
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
            self.projekt.gutachten_file.save(
                "g.docx", SimpleUploadedFile("g.docx", fh.read())
            )
        Path(tmp.name).unlink(missing_ok=True)
        self.knowledge = SoftwareKnowledge.objects.create(
            projekt=self.projekt,
            software_name="A",
            is_known_by_llm=True,
        )
        self.gutachten = Gutachten.objects.create(software_knowledge=self.knowledge, text="Alt")

    def test_view_shows_content(self):
        url = reverse("gutachten_view", args=[self.gutachten.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "Alt")

    def test_edit_updates_text(self):
        url = reverse("gutachten_edit", args=[self.gutachten.pk])
        resp = self.client.post(url, {"text": "Neu"})
        self.assertRedirects(resp, reverse("gutachten_view", args=[self.gutachten.pk]))
        self.gutachten.refresh_from_db()
        self.assertEqual(self.gutachten.text, "Neu")

    def test_edit_page_has_mde(self):
        url = reverse("gutachten_edit", args=[self.gutachten.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "easymde.min.css")

    def test_delete_removes_file(self):
        url = reverse("gutachten_delete", args=[self.gutachten.pk])
        resp = self.client.post(url)
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        self.assertFalse(Gutachten.objects.filter(pk=self.gutachten.pk).exists())


class KnowledgeDescriptionEditTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("kwuser", password="pass")
        self.client.login(username="kwuser", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.knowledge = SoftwareKnowledge.objects.create(
            projekt=self.projekt,
            software_name="A",
            is_known_by_llm=True,
            description="Alt",
        )

    def test_edit_page_has_mde(self):
        url = reverse("edit_knowledge_description", args=[self.knowledge.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "easymde.min.css")

    def test_edit_updates_description(self):
        url = reverse("edit_knowledge_description", args=[self.knowledge.pk])
        resp = self.client.post(url, {"description": "Neu"})
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        self.knowledge.refresh_from_db()
        self.assertEqual(self.knowledge.description, "Neu")


class Anlage5ReviewFormTests(NoesisTestCase):
    def test_get_json(self):
        cat = ZweckKategorieA.objects.create(beschreibung="A")
        form = Anlage5ReviewForm({"purposes": [cat.pk], "sonstige": "x"})
        self.assertTrue(form.is_valid())
        data = form.get_json()
        self.assertEqual(data["purposes"], [cat.pk])
        self.assertEqual(data["sonstige"], "x")


