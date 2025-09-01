import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from ..base import NoesisTestCase
from ...models import (
    BVProject,
    BVProjectFile,
    Anlage2Function,
    AnlagenFunktionsMetadaten,
    ZweckKategorieA,
    Anlage5Review,
)
from ...utils import has_any_gap
from ...utils import get_project_file


pytestmark = pytest.mark.unit


class HasAnyGapTests(NoesisTestCase):
    def setUp(self):
        self.projekt = BVProject.objects.create(software_typen="A", beschreibung="x")

    def _file(self, nr: int) -> BVProjectFile:
        return BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=nr,
            upload=SimpleUploadedFile(f"a{nr}.txt", b"x"),
        )

    def test_no_files_no_gap(self):
        assert has_any_gap(self.projekt) is False

    # --- Versionierung / aktive Datei-Logik ---
    def test_versioning_ignores_inactive_newer_anlage1(self):
        # v1 aktiv, keine Vorschläge
        pf1_v1 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a1_v1.txt", b"x"),
            question_review={"1": {"vorschlag": ""}},
        )
        # v2 inaktiv, hätte Vorschläge -> darf NICHT zählen
        pf1_v2 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            version=2,
            is_active=False,
            upload=SimpleUploadedFile("a1_v2.txt", b"x"),
            question_review={"1": {"vorschlag": "Bitte prüfen"}},
        )
        assert has_any_gap(self.projekt) is False

    def test_versioning_picks_highest_active_version_anlage1(self):
        # v1 aktiv, hat Vorschlag
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a1_v1.txt", b"x"),
            question_review={"1": {"vorschlag": "Alt"}},
        )
        # v2 aktiv, KEIN Vorschlag -> sollte v2 ziehen und damit kein GAP
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            version=2,
            is_active=True,
            upload=SimpleUploadedFile("a1_v2.txt", b"x"),
            question_review={"1": {"vorschlag": ""}},
        )
        assert has_any_gap(self.projekt) is False

    def test_versioning_anlage4_manual_comment_active_only(self):
        # v2 inaktiv mit Kommentar -> ignorieren
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=4,
            version=2,
            is_active=False,
            upload=SimpleUploadedFile("a4_v2.txt", b"x"),
            manual_comment="Hinweis",
        )
        # v1 aktiv ohne Kommentar
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=4,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a4_v1.txt", b"x"),
            manual_comment="",
        )
        assert has_any_gap(self.projekt) is False

    def test_versioning_anlage2_metadata_active_only(self):
        func = Anlage2Function.objects.create(name="Bericht")
        # v2 inaktiv mit Note -> ignorieren
        pf2_v2 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=2,
            version=2,
            is_active=False,
            upload=SimpleUploadedFile("a2_v2.txt", b"x"),
        )
        AnlagenFunktionsMetadaten.objects.create(
            anlage_datei=pf2_v2,
            funktion=func,
            supervisor_notes="Bitte prüfen",
        )
        # v1 aktiv ohne Notes/Override
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=2,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a2_v1.txt", b"x"),
        )
        assert has_any_gap(self.projekt) is False

    # --- Direkte Tests für get_project_file ---
    def test_get_project_file_specific_version(self):
        p = self.projekt
        f1 = BVProjectFile.objects.create(
            project=p,
            anlage_nr=3,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a3_v1.txt", b"x"),
        )
        f2 = BVProjectFile.objects.create(
            project=p,
            anlage_nr=3,
            version=2,
            is_active=False,
            upload=SimpleUploadedFile("a3_v2.txt", b"x"),
        )
        assert get_project_file(p, 3, version=1).id == f1.id
        assert get_project_file(p, 3, version=2).id == f2.id

    def test_get_project_file_highest_active_version(self):
        p = self.projekt
        # v1 aktiv, v2 aktiv -> erwarte v2
        BVProjectFile.objects.create(
            project=p,
            anlage_nr=6,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a6_v1.txt", b"x"),
        )
        f2 = BVProjectFile.objects.create(
            project=p,
            anlage_nr=6,
            version=2,
            is_active=True,
            upload=SimpleUploadedFile("a6_v2.txt", b"x"),
        )
        assert get_project_file(p, 6).id == f2.id

    # --- Lösch-/Rollback-Szenarien für Datenkonsistenz ---
    def test_delete_latest_active_restores_previous_state_anlage1(self):
        # v1 aktiv ohne Vorschläge, v2 aktiv mit Vorschlag -> GAP
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a1_v1.txt", b"x"),
            question_review={"1": {"vorschlag": ""}},
        )
        pf_latest = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=1,
            version=2,
            is_active=True,
            upload=SimpleUploadedFile("a1_v2.txt", b"x"),
            question_review={"1": {"vorschlag": "Bitte ergänzen"}},
        )
        assert has_any_gap(self.projekt) is True
        # Lösche die neueste aktive Version -> kein GAP mehr
        pf_latest.delete()
        assert has_any_gap(self.projekt) is False

    def test_delete_latest_active_restores_previous_state_anlage2(self):
        func = Anlage2Function.objects.create(name="Reporting")
        # v1 aktiv ohne Notes/Override, v2 aktiv mit Supervisor-Note -> GAP
        pf_v1 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=2,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a2_v1.txt", b"x"),
        )
        pf_v2 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=2,
            version=2,
            is_active=True,
            upload=SimpleUploadedFile("a2_v2.txt", b"x"),
        )
        AnlagenFunktionsMetadaten.objects.create(
            anlage_datei=pf_v2,
            funktion=func,
            supervisor_notes="Bitte prüfen",
        )
        assert has_any_gap(self.projekt) is True
        pf_v2.delete()
        assert has_any_gap(self.projekt) is False

    def test_delete_latest_active_restores_previous_state_anlage4(self):
        # v1 aktiv ohne Kommentar, v2 aktiv mit Kommentar -> GAP
        BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=4,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a4_v1.txt", b"x"),
            manual_comment="",
        )
        pf_v2 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=4,
            version=2,
            is_active=True,
            upload=SimpleUploadedFile("a4_v2.txt", b"x"),
            manual_comment="Hinweis",
        )
        assert has_any_gap(self.projekt) is True
        pf_v2.delete()
        assert has_any_gap(self.projekt) is False

    def test_delete_latest_active_restores_previous_state_anlage5(self):
        # Universe of purposes (nutze vorhandene + ggf. neu angelegte)
        ZweckKategorieA.objects.get_or_create(beschreibung="A")
        ZweckKategorieA.objects.get_or_create(beschreibung="B")
        # v1 aktiv: vollständig, keine Sonstigen -> kein GAP
        pf_v1 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=5,
            version=1,
            is_active=True,
            upload=SimpleUploadedFile("a5_v1.txt", b"x"),
        )
        r1 = Anlage5Review.objects.create(project_file=pf_v1, sonstige_zwecke="")
        r1.found_purposes.add(*list(ZweckKategorieA.objects.all()))
        # v2 aktiv: unvollständig -> GAP
        pf_v2 = BVProjectFile.objects.create(
            project=self.projekt,
            anlage_nr=5,
            version=2,
            is_active=True,
            upload=SimpleUploadedFile("a5_v2.txt", b"x"),
        )
        r2 = Anlage5Review.objects.create(project_file=pf_v2, sonstige_zwecke="")
        # absichtlich unvollständig: nur einen der Zwecke hinzufügen
        r2.found_purposes.add(ZweckKategorieA.objects.first())
        assert has_any_gap(self.projekt) is True
        pf_v2.delete()
        assert has_any_gap(self.projekt) is False

    def test_anlage1_question_review_triggers_gap(self):
        pf1 = self._file(1)
        pf1.question_review = {"1": {"vorschlag": "Bitte ergänzen."}}
        pf1.save()
        assert has_any_gap(self.projekt) is True

    def test_anlage2_metadata_triggers_gap_by_override_false(self):
        pf2 = self._file(2)
        func = Anlage2Function.objects.create(name="Login")
        AnlagenFunktionsMetadaten.objects.create(
            anlage_datei=pf2,
            funktion=func,
            is_negotiable_manual_override=False,
        )
        assert has_any_gap(self.projekt) is True

    def test_anlage2_metadata_triggers_gap_by_supervisor_notes(self):
        pf2 = self._file(2)
        func = Anlage2Function.objects.create(name="Export")
        AnlagenFunktionsMetadaten.objects.create(
            anlage_datei=pf2,
            funktion=func,
            supervisor_notes="Bitte prüfen",
        )
        assert has_any_gap(self.projekt) is True

    def test_anlage2_metadata_no_gap_when_all_overridden_true_and_no_notes(self):
        pf2 = self._file(2)
        func = Anlage2Function.objects.create(name="Analyse")
        AnlagenFunktionsMetadaten.objects.create(
            anlage_datei=pf2,
            funktion=func,
            is_negotiable_manual_override=True,
            supervisor_notes="",
        )
        # Anlage 2 allein erzeugt hier keinen GAP
        assert has_any_gap(self.projekt) is False

    def test_anlage4_manual_comment_triggers_gap(self):
        pf4 = self._file(4)
        pf4.manual_comment = " Hinweis vorhanden "
        pf4.save()
        assert has_any_gap(self.projekt) is True

    def test_anlage5_review_triggers_gap_on_incomplete_purposes(self):
        # Setup purposes universe
        a = ZweckKategorieA.objects.create(beschreibung="A")
        ZweckKategorieA.objects.create(beschreibung="B")

        pf5 = self._file(5)
        review = Anlage5Review.objects.create(project_file=pf5, sonstige_zwecke="")
        review.found_purposes.add(a)  # 1 of 2 -> incomplete

        assert has_any_gap(self.projekt) is True

    def test_anlage5_review_triggers_gap_on_other_text(self):
        ZweckKategorieA.objects.create(beschreibung="A")
        pf5 = self._file(5)
        Anlage5Review.objects.create(project_file=pf5, sonstige_zwecke="Sonstiges")
        assert has_any_gap(self.projekt) is True

    def test_anlage5_complete_no_gap(self):
        # All purposes found and no other text -> no GAP from A5
        ZweckKategorieA.objects.get_or_create(beschreibung="A")
        ZweckKategorieA.objects.get_or_create(beschreibung="B")
        pf5 = self._file(5)
        review = Anlage5Review.objects.create(project_file=pf5, sonstige_zwecke="")
        review.found_purposes.add(*list(ZweckKategorieA.objects.all()))
        assert has_any_gap(self.projekt) is False
