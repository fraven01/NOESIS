from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.test import TestCase
from django.http import QueryDict
from django.db import IntegrityError
from types import SimpleNamespace


from django.apps import apps
from ..models import (
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
    Anlage2Config,
    Anlage2ColumnHeading,
    Anlage2SubQuestion,
    Anlage2FunctionResult,
    SoftwareKnowledge,
    BVSoftware,
    Gutachten,
    FormatBParserRule,
    AntwortErkennungsRegel,
    Anlage4Config,
)
from ..docx_utils import (
    extract_text,
    get_docx_page_count,
    get_pdf_page_count,
    extract_images,
    parse_anlage2_table,
    _normalize_header_text,
)

from .. import text_parser

from core.text_parser import parse_anlage2_text, PHRASE_TYPE_CHOICES

from ..anlage4_parser import parse_anlage4

from ..parser_manager import parser_manager
from ..parsers import AbstractParser

from pathlib import Path
from tempfile import NamedTemporaryFile
from docx import Document
import shutil
from PIL import Image
import fitz

from django.core.files.uploadedfile import SimpleUploadedFile
from ..forms import (
    BVProjectForm,
    BVProjectUploadForm,
    BVProjectFileJSONForm,
    Anlage2ConfigForm,
    Anlage2ReviewForm,
)
from ..workflow import set_project_status
from ..models import ProjectStatus
from ..llm_tasks import (
    classify_system,
    check_anlage1,
    check_anlage2,
    analyse_anlage2,
    analyse_anlage3,
    analyse_anlage4,
    analyse_anlage4_async,
    check_anlage3_vision,
    check_anlage2_functions,
    worker_verify_feature,
    worker_generate_gutachten,
    worker_run_initial_check,
    worker_run_anlage3_vision,
    worker_anlage4_evaluate,
    worker_generate_gap_summary,
    get_prompt,
    generate_gutachten,
    run_anlage2_analysis,
    parse_anlage1_questions,
    _parse_anlage2,
)
from ..views import _verification_to_initial, _build_row_data
from ..reporting import generate_gap_analysis, generate_management_summary
from unittest.mock import patch, ANY
from django.core.management import call_command
from django.test import override_settings
import json



def create_statuses() -> None:
    ProjectStatus.objects.all().delete()
    data = [
        ("NEW", "Neu"),
        ("CLASSIFIED", "Klassifiziert"),
        ("GUTACHTEN_OK", "Gutachten OK"),
        ("GUTACHTEN_FREIGEGEBEN", "Gutachten freigegeben"),
        ("IN_PRUEFUNG_ANLAGE_X", "In Prüfung Anlage X"),
        ("FB_IN_PRUEFUNG", "FB in Prüfung"),
        ("ENDGEPRUEFT", "Endgeprüft"),
    ]
    for idx, (key, name) in enumerate(data, start=1):
        ProjectStatus.objects.create(
            name=name,
            key=key,
            ordering=idx,
            is_default=key == "NEW",
            is_done_status=key == "ENDGEPRUEFT",
        )


def setUpModule():
    pass


def create_project(software: list[str] | None = None, **kwargs) -> BVProject:
    projekt = BVProject.objects.create(**kwargs)
    for name in software or []:
        BVSoftware.objects.create(projekt=projekt, name=name)
    return projekt


def seed_test_data(*, skip_prompts: bool = False) -> None:
    """Befüllt die Test-Datenbank mit Initialdaten.

    Bestehende Einträge werden zuvor gelöscht. Optional können die
    Prompt-Definitionen übersprungen werden.
    """
    BVProject.objects.all().delete()
    Prompt.objects.all().delete()
    Tile.objects.all().delete()
    Area.objects.all().delete()
    Anlage2Function.objects.all().delete()
    Anlage2SubQuestion.objects.all().delete()
    Anlage2ColumnHeading.objects.all().delete()
    Anlage2Config.objects.all().delete()
    Anlage1Question.objects.all().delete()
    apps.get_model("core", "Anlage1QuestionVariant").objects.all().delete()
    apps.get_model("core", "LLMRole").objects.all().delete()
    FormatBParserRule.objects.all().delete()
    AntwortErkennungsRegel.objects.all().delete()
    Anlage4Config.objects.all().delete()
    LLMConfig.objects.all().delete()
    from django.apps import apps as django_apps
    from importlib import import_module
    create_initial_data = import_module(
        "core.migrations.0002_seed_initial_data"
    ).create_initial_data
    from ..llm_tasks import (
        ANLAGE1_QUESTIONS,
        _ANLAGE1_INTRO,
        _ANLAGE1_IT,
        _ANLAGE1_SUFFIX,
    )

    try:
        create_initial_data(django_apps, None)
    except LookupError:
        pass
    create_statuses()

    # Anlage1 Fragen aktualisieren
    Anlage1QuestionModel = apps.get_model("core", "Anlage1Question")
    Anlage1QuestionVariant = apps.get_model("core", "Anlage1QuestionVariant")
    for idx, text in enumerate(ANLAGE1_QUESTIONS, start=1):
        try:
            question = Anlage1QuestionModel.objects.get(num=idx)
        except Anlage1QuestionModel.DoesNotExist:
            continue
        question.text = text
        question.parser_enabled = True
        question.llm_enabled = True
        question.save()
        Anlage1QuestionVariant.objects.get_or_create(question=question, text=text)

    if skip_prompts:
        return

    for idx, text in enumerate(ANLAGE1_QUESTIONS, start=1):
        Prompt.objects.update_or_create(name=f"anlage1_q{idx}", defaults={"text": text})

    check_anlage1_text = (
        _ANLAGE1_INTRO
        + ANLAGE1_QUESTIONS[0]
        + "\n"
        + ANLAGE1_QUESTIONS[1]
        + "\n"
        + _ANLAGE1_IT
        + "".join(f"{q}\n" for q in ANLAGE1_QUESTIONS[2:])
        + _ANLAGE1_SUFFIX
    )
    Prompt.objects.update_or_create(name="check_anlage1", defaults={"text": check_anlage1_text})
    Prompt.objects.update_or_create(
        name="check_anlage3_vision",
        defaults={"text": "Prüfe die folgenden Bilder der Anlage. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n"},
    )
    # Weitere Prompts für Tests bereitstellen
    roles = {r.name: r for r in apps.get_model("core", "LLMRole").objects.all()}
    prompt_data = {
        "analyse_anlage2": {
            "text": (
                "Analysiere den folgenden Text und gib eine JSON-Liste von Objekten "
                "mit den Schlüsseln 'funktion', 'technisch_vorhanden', "
                "'einsatz_bei_telefonica', 'zur_lv_kontrolle' und 'ki_beteiligung' zur\n\n"
            )
        },
        "anlage1_email": {
            "text": (
                "Formuliere eine freundliche E-Mail an den Fachbereich. "
                "Wir haben die Anlage 1 geprüft und noch folgende Vorschläge, "
                "bevor der Mitbestimmungsprozess weiter gehen kann. "
                "Bitte fasse die folgenden Vorschläge zusammen:\r\n\r\n"
            )
        },
        "anlage2_ai_involvement_check": {
            "text": (
                "Antworte ausschließlich mit 'Ja' oder 'Nein'. Frage: "
                "Beinhaltet die Funktion '{function_name}' der Software "
                "'{software_name}' typischerweise eine KI-Komponente? "
                "Eine KI-Komponente liegt vor, wenn die Funktion "
                "unstrukturierte Daten (Text, Bild, Ton) verarbeitet, "
                "Sentiment-Analysen durchführt oder nicht-deterministische, "
                "probabilistische Ergebnisse liefert."
            )
        },
        "anlage2_ai_involvement_justification": {
            "text": (
                "Gib eine kurze Begründung, warum die Funktion '{function_name}' "
                "der Software '{software_name}' eine KI-Komponente beinhaltet oder "
                "beinhalten kann, insbesondere im Hinblick auf die Verarbeitung "
                "unstrukturierter Daten oder nicht-deterministischer Ergebnisse."
            )
        },
        "anlage2_feature_justification": {
            "text": (
                "Warum besitzt die Software '{software_name}' typischerweise die "
                "Funktion oder Eigenschaft '{function_name}'?   Ist es möglich "
                "mit der {function_name} eine Leistungskontrolle oder eine "
                "Verhaltenskontrolle  Ist damit eine Leistungskontrolle oder "
                "eine Verhaltenskontrolle im Sinne des §87 Abs. 1 Nr. 6 möglich? "
                "Wenn ja, wie?"
            )
        },
        "anlage2_feature_verification": {
            "text": (
                "Deine einzige Aufgabe ist es, die folgende Frage mit einem einzigen "
                "Wort zu beantworten. Deine Antwort darf AUSSCHLIESSLICH \"Ja\", "
                "\"Nein\", oder \"Unsicher\" sein. Gib keine Einleitung, keine "
                "Begründung und keine weiteren Erklärungen ab.\r\n\r\nFrage: "
                "Besitzt die Software '{software_name}' basierend auf allgemeinem "
                "Wissen typischerweise die Funktion oder Eigenschaft "
                "'{function_name}'?\n\n{gutachten}"
            ),
            "role": roles.get("Standard"),
            "use_system_role": False,
        },
        "check_anlage2_function": {
            "text": (
                "Prüfe anhand des folgenden Textes, ob die genannte Funktion "
                "vorhanden ist. Gib ein JSON mit den Schlüsseln \"technisch_verfuegbar\", "
                "\"einsatz_telefonica\", \"zur_lv_kontrolle\" und \"ki_beteiligung\" "
                "zurück.\n\n"
            )
        },
        "check_anlage3": {"text": "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n"},
        "check_anlage4": {"text": "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n"},
        "check_anlage5": {"text": "Prüfe die folgende Anlage auf Vollständigkeit. Gib ein JSON mit 'ok' und 'hinweis' zurück:\n\n"},
        "classify_system": {
            "text": (
                "Bitte klassifiziere das folgende Softwaresystem. "
                "Gib ein JSON mit den Schlüsseln 'kategorie' und 'begruendung' zurück.\n\n"
            )
        },
        "generate_gutachten": {
            "text": (
                "Erstelle ein tiefgehendes Gutachten zu der Software im Sinne des § 87 Abs. 1 Nr. 6 BetrVG. "
                "Richte das Gutachten ausschließlich an Betriebsräte und überspringe allgemeine Erläuterungen "
                "zu DSGVO oder Datenschutzrecht ebenso musst du nicht erläutern, wann Mitbestimmungsrechte "
                "nach §87 (1) Nr. 6 gelten.\n\nDein Gutachten soll folgende Punkte abdecken: \n\n1. **Mitbestimmungspflichtige Funktionen**   \n- Liste alleFeatures auf, die der Leistungs- oder Verhaltenskontrolle dienen (z. B. Analyse von Nutzungshistorien, App- und Kommunikationsauswertung, Dateizugriffsprotokolle).\n- Erläutere kurz, warum jede einzelne Funktion unter § 87 1 Nr. 6 BetrVG fällt. \n\n2. **Eingriffsintensität aus Mitarbeitersicht**   \n   - Beschreibe, wie stark jede dieser Funktionen in den Arbeitsablauf eingreift und welche Verhaltensaspekte sie überwacht (z. B. Häufigkeit von App-Nutzung, Kommunikationsverhalten, Standortdaten).   \n   - Nutze eine Skala (gering – mittel – hoch) und begründe die Einstufung anhand typischer Betriebsabläufe in einem Telekommunikationsunternehmen. \n\n3. **Betroffene Leistungs- und Verhaltensaspekte**   \n   - Identifiziere konkret, welche Leistungskennzahlen (z. B. Aktivitätszeiten, App-Nutzungsdauer) und Verhaltensmuster (z. B. Kommunikationshäufigkeit, Datenübertragung) erfasst und ausgewertet werden.   \n   - Schätze ab, wie umfassend und detailliert die Auswertung jeweils ausfällt. \n\n4. **Handlungsbedarf für den Betriebsrat**   \n   - Fasse zusammen, bei welchen Funktionen und Einsatzszenarien eine Betriebsvereinbarung zwingend erforderlich ist. \n\n5. **Weitere Mitbestimmungsrechte (Kurzhinweise)**   \n   - Wenn offensichtlich erkennbar ist, dass andere relevante Mitbestimmungsrechte nach BetrVG (z. B. §§ 80 ff. zur Informationspflicht) berührt sind, bewerte kurz, warum diese Software dieses Recht des Betriebsrats berühren könnte. \n\nArbeite strukturiert mit klaren Überschriften und Bullet-Points. Wo sinnvoll, nutze kurze Tabellen oder Zusammenfassungen zur Übersicht. \n. Antworte auf deutsch.\nSoftware: \n"
            ),
            "role": roles.get("Gutachten"),
        },
        "initial_check_knowledge": {
            "text": "Kennst du die Software '{name}'? Antworte ausschließlich mit einem einzigen Wort: 'Ja' oder 'Nein'.",
            "use_system_role": False,
        },
        "initial_check_knowledge_with_context": {
            "text": (
                "Kennst du die Software '{name}'? Hier ist zusätzlicher Kontext, um sie zu identifizieren: \"{user_context}\". "
                "Antworte ausschließlich mit einem einigen Wort: 'Ja' oder 'Nein'."
            )
        },
        "initial_llm_check": {
            "text": (
                "Erstelle eine kurze, technisch korrekte Beschreibung für die Software '{name}'. "
                "Nutze Markdown mit Überschriften, Listen oder Fettdruck, um den Text zu strukturieren. "
                "Erläutere, was sie tut und wie sie typischerweise eingesetzt wird."
            ),
            "role": roles.get("Gutachten"),
        },
    }

    for name, data in prompt_data.items():
        Prompt.objects.update_or_create(
            name=name,
            defaults={
                "text": data["text"],
                "role": data.get("role"),
                "use_system_role": data.get("use_system_role", True),
            },
        )


class NoesisTestCase(TestCase):
    """Basisklasse für alle Tests mit gefüllter Datenbank."""

    @classmethod
    def setUpTestData(cls):
        seed_test_data()
        cls.user = User.objects.create_user("baseuser", password="pass")
        cls.superuser = User.objects.create_superuser(
            "basesuper", "admin@example.com", password="pass"
        )


class BVProjectFileTests(NoesisTestCase):
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
        self.assertListEqual(
            list(projekt.anlagen.values_list("anlage_nr", flat=True)), [1, 2, 3]
        )

    def test_default_flags(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="d",
        )
        self.assertFalse(pf.manual_reviewed)
        self.assertFalse(pf.verhandlungsfaehig)
        pf.manual_reviewed = True
        pf.verhandlungsfaehig = True
        pf.save()
        pf.refresh_from_db()
        self.assertTrue(pf.manual_reviewed)
        self.assertTrue(pf.verhandlungsfaehig)

    def test_json_form_shows_analysis_field_for_anlage3(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=SimpleUploadedFile("a.txt", b"x"),
            text_content="t",
            analysis_json={"ok": True},
        )
        form = BVProjectFileJSONForm(instance=pf)
        self.assertIn("analysis_json", form.fields)

    def test_save_stores_task_id(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        Anlage2Function.objects.create(name="Login")
        with patch("core.models.async_task", return_value="tid1") as mock_task:
            pf = BVProjectFile.objects.create(
                projekt=projekt,
                anlage_nr=2,
                upload=SimpleUploadedFile("a.txt", b"x"),
                text_content="t",
            )
        self.assertEqual(pf.verification_task_id, "tid1")
        mock_task.assert_called_with(
            "core.llm_tasks.check_anlage2_functions",
            projekt.pk,
        )

    def test_is_verification_running(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pf = BVProjectFile(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"x"),
            verification_task_id="tid",
        )
        with patch("core.models.fetch") as mock_fetch:
            mock_fetch.return_value = SimpleNamespace(success=None)
            self.assertTrue(pf.is_verification_running())
            mock_fetch.return_value = SimpleNamespace(success=True)
            self.assertFalse(pf.is_verification_running())

    def test_check_functions_clears_task_id(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"x"),
            verification_task_id="tid",
        )
        Anlage2Function.objects.create(name="Login")
        with patch("core.llm_tasks.query_llm", return_value="{}"):
            check_anlage2_functions(projekt.pk)
        pf.refresh_from_db()
        self.assertEqual(pf.verification_task_id, "")

    def test_template_shows_disabled_state_when_task_running(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"x"),
            verification_task_id="tid",
        )
        self.client.login(username=self.user.username, password="pass")
        with patch("django_q.tasks.fetch") as mock_fetch:
            mock_fetch.return_value = SimpleNamespace(success=None)
            url = reverse("projekt_detail", args=[projekt.pk])
            resp = self.client.get(url)
        self.assertContains(resp, "disabled-btn")


class ProjektFileUploadTests(NoesisTestCase):
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

    def test_pdf_upload_stores_bytes(self):
        pdf = fitz.open()
        pdf.new_page()
        tmp = NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("t.pdf", fh.read())
        Path(tmp.name).unlink(missing_ok=True)

        url = reverse("projekt_file_upload", args=[self.projekt.pk])
        resp = self.client.post(
            url,
            {"anlage_nr": 3, "upload": upload, "manual_comment": ""},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 302)
        file_obj = self.projekt.anlagen.get(anlage_nr=3)
        self.assertEqual(file_obj.text_content, "")

    def test_anlage2_upload_queues_check(self):
        doc = Document()
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Funktion"
        table.cell(0, 1).text = "Technisch vorhanden"
        table.cell(1, 0).text = "Login"
        table.cell(1, 1).text = "Ja"
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("t.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)

        Anlage2Function.objects.create(name="Login")

        url = reverse("projekt_file_upload", args=[self.projekt.pk])
        with patch("core.views.async_task") as mock_async:
            resp = self.client.post(
                url,
                {"anlage_nr": 2, "upload": upload, "manual_comment": ""},
                format="multipart",
            )
        self.assertEqual(resp.status_code, 302)
        pf = self.projekt.anlagen.get(anlage_nr=2)
        self.assertIsNone(pf.analysis_json)
        mock_async.assert_called_with(
            "core.llm_tasks.check_anlage2_functions",
            self.projekt.pk,
        )


class AutoApprovalTests(NoesisTestCase):
    """Tests für die automatische Genehmigung von Dokumenten."""

    def setUp(self) -> None:
        self.user = User.objects.create_user("auto", password="pass")
        self.client.login(username="auto", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")

    def _upload_doc(self, document: Document) -> BVProjectFile:
        """Hilfsfunktion zum Hochladen eines DOCX-Dokuments."""
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        document.save(tmp.name)
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
        return self.projekt.anlagen.get(anlage_nr=1)

    def test_single_page_auto_approved(self):
        doc = Document()
        doc.add_paragraph("Seite 1")
        pf = self._upload_doc(doc)
        self.assertFalse(pf.manual_reviewed)
        self.assertFalse(pf.verhandlungsfaehig)

    def test_multi_page_requires_manual_review(self):
        img = Image.new("RGB", (10, 10), color="red")
        img_tmp = NamedTemporaryFile(delete=False, suffix=".png")
        img.save(img_tmp.name)
        img_tmp.close()

        doc = Document()
        doc.add_paragraph("Seite 1")
        doc.add_page_break()
        doc.add_paragraph("Seite 2")
        doc.add_picture(img_tmp.name)
        Path(img_tmp.name).unlink(missing_ok=True)

        pf = self._upload_doc(doc)
        self.assertFalse(pf.manual_reviewed)
        self.assertFalse(pf.verhandlungsfaehig)

    def test_toggle_manual_review_sets_flag(self):
        doc = Document()
        doc.add_paragraph("Seite 1")
        doc.add_page_break()
        doc.add_paragraph("Seite 2")
        pf = self._upload_doc(doc)

        url = reverse("project_file_toggle_flag", args=[pf.pk, "manual_reviewed"])
        resp = self.client.post(url, {"value": "1"})
        self.assertEqual(resp.status_code, 302)
        pf.refresh_from_db()
        self.assertTrue(pf.manual_reviewed)
        self.assertFalse(pf.verhandlungsfaehig)

    def test_project_status_updated_after_all_anlage3_reviewed(self):
        pf1 = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=3,
            upload=SimpleUploadedFile("a.txt", b"x"),
            text_content="x",
        )
        pf2 = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=3,
            upload=SimpleUploadedFile("b.txt", b"x"),
            text_content="y",
        )

        for pf in (pf1, pf2):
            url = reverse("project_file_toggle_flag", args=[pf.pk, "manual_reviewed"])
            self.client.post(url, {"value": "1"})

        self.projekt.refresh_from_db()
        self.assertEqual(self.projekt.status.key, "ENDGEPRUEFT")


class BVProjectModelTests(NoesisTestCase):
    def test_title_auto_set_from_software(self):
        projekt = BVProject.objects.create(software_typen="A, B", beschreibung="x")
        self.assertEqual(projekt.title, "A, B")

    def test_title_preserved_when_set(self):
        projekt = BVProject.objects.create(
            title="X", software_typen="A", beschreibung="x"
        )
        self.assertEqual(projekt.title, "X")

    def test_save_accepts_list_for_software_typen(self):
        projekt = BVProject.objects.create(
            software_typen=["A", "", "B "],
            beschreibung="x",
        )
        self.assertEqual(projekt.software_typen, "A, B")


class Anlage2FunctionResultModelTests(NoesisTestCase):
    def test_manual_result_field(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        func = Anlage2Function.objects.create(name="Login")
        res = Anlage2FunctionResult.objects.create(
            projekt=projekt,
            funktion=func,
            manual_result={"technisch_vorhanden": True, "ki_beteiligung": False},
            source="manual",
        )
        self.assertTrue(res.manual_result["technisch_vorhanden"])
        self.assertFalse(res.manual_result["ki_beteiligung"])


class WorkflowTests(NoesisTestCase):
    def test_default_status(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.assertEqual(projekt.status.key, "NEW")

    def test_set_project_status(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        set_project_status(projekt, "CLASSIFIED")
        projekt.refresh_from_db()
        self.assertEqual(projekt.status.key, "CLASSIFIED")

    def test_invalid_status(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        with self.assertRaises(ValueError):
            set_project_status(projekt, "XXX")

    def test_set_project_status_new_states(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        for status in [
            "IN_PRUEFUNG_ANLAGE_X",
            "FB_IN_PRUEFUNG",
            "ENDGEPRUEFT",
        ]:
            set_project_status(projekt, status)
            projekt.refresh_from_db()
            self.assertEqual(projekt.status.key, status)

    def test_status_history_created(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.assertEqual(projekt.status_history.count(), 1)
        set_project_status(projekt, "CLASSIFIED")
        self.assertEqual(projekt.status_history.count(), 2)


class BuildRowDataTests(NoesisTestCase):
    def setUp(self):
        self.func = Anlage2Function.objects.create(name="Testfunktion")
        self.form = Anlage2ReviewForm()

    def test_flag_set_on_difference(self):
        analysis = {"Testfunktion": {"technisch_vorhanden": True}}
        verification = {"Testfunktion": {"technisch_vorhanden": False}}
        row = _build_row_data(
            "Testfunktion",
            "Testfunktion",
            self.func.id,
            f"func{self.func.id}_",
            self.form,
            {},
            {},
            {},
            analysis,
            verification,
            {},
            {},
        )
        self.assertTrue(row["requires_manual_review"])

    def test_flag_not_set_when_manual(self):
        analysis = {"Testfunktion": {"technisch_vorhanden": True}}
        verification = {"Testfunktion": {"technisch_vorhanden": False}}
        manual = {"Testfunktion": {"technisch_vorhanden": True}}
        row = _build_row_data(
            "Testfunktion",
            "Testfunktion",
            self.func.id,
            f"func{self.func.id}_",
            self.form,
            {},
            {},
            {},
            analysis,
            verification,
            manual,
            {},
        )
        self.assertFalse(row["requires_manual_review"])


class LLMTasksTests(NoesisTestCase):
    maxDiff = None

    def test_classify_system(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testtext",
        )
        with patch(
            "core.llm_tasks.query_llm",
            return_value='{"kategorie":"X","begruendung":"ok"}',
        ):
            data = classify_system(projekt.pk)
        projekt.refresh_from_db()
        self.assertEqual(projekt.classification_json["kategorie"]["value"], "X")
        self.assertEqual(projekt.status.key, "CLASSIFIED")
        self.assertEqual(data["kategorie"]["value"], "X")

    def test_check_anlage2(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Anlagetext",
        )
        func = Anlage2Function.objects.create(name="Login")
        llm_reply = json.dumps({"technisch_verfuegbar": True})
        with patch("core.llm_tasks.query_llm", return_value=llm_reply) as mock_q:
            data = check_anlage2(projekt.pk)
        mock_q.assert_called()
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertTrue(data["functions"][0]["technisch_verfuegbar"])
        self.assertEqual(data["functions"][0]["source"], "llm")
        res = Anlage2FunctionResult.objects.get(projekt=projekt, funktion=func)
        self.assertEqual(res.source, "llm")

    def test_check_anlage2_functions_stores_result(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
        )
        func = Anlage2Function.objects.create(name="Login")
        llm_reply = json.dumps({"technisch_verfuegbar": True})
        with patch("core.llm_tasks.query_llm", return_value=llm_reply):
            check_anlage2_functions(projekt.pk)
        res = Anlage2FunctionResult.objects.get(projekt=projekt, funktion=func)
        self.assertTrue(res.ai_result["technisch_verfuegbar"])

    def test_check_anlage2_llm_receives_text(self):
        """Der LLM-Prompt enthält den bekannten Text."""
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testinhalt Anlage2",
        )
        func = Anlage2Function.objects.create(name="Login")
        llm_reply = json.dumps({"technisch_verfuegbar": False})
        with patch("core.llm_tasks.query_llm", return_value=llm_reply) as mock_q:
            data = check_anlage2(projekt.pk)
        self.assertIn("Testinhalt Anlage2", mock_q.call_args_list[0].args[0].text)
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertEqual(data["functions"][0]["funktion"], "Login")

    def test_check_anlage2_prompt_contains_text(self):
        """Der Prompt enth\u00e4lt den gesamten Anlagentext."""
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Testinhalt Anlage2",
        )
        func = Anlage2Function.objects.create(name="Login")
        llm_reply = json.dumps({"technisch_verfuegbar": False})
        with patch("core.llm_tasks.query_llm", return_value=llm_reply) as mock_q:
            data = check_anlage2(projekt.pk)
        prompt = mock_q.call_args_list[0].args[0].text
        self.assertIn("Testinhalt Anlage2", prompt)
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertEqual(data["functions"][0]["funktion"], "Login")

    def test_check_anlage2_parser(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        table = doc.add_table(rows=2, cols=5)
        table.cell(0, 0).text = "Funktion"
        table.cell(0, 1).text = "Technisch vorhanden"
        table.cell(0, 2).text = "Einsatz bei Telefónica"
        table.cell(0, 3).text = "Zur LV-Kontrolle"
        table.cell(0, 4).text = "KI-Beteiligung"
        table.cell(1, 0).text = "Login"
        table.cell(1, 1).text = "Ja"
        table.cell(1, 2).text = "Nein"
        table.cell(1, 3).text = "Nein"
        table.cell(1, 4).text = "Ja"
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("b.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=upload,
            text_content="ignored",
        )
        func = Anlage2Function.objects.create(name="Login")

        with patch("core.llm_tasks.query_llm") as mock_q:
            data = check_anlage2(projekt.pk)
        mock_q.assert_not_called()
        expected = {
            "task": "check_anlage2",
            "functions": [
                {
                    "funktion": "Login",
                    "technisch_verfuegbar": {"value": True, "note": None},
                    "ki_beteiligung": {"value": True, "note": None},
                    "source": "parser",
                }
            ],
        }
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertEqual(data, expected)
        self.assertEqual(file_obj.analysis_json, expected)

    def test_run_anlage2_analysis_table(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        table = doc.add_table(rows=2, cols=5)
        table.cell(0, 0).text = "Funktion"
        table.cell(0, 1).text = "Technisch vorhanden"
        table.cell(0, 2).text = "Einsatz bei Telefónica"
        table.cell(0, 3).text = "Zur LV-Kontrolle"
        table.cell(0, 4).text = "KI-Beteiligung"
        table.cell(1, 0).text = "Login"
        table.cell(1, 1).text = "Ja"
        table.cell(1, 2).text = "Nein"
        table.cell(1, 3).text = "Nein"
        table.cell(1, 4).text = "Ja"
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("b.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=upload,
            text_content="ignored",
        )
        func = Anlage2Function.objects.create(name="Login")

        result = run_anlage2_analysis(pf)
        expected = [
            {
                "funktion": "Login",
                "technisch_verfuegbar": {"value": True, "note": None},
                "einsatz_telefonica": {"value": False, "note": None},
                "zur_lv_kontrolle": {"value": False, "note": None},
                "ki_beteiligung": {"value": True, "note": None},
            }
        ]

        pf.refresh_from_db()
        res = Anlage2FunctionResult.objects.get(projekt=projekt, funktion=func)
        self.assertTrue(res.doc_result["technisch_verfuegbar"]["value"])
        self.assertEqual(result, expected)
        self.assertEqual(json.loads(pf.analysis_json), expected)

    def test_run_anlage2_analysis_sets_negotiable_on_match(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        table = doc.add_table(rows=2, cols=5)
        table.cell(0, 0).text = "Funktion"
        table.cell(0, 1).text = "Technisch vorhanden"
        table.cell(0, 2).text = "Einsatz bei Telefónica"
        table.cell(0, 3).text = "Zur LV-Kontrolle"
        table.cell(0, 4).text = "KI-Beteiligung"
        table.cell(1, 0).text = "Login"
        table.cell(1, 1).text = "Ja"
        table.cell(1, 2).text = "Nein"
        table.cell(1, 3).text = "Nein"
        table.cell(1, 4).text = "Ja"
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("b.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=upload,
            text_content="ignored",
        )
        func = Anlage2Function.objects.create(name="Login")
        Anlage2FunctionResult.objects.create(
            projekt=projekt,
            funktion=func,
            ai_result={"technisch_verfuegbar": True},
        )

        run_anlage2_analysis(pf)

        res = Anlage2FunctionResult.objects.get(projekt=projekt, funktion=func)
        self.assertTrue(res.is_negotiable)

    def test_parser_manager_fallback(self):
        class FailParser(AbstractParser):
            name = "fail"

            def parse(self, project_file):
                raise ValueError("boom")

        class DummyParser(AbstractParser):
            name = "dummy"

            def parse(self, project_file):
                return [{"funktion": "Dummy"}]

        parser_manager.register(FailParser)
        parser_manager.register(DummyParser)
        cfg = Anlage2Config.get_instance()
        cfg.parser_order = ["fail", "dummy"]
        cfg.save()

        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        table = doc.add_table(rows=1, cols=1)
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("c.docx", fh.read())
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=upload,
        )

        try:
            result = run_anlage2_analysis(pf)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
            parser_manager._parsers.pop("fail")
            parser_manager._parsers.pop("dummy")
            cfg.parser_order = ["table"]
            cfg.save()

        self.assertEqual(result, [{"funktion": "Dummy"}])

    def test_parser_manager_order(self):
        class P1(AbstractParser):
            name = "one"

            def parse(self, project_file):
                return [{"val": 1}]

        class P2(AbstractParser):
            name = "two"

            def parse(self, project_file):
                return [{"val": 2}]

        parser_manager.register(P1)
        parser_manager.register(P2)
        cfg = Anlage2Config.get_instance()
        cfg.parser_order = ["two", "one"]
        cfg.save()

        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        table = doc.add_table(rows=1, cols=1)
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("d.docx", fh.read())
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=upload,
        )
        try:
            result = run_anlage2_analysis(pf)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
            parser_manager._parsers.pop("one")
            parser_manager._parsers.pop("two")
            cfg.parser_order = ["table"]
            cfg.save()

        self.assertEqual(result, [{"val": 2}])

    def test_parser_manager_selects_best(self):
        class P1(AbstractParser):
            name = "p1"

            def parse(self, project_file):
                return [{"funktion": "A", "technisch_verfuegbar": {"value": False}}]

        class P2(AbstractParser):
            name = "p2"

            def parse(self, project_file):
                return [{"funktion": "A", "technisch_verfuegbar": {"value": True}}]

        parser_manager.register(P1)
        parser_manager.register(P2)
        cfg = Anlage2Config.get_instance()
        cfg.parser_order = ["p1", "p2"]
        cfg.save()

        with patch(
            "core.llm_tasks.parse_anlage2_table", return_value=[]
        ) as m_tab, patch(
            "core.llm_tasks.parse_anlage2_text", return_value=[]
        ) as m_text:
            run_anlage2_analysis(pf)
        m_tab.assert_not_called()
        m_text.assert_called_once()

    def test_run_anlage2_analysis_auto_prefers_table(self):

        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"x"),
            text_content="t",
        )
        cfg = Anlage2Config.get_instance()

        cfg.parser_mode = "auto"
        cfg.save()
        table_result = [{"funktion": "Login"}]
        with patch(
            "core.llm_tasks.parse_anlage2_table", return_value=table_result
        ) as m_tab, patch(
            "core.llm_tasks.parse_anlage2_text", return_value=[{"funktion": "Alt"}]
        ) as m_text:
            result = run_anlage2_analysis(pf)
        m_tab.assert_called_once()
        m_text.assert_not_called()
        self.assertEqual(result, table_result)

    def test_run_anlage2_analysis_auto_fallback_empty_table(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"x"),
            text_content="t",
        )
        cfg = Anlage2Config.get_instance()
        cfg.parser_mode = "auto"
        cfg.save()
        with patch(
            "core.llm_tasks.parse_anlage2_table", return_value=[]
        ) as m_tab, patch(
            "core.llm_tasks.parse_anlage2_text", return_value=[{"funktion": "Login"}]
        ) as m_text:
            result = run_anlage2_analysis(pf)
        m_tab.assert_called_once()
        m_text.assert_called_once()
        self.assertEqual(result, [{"funktion": "Login"}])


    def test_check_anlage2_table_error_fallback(self):

        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pf = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("b.txt", b"x"),
        )

        try:
            result = parser_manager.parse_anlage2(pf)
        finally:
            parser_manager._parsers.pop("p1")
            parser_manager._parsers.pop("p2")
            cfg.parser_order = ["table"]
            cfg.save()

        self.assertTrue(result[0]["technisch_verfuegbar"]["value"])


    def test_analyse_anlage2(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="b")
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text A1",
        )
        doc = Document()
        table = doc.add_table(rows=2, cols=5)
        table.cell(0, 0).text = "Funktion"
        table.cell(0, 1).text = "Technisch vorhanden"
        table.cell(0, 2).text = "Einsatz bei Telefónica"
        table.cell(0, 3).text = "Zur LV-Kontrolle"
        table.cell(0, 4).text = "KI-Beteiligung"
        table.cell(1, 0).text = "Login"
        table.cell(1, 1).text = "Ja"
        table.cell(1, 2).text = "Nein"
        table.cell(1, 3).text = "Nein"
        table.cell(1, 4).text = "Ja"
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("b.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=2,
            upload=upload,
            text_content="- Login",
        )

        data = analyse_anlage2(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=2)
        self.assertEqual(data["missing"]["value"], [])
        self.assertEqual(file_obj.analysis_json["additional"]["value"], [])


    def test_analyse_anlage3_auto_ok(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        doc.add_paragraph("Seite 1")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("c.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=upload,
            text_content="ignored",
        )

        data = analyse_anlage3(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=3)
        self.assertTrue(data["auto_ok"])  # pages <= 1
        self.assertEqual(file_obj.analysis_json["auto_ok"], True)
        if hasattr(file_obj, "verhandlungsfaehig"):
            self.assertTrue(file_obj.verhandlungsfaehig)

    def test_analyse_anlage3_manual_required(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        doc.add_paragraph("Seite 1")
        doc.add_page_break()
        doc.add_paragraph("Seite 2")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("d.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=upload,
            text_content="ignored",
        )

        data = analyse_anlage3(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=3)
        self.assertTrue(data["manual_required"])  # pages > 1
        self.assertEqual(file_obj.analysis_json["manual_required"], True)
        if hasattr(file_obj, "verhandlungsfaehig"):
            self.assertFalse(file_obj.verhandlungsfaehig)

    def test_analyse_anlage3_pdf_auto_ok(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pdf = fitz.open()
        pdf.new_page()
        tmp = NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("c.pdf", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=upload,
            text_content="ignored",
        )

        data = analyse_anlage3(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=3)
        self.assertTrue(data["auto_ok"])  # pages <= 1
        self.assertEqual(file_obj.analysis_json["auto_ok"], True)

    def test_analyse_anlage3_pdf_manual_required(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        pdf = fitz.open()
        pdf.new_page()
        pdf.new_page()
        tmp = NamedTemporaryFile(delete=False, suffix=".pdf")
        pdf.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("d.pdf", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=upload,
            text_content="ignored",
        )

        data = analyse_anlage3(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=3)
        self.assertTrue(data["manual_required"])  # pages > 1
        self.assertEqual(file_obj.analysis_json["manual_required"], True)

    def test_analyse_anlage3_multiple_files(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")

        doc1 = Document()
        doc1.add_paragraph("Seite 1")
        tmp1 = NamedTemporaryFile(delete=False, suffix=".docx")
        doc1.save(tmp1.name)
        tmp1.close()
        with open(tmp1.name, "rb") as fh:
            upload1 = SimpleUploadedFile("e.docx", fh.read())
        Path(tmp1.name).unlink(missing_ok=True)
        pf1 = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=upload1,
            text_content="x",
        )

        doc2 = Document()
        doc2.add_paragraph("Seite 1")
        doc2.add_page_break()
        doc2.add_paragraph("Seite 2")
        tmp2 = NamedTemporaryFile(delete=False, suffix=".docx")
        doc2.save(tmp2.name)
        tmp2.close()
        with open(tmp2.name, "rb") as fh:
            upload2 = SimpleUploadedFile("f.docx", fh.read())
        Path(tmp2.name).unlink(missing_ok=True)
        pf2 = BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=upload2,
            text_content="y",
        )

        analyse_anlage3(projekt.pk)
        pf1.refresh_from_db()
        pf2.refresh_from_db()
        self.assertIsNotNone(pf1.analysis_json)
        self.assertIsNotNone(pf2.analysis_json)

    def test_check_anlage3_vision_stores_json(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        doc.add_paragraph("A")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("g.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=projekt,
            anlage_nr=3,
            upload=upload,
            text_content="ignored",
        )

        llm_reply = json.dumps({"ok": True, "hinweis": "x"})
        with patch("core.llm_tasks.query_llm_with_images", return_value=llm_reply):
            data = check_anlage3_vision(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=3)
        self.assertTrue(data["ok"]["value"])
        self.assertTrue(file_obj.analysis_json["ok"]["value"])

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
        with patch(
            "core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply] * 9
        ):
            data = check_anlage1(projekt.pk)
        file_obj = projekt.anlagen.get(anlage_nr=1)
        answers = [
            ["ACME"],
            ["IT"],
            "leer",
            "raw",
            "Zweck",
            "leer",
            "leer",
            "leer",
            "leer",
        ]
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
            {
                "1": {"answer": "A1", "found_num": None},
                "2": {"answer": "A2", "found_num": None},
            },
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
            {
                "1": {"answer": "A1", "found_num": "1"},
                "2": {"answer": "A2", "found_num": "2"},
            },
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
            side_effect=['{"task": "check_anlage1"}'] + [eval_reply] * enabled_count,
        ) as mock_q:
            data = check_anlage1(projekt.pk)
        prompt = mock_q.call_args_list[0].args[0].text
        self.assertNotIn("Frage 1", prompt)
        self.assertIn("1", data["questions"])
        self.assertIsNone(data["questions"]["1"]["status"])

    def test_parse_anlage2_question_list(self):
        text = "Welche Funktionen bietet das System?\u00b6- Login\u00b6- Suche"
        parsed = _parse_anlage2(text)
        self.assertEqual(parsed, ["Login", "Suche"])

    def test_parse_anlage2_table_llm(self):
        text = "Funktion | Beschreibung\u00b6Login | a\u00b6Suche | b"
        with patch(
            "core.llm_tasks.query_llm", return_value='["Login", "Suche"]'
        ) as mock_q:
            parsed = _parse_anlage2(text)
        mock_q.assert_called_once()
        self.assertEqual(parsed, ["Login", "Suche"])


class PromptTests(NoesisTestCase):
    def test_get_prompt_returns_default(self):
        self.assertEqual(get_prompt("unknown", "foo"), "foo")

    def test_get_prompt_returns_db_value(self):
        p, _ = Prompt.objects.get_or_create(
            name="classify_system", defaults={"text": "orig"}
        )
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

    def test_check_anlage3_vision_prompt_text(self):
        p = Prompt.objects.get(name="check_anlage3_vision")
        expected = (
            "Pr\u00fcfe die folgenden Bilder der Anlage. "
            "Gib ein JSON mit 'ok' und 'hinweis' zur\u00fcck:\n\n"
        )
        self.assertEqual(p.text, expected)


class PromptImportTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("pimport", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="pimport", password="pass")

    def test_import_with_clear_first_replaces_prompts(self):
        Prompt.objects.create(name="old", text="x")
        payload = json.dumps([{"name": "neu", "text": "t"}])
        file = SimpleUploadedFile("p.json", payload.encode("utf-8"))
        url = reverse("admin_prompt_import")
        resp = self.client.post(
            url,
            {"json_file": file, "clear_first": "on"},
            format="multipart",
        )
        self.assertRedirects(resp, reverse("admin_prompts"))
        self.assertEqual(Prompt.objects.count(), 1)
        self.assertTrue(Prompt.objects.filter(name="neu").exists())


class ReportingTests(NoesisTestCase):
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



class ProjektFileCheckViewTests(NoesisTestCase):
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
        llm_reply = json.dumps(
            {
                "companies": None,
                "departments": None,
                "vendors": None,
                "question4_raw": None,
                "purpose_summary": None,
                "documentation_links": None,
                "replaced_systems": None,
                "legacy_functions": None,
                "question9_raw": None,
            }
        )
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch(
            "core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply] * 9
        ):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        file_obj = self.projekt.anlagen.get(anlage_nr=1)
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected["questions"] = {
            str(i): {"answer": "leer", "status": "ok", "hinweis": "", "vorschlag": ""}
            for i in nums
        }
        self.assertEqual(file_obj.analysis_json, expected)

    def test_file_check_pk_endpoint_saves_json(self):
        file_obj = self.projekt.anlagen.get(anlage_nr=1)
        url = reverse("projekt_file_check_pk", args=[file_obj.pk])
        expected = {"task": "check_anlage1"}
        llm_reply = json.dumps(
            {
                "companies": None,
                "departments": None,
                "vendors": None,
                "question4_raw": None,
                "purpose_summary": None,
                "documentation_links": None,
                "replaced_systems": None,
                "legacy_functions": None,
                "question9_raw": None,
            }
        )
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch(
            "core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply] * 9
        ):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        file_obj.refresh_from_db()
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected["questions"] = {
            str(i): {"answer": "leer", "status": "ok", "hinweis": "", "vorschlag": ""}
            for i in nums
        }
        self.assertEqual(file_obj.analysis_json, expected)


class Anlage2ReviewTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("rev", password="pass")
        self.client.login(username="rev", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("c.txt", b"d"),
            text_content="Text",
            analysis_json={
                "functions": [
                    {
                        "funktion": "Login",
                        "technisch_vorhanden": {"value": True, "note": None},
                        "einsatz_bei_telefonica": {"value": False, "note": None},
                        "zur_lv_kontrolle": {"value": False, "note": None},
                        "ki_beteiligung": {"value": True, "note": None},
                    }
                ]
            },
        )
        self.func = Anlage2Function.objects.create(name="Login")
        self.sub = Anlage2SubQuestion.objects.create(funktion=self.func, frage_text="Warum?")

    def test_get_shows_table(self):
        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "Login")
        self.assertContains(resp, "Warum?")
        self.assertContains(resp, f"name=\"func{self.func.id}_technisch_vorhanden\"")

    def test_post_saves_data(self):
        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.post(
            url,
            {
                f"func{self.func.id}_technisch_vorhanden": "on",
                f"sub{self.sub.id}_ki_beteiligung": "on",
            },
        )
        self.assertRedirects(resp, reverse("projekt_detail", args=[self.projekt.pk]))
        self.file.refresh_from_db()
        data = self.file.manual_analysis_json["functions"][str(self.func.id)]
        self.assertTrue(data["technisch_vorhanden"])
        self.assertTrue(data["subquestions"][str(self.sub.id)]["ki_beteiligung"])

    def test_prefill_from_analysis(self):
        """Die Formulardaten verwenden Analysewerte als Vorgabe."""
        self.file.manual_analysis_json = None
        self.file.analysis_json = {
            "functions": [
                {
                    "funktion": "Login",
                    "technisch_vorhanden": {"value": True, "note": None},
                    "einsatz_bei_telefonica": {"value": True, "note": None},
                    "zur_lv_kontrolle": {"value": True, "note": None},
                }
            ]
        }
        self.file.save()

        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.get(url)
        field = f"func{self.func.id}_technisch_vorhanden"
        self.assertTrue(resp.context["form"].initial[field])

    def test_rows_include_lookup_key(self):
        url = reverse("projekt_file_edit_json", args=[self.file.pk])
        resp = self.client.get(url)
        rows = resp.context["rows"]
        self.assertEqual(rows[0]["verif_key"], self.func.name)
        self.assertEqual(
            rows[1]["verif_key"], f"{self.func.name}: {self.sub.frage_text}"
        )

    def test_auto_analysis_runs_once_for_new_file(self):
        pf = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("n.txt", b"x"),
            text_content="t",
        )
        url = reverse("projekt_file_edit_json", args=[pf.pk])

        def _fake(obj):
            obj.analysis_json = {"functions": []}
            obj.save(update_fields=["analysis_json"])
            return []

        with patch("core.views.run_anlage2_analysis", side_effect=_fake) as mock_func:
            self.client.get(url)
            self.client.get(url)
        self.assertEqual(mock_func.call_count, 1)


class WorkerGenerateGutachtenTests(NoesisTestCase):
    def setUp(self):
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("a.txt", b"data"),
            text_content="Text",
        )
        self.knowledge = SoftwareKnowledge.objects.create(
            projekt=self.projekt,
            software_name="A",
            is_known_by_llm=True,
            description="",
        )

    def test_worker_creates_file(self):
        with patch("core.llm_tasks.query_llm", return_value="Text"):
            path = worker_generate_gutachten(self.projekt.pk, self.knowledge.pk)
        self.projekt.refresh_from_db()
        self.assertTrue(self.projekt.gutachten_file.name)
        self.assertEqual(self.projekt.status.key, "GUTACHTEN_OK")
        self.assertEqual(Gutachten.objects.filter(software_knowledge=self.knowledge).count(), 1)
        Path(path).unlink(missing_ok=True)

    def test_worker_updates_existing_gutachten(self):
        Gutachten.objects.create(software_knowledge=self.knowledge, text="Alt")
        with patch("core.llm_tasks.query_llm", return_value="Neu"):
            path = worker_generate_gutachten(self.projekt.pk, self.knowledge.pk)
        gutachten = Gutachten.objects.get(software_knowledge=self.knowledge)
        self.assertEqual(gutachten.text, "Neu")
        self.assertEqual(Gutachten.objects.filter(software_knowledge=self.knowledge).count(), 1)
        Path(path).unlink(missing_ok=True)


class WorkerAnlage3VisionTests(NoesisTestCase):
    def setUp(self):
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        doc = Document()
        doc.add_paragraph("A")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        with open(tmp.name, "rb") as fh:
            upload = SimpleUploadedFile("v.docx", fh.read())
        Path(tmp.name).unlink(missing_ok=True)
        BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=3,
            upload=upload,
            text_content="ignored",
        )

    def test_worker_runs_vision_check(self):
        reply = json.dumps({"ok": True})
        with patch("core.llm_tasks.query_llm_with_images", return_value=reply):
            data = worker_run_anlage3_vision(self.projekt.pk)
        self.assertTrue(data["ok"]["value"])
        file_obj = self.projekt.anlagen.get(anlage_nr=3)
        self.assertTrue(file_obj.analysis_json["ok"]["value"])

    def test_model_name_is_forwarded(self):
        with patch(
            "core.llm_tasks.query_llm_with_images",
            return_value=json.dumps({"ok": False}),
        ) as mock_q:
            worker_run_anlage3_vision(self.projekt.pk, model_name="vision")
        self.assertEqual(mock_q.call_args[0][2], "vision")


class ProjektFileDeleteResultTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("deluser", password="pass")
        self.client.login(username="deluser", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=3,
            upload=SimpleUploadedFile("d.txt", b"data"),
            text_content="Text",
            analysis_json={"auto_ok": True},
            manual_reviewed=True,
            verhandlungsfaehig=True,
        )

    def test_delete_resets_fields(self):
        url = reverse("projekt_file_delete_result", args=[self.file.pk])
        resp = self.client.post(url)
        self.assertRedirects(resp, reverse("anlage3_review", args=[self.projekt.pk]))
        self.file.refresh_from_db()
        self.assertIsNone(self.file.analysis_json)
        self.assertFalse(self.file.manual_reviewed)
        self.assertFalse(self.file.verhandlungsfaehig)


class ProjektFileCheckResultTests(NoesisTestCase):
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
        self.file2 = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("b.txt", b"data"),
            text_content="Text2",
        )

    def test_get_runs_check_and_redirects_to_edit(self):
        url = reverse("projekt_file_check_view", args=[self.file.pk])
        expected = {"task": "check_anlage1"}
        llm_reply = json.dumps(
            {
                "companies": None,
                "departments": None,
                "vendors": None,
                "question4_raw": None,
                "purpose_summary": None,
                "documentation_links": None,
                "replaced_systems": None,
                "legacy_functions": None,
                "question9_raw": None,
            }
        )
        eval_reply = json.dumps({"status": "ok", "hinweis": "", "vorschlag": ""})
        with patch(
            "core.llm_tasks.query_llm", side_effect=[llm_reply] + [eval_reply] * 9
        ):
            resp = self.client.get(url)
        self.assertRedirects(resp, reverse("projekt_file_edit_json", args=[self.file.pk]))
        self.file.refresh_from_db()
        nums = [q.num for q in Anlage1Question.objects.order_by("num")]
        expected["questions"] = {
            str(i): {"answer": "leer", "status": "ok", "hinweis": "", "vorschlag": ""}
            for i in nums
        }
        self.assertEqual(self.file.analysis_json, expected)

    def test_post_triggers_check_and_redirects(self):
        url = reverse("projekt_file_check_view", args=[self.file.pk])
        with patch("core.views.check_anlage1") as mock_func:
            mock_func.return_value = {"task": "check_anlage1"}
            resp = self.client.post(url)
        self.assertRedirects(resp, reverse("projekt_file_edit_json", args=[self.file.pk]))
        mock_func.assert_called_with(self.projekt.pk, model_name=None)

    def test_anlage2_uses_parser_by_default(self):
        url = reverse("projekt_file_check_view", args=[self.file2.pk])
        with patch("core.views.analyse_anlage2") as mock_func:
            mock_func.return_value = {"task": "analyse_anlage2"}
            resp = self.client.get(url)
        self.assertRedirects(resp, reverse("projekt_file_edit_json", args=[self.file2.pk]))
        mock_func.assert_called_with(self.projekt.pk, model_name=None)

    def test_llm_param_triggers_full_check(self):
        url = reverse("projekt_file_check_view", args=[self.file2.pk]) + "?llm=1"
        with patch("core.views.check_anlage2") as mock_func:
            mock_func.return_value = {"task": "check_anlage2"}
            resp = self.client.get(url)
        self.assertRedirects(resp, reverse("projekt_file_edit_json", args=[self.file2.pk]))
        mock_func.assert_called_with(self.projekt.pk, model_name=None)

    def test_anlage3_uses_analysis(self):
        pf = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=3,
            upload=SimpleUploadedFile("c.txt", b"x"),
            text_content="T",
        )
        url = reverse("projekt_file_check_view", args=[pf.pk])
        with patch("core.views.analyse_anlage3") as mock_func:
            mock_func.return_value = {"task": "analyse_anlage3"}
            resp = self.client.get(url)
        self.assertRedirects(resp, reverse("anlage3_review", args=[self.projekt.pk]))
        mock_func.assert_called_with(self.projekt.pk, model_name=None)

    def test_anlage3_llm_param_triggers_vision_check(self):
        pf = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=3,
            upload=SimpleUploadedFile("d.txt", b"x"),
            text_content="T",
        )
        url = reverse("projekt_file_check_view", args=[pf.pk]) + "?llm=1"
        with patch("core.views.check_anlage3_vision") as mock_func:
            mock_func.return_value = {"task": "check_anlage3_vision"}
            resp = self.client.get(url)
        self.assertRedirects(resp, reverse("anlage3_review", args=[self.projekt.pk]))
        mock_func.assert_called_with(self.projekt.pk, model_name=None)

    def test_parse_view_runs_parser(self):
        url = reverse("projekt_file_parse_anlage2", args=[self.file2.pk])
        with patch("core.views.run_anlage2_analysis") as mock_func:
            mock_func.return_value = []
            resp = self.client.get(url)
        self.assertRedirects(resp, reverse("projekt_file_edit_json", args=[self.file2.pk]))
        mock_func.assert_called_with(self.file2)

    def test_parse_view_rejects_other_files(self):
        url = reverse("projekt_file_parse_anlage2", args=[self.file.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


class LLMConfigTests(NoesisTestCase):
    @override_settings(GOOGLE_API_KEY="x")
    @patch("google.generativeai.list_models")
    @patch("google.generativeai.configure")
    def test_ready_populates_models(self, mock_conf, mock_list):
        mock_list.return_value = [
            type("M", (), {"name": "m1"})(),
            type("M", (), {"name": "m2"})(),
        ]
        from core.signals import init_llm_config

        init_llm_config(None)
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
        from core.signals import init_llm_config

        init_llm_config(None)
        cfg = LLMConfig.objects.first()
        self.assertEqual(cfg.available_models, ["new"])
        self.assertTrue(cfg.models_changed)



class Anlage2ConfigSingletonTests(NoesisTestCase):
    def test_single_instance_enforced(self):
        first = Anlage2Config.get_instance()
        from django.db import transaction
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Anlage2Config.objects.create()
        self.assertEqual(Anlage2Config.objects.count(), 1)


class Anlage1EmailTests(NoesisTestCase):
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


class TileVisibilityTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("tileuser", password="pass")
        self.user.groups.add(admin_group)
        work = Area.objects.get_or_create(slug="work", defaults={"name": "Work"})[0]
        self.personal = Area.objects.get_or_create(
            slug="personal", defaults={"name": "Personal"}
        )[0]
        self.talkdiary = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "url_name": "talkdiary_personal",
            },
        )[0]
        self.talkdiary.areas.add(self.personal)
        self.projekt = Tile.objects.get_or_create(
            slug="projektverwaltung",
            defaults={
                "name": "Projektverwaltung",
                "url_name": "projekt_list",
            },
        )[0]
        self.projekt.areas.add(work)
        self.cfg = LLMConfig.objects.first() or LLMConfig.objects.create(
            models_changed=False
        )
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


class LLMConfigNoticeMiddlewareTests(NoesisTestCase):
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


class HomeRedirectTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("redir", password="pass")
        personal = Area.objects.get_or_create(
            slug="personal", defaults={"name": "Personal"}
        )[0]
        tile = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "url_name": "talkdiary_personal",
            },
        )[0]
        tile.areas.add(personal)
        UserTileAccess.objects.create(user=self.user, tile=tile)
        self.client.login(username="redir", password="pass")

    def test_redirect_personal(self):
        resp = self.client.get(reverse("home"))
        self.assertRedirects(resp, reverse("personal"))


class AreaImageTests(NoesisTestCase):
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
        personal, _ = Area.objects.get_or_create(
            slug="personal", defaults={"name": "Personal"}
        )
        work.image.save("w.png", SimpleUploadedFile("w.png", b"d"), save=True)
        personal.image.save("p.png", SimpleUploadedFile("p.png", b"d"), save=True)
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, f'alt="{work.name}"', html=False)
        self.assertContains(resp, f'alt="{personal.name}"', html=False)


class RecordingDeleteTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("recuser", password="pass")
        self.client.login(username="recuser", password="pass")
        self.personal = Area.objects.get_or_create(
            slug="personal", defaults={"name": "Personal"}
        )[0]
        self.tile = Tile.objects.get_or_create(
            slug="talkdiary",
            defaults={
                "name": "TalkDiary",
                "url_name": "talkdiary_personal",
            },
        )[0]
        self.tile.areas.add(self.personal)
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


class ModelSelectionTests(NoesisTestCase):
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


    def test_file_check_uses_category(self):
        url = reverse("projekt_file_check", args=[self.projekt.pk, 1])
        with patch("core.views.check_anlage1") as mock_func:
            mock_func.return_value = {"task": "check_anlage1"}
            resp = self.client.post(url, {"model_category": "anlagen"})
        self.assertEqual(resp.status_code, 200)
        mock_func.assert_called_with(
            self.projekt.pk,
            model_name=LLMConfig.get_instance().anlagen_model,
        )

    def test_forms_show_categories(self):
        edit_url = reverse("projekt_edit", args=[self.projekt.pk])
        resp = self.client.get(edit_url)
        self.assertContains(resp, "Standard")
        self.assertContains(resp, "Gutachten")
        self.assertContains(resp, "Anlagen")

        view_url = reverse(
            "projekt_file_check_view", args=[self.projekt.anlagen.first().pk]
        )
        with patch("core.views.check_anlage1") as mock_func:
            mock_func.return_value = {"task": "check_anlage1"}
            resp = self.client.get(view_url)
        self.assertRedirects(
            resp,
            reverse("projekt_file_edit_json", args=[self.projekt.anlagen.first().pk]),
        )


    def test_functions_check_uses_model(self):
        url = reverse("projekt_functions_check", args=[self.projekt.pk])
        with patch("core.views.check_anlage2_functions") as mock_func:
            mock_func.return_value = []
            resp = self.client.post(url, {"model": "mf"})
        self.assertEqual(resp.status_code, 200)
        mock_func.assert_called_with(self.projekt.pk, model_name="mf")

    def test_prompt_save_triggers_async_check(self):
        url = reverse("projekt_detail", args=[self.projekt.pk])
        with patch("core.views.async_task") as mock_task:
            resp = self.client.post(url, {"project_prompt": "Test"})
        self.assertRedirects(resp, url)
        mock_task.assert_called_with(
            "core.llm_tasks.check_anlage2_functions",
            self.projekt.pk,
        )


class FunctionImportExportTests(NoesisTestCase):
    def setUp(self):
        Anlage2Function.objects.all().delete()
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("adminie", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="adminie", password="pass")

    def test_export_returns_json(self):
        func = Anlage2Function.objects.create(name="Login")
        Anlage2SubQuestion.objects.create(funktion=func, frage_text="Warum?")
        url = reverse("anlage2_function_export")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data[0]["name"], "Login")
        self.assertEqual(data[0]["subquestions"][0]["frage_text"], "Warum?")

    def test_import_creates_functions(self):
        payload = json.dumps([
            {"name": "Login", "subquestions": ["Frage"]}
        ])
        file = SimpleUploadedFile("func.json", payload.encode("utf-8"))
        url = reverse("anlage2_function_import")
        resp = self.client.post(
            url,
            {"json_file": file, "clear_first": "on"},
            format="multipart",
        )
        self.assertRedirects(resp, reverse("anlage2_function_list"))
        self.assertTrue(Anlage2Function.objects.filter(name="Login").exists())

    def test_import_accepts_german_keys(self):
        payload = json.dumps([
            {
                "funktion": "Anwesenheit",
                "unterfragen": [
                    {"frage": "Testfrage"}
                ],
            }
        ])
        file = SimpleUploadedFile("func_de.json", payload.encode("utf-8"))
        url = reverse("anlage2_function_import")
        resp = self.client.post(
            url,
            {"json_file": file, "clear_first": "on"},
            format="multipart",
        )
        self.assertRedirects(resp, reverse("anlage2_function_list"))
        self.assertTrue(Anlage2Function.objects.filter(name="Anwesenheit").exists())
        self.assertEqual(
            Anlage2SubQuestion.objects.filter(funktion__name="Anwesenheit").count(),
            1,
        )


class GutachtenLLMCheckTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("gcheck", password="pass")
        self.client.login(username="gcheck", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.knowledge = SoftwareKnowledge.objects.create(
            projekt=self.projekt,
            software_name="A",
            is_known_by_llm=True,
        )
        self.gutachten = Gutachten.objects.create(software_knowledge=self.knowledge, text="Test")

    def test_endpoint_updates_note(self):
        url = reverse("gutachten_llm_check", args=[self.gutachten.pk])
        with patch("core.views.check_gutachten_functions") as mock_func:
            mock_func.return_value = "Hinweis"
            resp = self.client.post(url)
        self.assertRedirects(resp, reverse("gutachten_view", args=[self.gutachten.pk]))
        self.projekt.refresh_from_db()
        self.assertEqual(self.projekt.gutachten_function_note, "Hinweis")


class FeatureVerificationTests(NoesisTestCase):
    def setUp(self):
        self.projekt = BVProject.objects.create(
            software_typen="Word, Excel",
            beschreibung="x",
        )
        BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),
        )
        self.func = Anlage2Function.objects.create(name="Export")
        self.sub = Anlage2SubQuestion.objects.create(
            funktion=self.func,
            frage_text="Warum?",
        )

    def test_any_yes_returns_true(self):
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Ja", "Nein", "Begruendung", "Nein"],
        ) as mock_q:
            result = worker_verify_feature(self.projekt.pk, "function", self.func.pk)
        self.assertEqual(
            result,
            {
                "technisch_verfuegbar": True,
                "ki_begruendung": "Begruendung",
                "ki_beteiligt": False,
                "ki_beteiligt_begruendung": "",
            },
        )
        self.assertEqual(mock_q.call_count, 4)
        pf = BVProjectFile.objects.get(projekt=self.projekt, anlage_nr=2)
        self.assertEqual(
            pf.verification_json["Export"],
            {
                "technisch_verfuegbar": True,
                "ki_begruendung": "Begruendung",
                "ki_beteiligt": False,
                "ki_beteiligt_begruendung": "",
            },
        )
        res = Anlage2FunctionResult.objects.get(projekt=self.projekt, funktion=self.func)
        self.assertTrue(res.ai_result["technisch_verfuegbar"])

    def test_all_no_returns_false(self):
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Nein", "Nein"],
        ):
            result = worker_verify_feature(self.projekt.pk, "subquestion", self.sub.pk)
        self.assertEqual(
            result,
            {
                "technisch_verfuegbar": False,
                "ki_begruendung": "",
                "ki_beteiligt": None,
                "ki_beteiligt_begruendung": "",
            },
        )
        res = Anlage2FunctionResult.objects.get(projekt=self.projekt, funktion=self.func)
        self.assertFalse(res.ai_result["technisch_verfuegbar"])

    def test_subquestion_context_contains_question(self):
        """Die Subquestion wird korrekt im Kontext übergeben."""
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Nein", "Nein"],
        ) as mock_q:
            worker_verify_feature(self.projekt.pk, "subquestion", self.sub.pk)
        first_call_ctx = mock_q.call_args_list[0].args[1]
        self.assertEqual(first_call_ctx["subquestion_text"], self.sub.frage_text)

    def test_gutachten_text_is_added_to_context(self):
        doc = Document()
        doc.add_paragraph("Info")
        tmp = NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(tmp.name)
        tmp.close()
        dest_dir = Path(settings.MEDIA_ROOT) / "gutachten"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(tmp.name).name
        shutil.copy(tmp.name, dest)
        Path(tmp.name).unlink(missing_ok=True)
        self.projekt.gutachten_file.name = f"gutachten/{dest.name}"
        self.projekt.save(update_fields=["gutachten_file"])
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Ja", "Nein", "B", "Nein"],
        ) as mock_q:
            worker_verify_feature(self.projekt.pk, "function", self.func.pk)
        ctx = mock_q.call_args_list[0].args[1]
        self.assertIn("Info", ctx["gutachten"])
        dest.unlink(missing_ok=True)

    def test_mixed_returns_none(self):
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Unsicher", "Nein"],
        ):
            result = worker_verify_feature(self.projekt.pk, "function", self.func.pk)
        self.assertIsNone(result["technisch_verfuegbar"])
        self.assertEqual(result["ki_begruendung"], "")
        self.assertIsNone(result["ki_beteiligt"])
        self.assertEqual(result["ki_beteiligt_begruendung"], "")

    def test_negotiable_set_on_match(self):
        Anlage2FunctionResult.objects.create(
            projekt=self.projekt,
            funktion=self.func,
            doc_result={"technisch_verfuegbar": {"value": True}},
        )
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Ja", "Nein", "", "Nein"],
        ):
            worker_verify_feature(self.projekt.pk, "function", self.func.pk)
        res = Anlage2FunctionResult.objects.get(projekt=self.projekt, funktion=self.func)
        self.assertTrue(res.is_negotiable)

    def test_negotiable_not_set_on_mismatch(self):
        Anlage2FunctionResult.objects.create(
            projekt=self.projekt,
            funktion=self.func,
            doc_result={"technisch_verfuegbar": {"value": False}},
        )
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Ja", "Nein", "", "Nein"],
        ):
            worker_verify_feature(self.projekt.pk, "function", self.func.pk)
        res = Anlage2FunctionResult.objects.get(projekt=self.projekt, funktion=self.func)
        self.assertFalse(res.is_negotiable)


class InitialCheckTests(NoesisTestCase):
    def setUp(self):
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")

    def test_known_software_stores_description(self):
        with patch(
            "core.llm_tasks.query_llm",
            side_effect=["Ja", "Beschreibung"],
        ) as mock_q:
            sk = SoftwareKnowledge.objects.create(
                projekt=self.projekt,
                software_name="A",
            )
            result = worker_run_initial_check(sk.pk)
        self.assertTrue(result["is_known_by_llm"])
        self.assertEqual(result["description"], "Beschreibung")
        self.assertEqual(mock_q.call_count, 2)
        sk.refresh_from_db()
        self.assertTrue(sk.is_known_by_llm)
        self.assertEqual(sk.description, "Beschreibung")

    def test_unknown_sets_flags(self):
        with patch("core.llm_tasks.query_llm", return_value="Nein") as mock_q:
            sk = SoftwareKnowledge.objects.create(
                projekt=self.projekt,
                software_name="A",
            )
            result = worker_run_initial_check(sk.pk)
        self.assertFalse(result["is_known_by_llm"])
        self.assertEqual(result["description"], "")
        self.assertEqual(mock_q.call_count, 1)
        sk.refresh_from_db()
        self.assertFalse(sk.is_known_by_llm)
        self.assertEqual(sk.description, "")

    def test_context_is_passed_to_prompt(self):
        with patch("core.llm_tasks.query_llm", return_value="Nein") as mock_q:
            sk = SoftwareKnowledge.objects.create(
                projekt=self.projekt,
                software_name="A",
            )
            worker_run_initial_check(sk.pk, user_context="Hint")
        prompt_text = mock_q.call_args[0][0].text
        self.assertIn("Hint", prompt_text)



class EditKIJustificationTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("justi", password="pass")
        self.client.login(username="justi", password="pass")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.file = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"data"),

            verification_json={
                "Export": {"technisch_verfuegbar": True, "ki_begruendung": "Alt"}
            },
        )
        self.func = Anlage2Function.objects.create(name="Export")

    def test_get_returns_form(self):
        url = reverse(
            "edit_ki_justification",
            args=[self.file.pk],
        ) + f"?function={self.func.pk}"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Alt")

    def test_post_updates_value(self):
        url = reverse("edit_ki_justification", args=[self.file.pk])
        resp = self.client.post(
            url,
            {"function": self.func.pk, "ki_begruendung": "Neu"},
        )
        self.assertRedirects(resp, reverse("projekt_file_edit_json", args=[self.file.pk]))
        self.file.refresh_from_db()
        self.assertEqual(
            self.file.verification_json["Export"]["ki_begruendung"],
            "Neu",
        )


class VerificationToInitialTests(NoesisTestCase):
    def setUp(self):
        self.project = BVProject.objects.create(software_typen="A", beschreibung="x")
        BVProjectFile.objects.create(
            projekt=self.project,
            anlage_nr=2,
            upload=SimpleUploadedFile("v.txt", b"data"),
        )
        self.func = Anlage2Function.objects.create(name="Export")
        self.sub = Anlage2SubQuestion.objects.create(
            funktion=self.func,
            frage_text="Warum?",
        )

    def test_conversion_reads_ai_fields(self):
        data = {
            "Export": {
                "technisch_verfuegbar": True,
                "ki_beteiligt": True,
                "ki_beteiligt_begruendung": "Grund",
            },
            "Export: Warum?": {
                "technisch_verfuegbar": False,
                "ki_beteiligt": False,
                "ki_beteiligt_begruendung": "Nein",
            },
        }

        result = _verification_to_initial(data)
        func_data = result["functions"][str(self.func.id)]
        self.assertTrue(func_data["technisch_vorhanden"])
        self.assertTrue(func_data["ki_beteiligt"])
        self.assertEqual(func_data["ki_beteiligt_begruendung"], "Grund")

        sub_data = func_data["subquestions"][str(self.sub.id)]
        self.assertFalse(sub_data["technisch_vorhanden"])
        self.assertFalse(sub_data["ki_beteiligt"])
        self.assertEqual(sub_data["ki_beteiligt_begruendung"], "Nein")


class UserImportExportTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("uadmin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="uadmin", password="pass")

        self.group = Group.objects.create(name="testgroup")
        self.area = Area.objects.get_or_create(slug="work", defaults={"name": "Work"})[0]
        self.tile = Tile.objects.create(slug="t1", name="T", url_name="tile")
        self.tile.areas.add(self.area)

    def test_export_json(self):
        self.user.groups.add(self.group)
        self.user.tiles.add(self.tile)
        self.user.areas.add(self.area)
        url = reverse("admin_export_users_permissions")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        entry = next(u for u in data if u["username"] == "uadmin")
        self.assertIn("testgroup", entry["groups"])
        self.assertIn("work", entry["areas"])
        self.assertIn("tile", entry["tiles"])

    def test_import_creates_user(self):
        payload = json.dumps(
            [
                {
                    "username": "neu",
                    "email": "a@b.c",
                    "groups": ["testgroup"],
                    "areas": ["work"],
                    "tiles": ["tile"],
                }
            ]
        )
        file = SimpleUploadedFile("u.json", payload.encode("utf-8"))
        url = reverse("admin_import_users_permissions")
        resp = self.client.post(url, {"json_file": file}, format="multipart")
        self.assertRedirects(resp, reverse("admin_user_list"))
        user = User.objects.get(username="neu")
        self.assertTrue(user.groups.filter(name="testgroup").exists())
        self.assertTrue(user.areas.filter(slug="work").exists())
        self.assertTrue(user.tiles.filter(url_name="tile").exists())


class Anlage1ImportTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("a1import", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="a1import", password="pass")

    def test_clear_first_resets_questions(self):
        Anlage1Question.objects.create(num=99, text="Alt?", enabled=True)
        payload = json.dumps([{"text": "Neu?"}])
        file = SimpleUploadedFile("a1.json", payload.encode("utf-8"))
        url = reverse("admin_anlage1_import")
        resp = self.client.post(
            url,
            {"json_file": file, "clear_first": "on"},
            format="multipart",
        )
        self.assertRedirects(resp, reverse("admin_anlage1"))
        self.assertEqual(Anlage1Question.objects.count(), 1)
        q = Anlage1Question.objects.first()
        self.assertEqual(q.text, "Neu?")
        self.assertEqual(q.num, 1)

class Anlage2ConfigImportExportTests(NoesisTestCase):
    def setUp(self):
        admin_group = Group.objects.create(name="admin")
        self.user = User.objects.create_user("cfgadmin", password="pass")
        self.user.groups.add(admin_group)
        self.client.login(username="cfgadmin", password="pass")
        self.cfg = Anlage2Config.get_instance()

    def test_export_contains_headings_and_phrases(self):
        Anlage2ColumnHeading.objects.create(
            config=self.cfg,
            field_name="technisch_vorhanden",
            text="Verfügbar?",
        )
        url = reverse("admin_anlage2_config_export")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data["config"]["parser_mode"], self.cfg.parser_mode)
        self.assertEqual(data["config"]["parser_order"], self.cfg.parser_order)
        self.assertIn(
            {"field_name": "technisch_vorhanden", "text": "Verfügbar?"},
            data["alias_headings"],
        )

    def test_import_creates_headings(self):
        payload = json.dumps(
            {
                "config": {
                    "parser_mode": "text_only",
                    "parser_order": ["text"],
                    "enforce_subquestion_override": True,
                    "text_technisch_verfuegbar_true": ["ja"],
                },
                "alias_headings": [
                    {"field_name": "ki_beteiligung", "text": "KI?"}
                ],
            }
        )
        file = SimpleUploadedFile("cfg.json", payload.encode("utf-8"))
        url = reverse("admin_anlage2_config_import")
        resp = self.client.post(url, {"json_file": file}, format="multipart")
        self.assertRedirects(resp, reverse("anlage2_config"))
        self.assertTrue(
            Anlage2ColumnHeading.objects.filter(
                field_name="ki_beteiligung", text="KI?"
            ).exists()
        )
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.parser_mode, "text_only")
        self.assertEqual(self.cfg.parser_order, ["text"])
        self.assertTrue(self.cfg.enforce_subquestion_override)
        self.assertEqual(self.cfg.text_technisch_verfuegbar_true, ["ja"])


class Anlage2ConfigViewTests(NoesisTestCase):
    def setUp(self):
        admin = Group.objects.create(name="admin")
        self.user = User.objects.create_user("cfguser", password="pass")
        self.user.groups.add(admin)
        self.client.login(username="cfguser", password="pass")
        self.cfg = Anlage2Config.get_instance()


    def test_update_parser_mode(self):
        url = reverse("anlage2_config")
        resp = self.client.post(
            url,
            {
                "parser_mode": "text_only",
                "parser_order": ["text"],
                "action": "save_general",
                "active_tab": "general",
            },
        )
        self.assertRedirects(resp, url + "?tab=general")
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.parser_order, ["text"])

    def test_update_parser_order(self):
        url = reverse("anlage2_config")
        resp = self.client.post(
            url,
            {
                "parser_mode": self.cfg.parser_mode,
                "parser_order": ["text"],
                "action": "save_general",
                "active_tab": "general",
            },
        )
        self.assertRedirects(resp, url + "?tab=general")
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.parser_order, ["text"])

    def test_save_table_tab(self):
        url = reverse("anlage2_config")
        resp = self.client.post(
            url,
            {
                "new_field": "technisch_vorhanden",
                "new_text": "Verfügbar?",
                "action": "save_table",
                "active_tab": "table",
            },
        )
        self.assertRedirects(resp, url + "?tab=table")
        self.assertTrue(
            Anlage2ColumnHeading.objects.filter(text="Verfügbar?").exists()
        )

    def test_multiline_phrases_saved(self):
        url = reverse("anlage2_config")
        data = {
            "text_technisch_verfuegbar_true": "ja\nokay\n",
            "parser_mode": self.cfg.parser_mode,
            "parser_order": self.cfg.parser_order,
            "action": "save_text",
            "active_tab": "text",
        }
        for key, _ in PHRASE_TYPE_CHOICES:
            data[f"{key}-TOTAL_FORMS"] = "0"
            data[f"{key}-INITIAL_FORMS"] = "0"
            data[f"{key}-MIN_NUM_FORMS"] = "0"
            data[f"{key}-MAX_NUM_FORMS"] = "1000"
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 200)
        self.cfg.refresh_from_db()
        self.assertEqual(self.cfg.text_technisch_verfuegbar_true, ["ja", "okay"])


class AjaxAnlage2ReviewTests(NoesisTestCase):
    def setUp(self):
        self.user = User.objects.create_user("reviewer", password="pw")
        self.client.login(username="reviewer", password="pw")
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        self.pf = BVProjectFile.objects.create(
            projekt=self.projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.txt", b"x"),
        )
        self.func = Anlage2Function.objects.create(name="Login")

    def test_manual_result_saved(self):
        url = reverse("ajax_save_anlage2_review")
        resp = self.client.post(
            url,
            data=json.dumps({"project_file_id": self.pf.pk, "function_id": self.func.pk, "status": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        res = Anlage2FunctionResult.objects.get(projekt=self.projekt, funktion=self.func)
        self.assertTrue(res.manual_result["technisch_vorhanden"])

    def test_gap_generated_on_difference(self):
        Anlage2FunctionResult.objects.create(
            projekt=self.projekt,
            funktion=self.func,
            ai_result={"technisch_verfuegbar": True},
        )
        url = reverse("ajax_save_anlage2_review")

        def immediate(name, *args):
            self.assertEqual(name, "core.llm_tasks.worker_generate_gap_summary")
            worker_generate_gap_summary(*args)

        with patch("core.views.async_task", side_effect=immediate), patch(
            "core.llm_tasks.query_llm",
            return_value="Abweichung",
        ):
            resp = self.client.post(
                url,
                data=json.dumps({
                    "project_file_id": self.pf.pk,
                    "function_id": self.func.pk,
                    "status": False,
                }),
                content_type="application/json",
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("gap_summary"), "Abweichung")
        res = Anlage2FunctionResult.objects.get(projekt=self.projekt, funktion=self.func)
        self.assertEqual(res.gap_summary, "Abweichung")

    def test_manual_sets_negotiable(self):
        url = reverse("ajax_save_anlage2_review")
        resp = self.client.post(
            url,
            data=json.dumps({"project_file_id": self.pf.pk, "function_id": self.func.pk, "status": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        res = Anlage2FunctionResult.objects.get(projekt=self.projekt, funktion=self.func)
        self.assertTrue(res.is_negotiable)


