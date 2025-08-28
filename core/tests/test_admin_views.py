from .base import NoesisTestCase
from .test_general import *

class AdminProjectsTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("admin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="admin", password="pass")

        self.p1 = create_project(["A"], beschreibung="x")
        self.p2 = create_project(["B"], beschreibung="y")

    def test_delete_selected_projects(self):
        url = reverse("admin_projects")
        resp = self.client.post(url, {"delete_selected": "1", "selected_projects": [self.p1.id]})
        self.assertRedirects(resp, url)
        self.assertFalse(BVProject.objects.filter(id=self.p1.id).exists())
        self.assertTrue(BVProject.objects.filter(id=self.p2.id).exists())

    def test_delete_single_project(self):
        url = reverse("admin_projects")
        resp = self.client.post(url, {"delete_single": str(self.p2.id)})
        self.assertRedirects(resp, url)
        self.assertFalse(BVProject.objects.filter(id=self.p2.id).exists())

    def test_delete_single_requires_post(self):
        url = reverse("admin_project_delete", args=[self.p1.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(BVProject.objects.filter(id=self.p1.id).exists())


class AdminProjectCleanupTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("admin2", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="admin2", password="pass")

        self.projekt = create_project(["A"], beschreibung="x")
        self.file = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
            analysis_json={"ok": {"value": True, "editable": True}},
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

    def test_delete_gap_report(self):
        self.file.gap_summary = "foo"
        self.file.save()
        pf2 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("b.txt", b"data"),
            text_content="Text",
        )
        pf2.gap_summary = "bar"
        pf2.save()
        url = reverse("admin_project_cleanup", args=[self.projekt.pk])
        resp = self.client.post(url, {"action": "delete_gap_report"})
        self.assertRedirects(resp, url)
        self.file.refresh_from_db()
        pf2.refresh_from_db()
        self.assertEqual(self.file.gap_summary, "")
        self.assertEqual(pf2.gap_summary, "")

    def test_cleanup_does_not_touch_analysis_json(self):
        original = self.file.analysis_json
        url = reverse("admin_project_cleanup", args=[self.projekt.pk])
        resp = self.client.post(url, {"action": "delete_classification"})
        self.assertRedirects(resp, url)
        self.file.refresh_from_db()
        self.assertEqual(self.file.analysis_json, original)

    def test_version_column_and_sorting(self):
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            version=2,
            upload=SimpleUploadedFile("a2.txt", b"data"),
        )
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=2,
            version=1,
            upload=SimpleUploadedFile("b1.txt", b"data"),
        )
        url = reverse("admin_project_cleanup", args=[self.projekt.pk])
        resp = self.client.get(url)
        files = list(resp.context["files"])
        self.assertEqual(
            [(f.anlage_nr, f.version) for f in files],
            [(1, 1), (1, 2), (2, 1)],
        )
        self.assertContains(resp, "<th class=\"py-2\">Version</th>")
class AdminPromptsViewTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("padmin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="padmin", password="pass")
        self.prompt = Prompt.objects.create(name="p1", text="orig")

    def test_update_prompt(self):
        url = reverse("admin_prompts")
        resp = self.client.post(
            url,
            {
                "pk": self.prompt.id,
                "text": "neu",
                "action": "save",
                "use_system_role": "on",
            },
        )
        self.assertRedirects(resp, url)
        self.prompt.refresh_from_db()
        self.assertEqual(self.prompt.text, "neu")

    def test_delete_prompt(self):
        url = reverse("admin_prompts")
        resp = self.client.post(url, {"pk": self.prompt.id, "action": "delete"})
        self.assertRedirects(resp, url)
        self.assertFalse(Prompt.objects.filter(id=self.prompt.id).exists())


class AdminModelsViewTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("amodel", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="amodel", password="pass")
        self.cfg = LLMConfig.get_instance()
        self.cfg.default_model = "a"
        self.cfg.gutachten_model = "a"
        self.cfg.anlagen_model = "a"
        self.cfg.available_models = ["a", "b"]
        self.cfg.save()

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


class AdminAnlage1ViewTests(NoesisTestCase):
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
        resp = self.client.post(
            url, self._build_post_data(new=True, parser=True, llm=False)
        )
        self.assertRedirects(resp, url)
        self.assertEqual(Anlage1Question.objects.count(), count + 1)
        q = Anlage1Question.objects.order_by("-num").first()
        self.assertEqual(q.text, "Neue Frage?")
        self.assertTrue(q.parser_enabled)
        self.assertFalse(q.llm_enabled)

    def test_add_new_question_unchecked(self):
        url = reverse("admin_anlage1")
        count = Anlage1Question.objects.count()
        resp = self.client.post(
            url, self._build_post_data(new=True, parser=False, llm=False)
        )
        self.assertRedirects(resp, url)
        self.assertEqual(Anlage1Question.objects.count(), count + 1)
        q = Anlage1Question.objects.order_by("-num").first()
        self.assertFalse(q.parser_enabled)
        self.assertFalse(q.llm_enabled)


