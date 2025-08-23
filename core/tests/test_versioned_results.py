from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.urls import reverse
from docx import Document
from tempfile import NamedTemporaryFile
from pathlib import Path
from unittest.mock import patch

from core.models import (
    Anlage2Function,
    AnlagenFunktionsMetadaten,
    BVProject,
    BVProjectFile,
    FunktionsErgebnis,
    ProjectStatus,
)
from core.views import _verification_to_initial, _save_project_file


def test_funktions_ergebnisse_sind_versionsabhaengig(db):
    """Prüft, dass Ergebnisse pro Anlagen-Version getrennt gespeichert werden."""
    ProjectStatus.objects.create(name="Offen", is_default=True)
    projekt = BVProject.objects.create(title="P")
    funktion = Anlage2Function.objects.create(name="Anmelden")
    pf1 = BVProjectFile.objects.create(
        project=projekt,
        anlage_nr=2,
        upload=SimpleUploadedFile("a.txt", b"a"),
        version=1,
    )
    pf2 = BVProjectFile.objects.create(
        project=projekt,
        anlage_nr=2,
        upload=SimpleUploadedFile("b.txt", b"b"),
        version=2,
    )

    AnlagenFunktionsMetadaten.objects.create(anlage_datei=pf1, funktion=funktion)
    AnlagenFunktionsMetadaten.objects.create(anlage_datei=pf2, funktion=funktion)

    FunktionsErgebnis.objects.create(
        anlage_datei=pf1,
        funktion=funktion,
        quelle="ki",
        technisch_verfuegbar=True,
    )
    FunktionsErgebnis.objects.create(
        anlage_datei=pf2,
        funktion=funktion,
        quelle="ki",
        technisch_verfuegbar=False,
    )

    data1 = _verification_to_initial(pf1)
    data2 = _verification_to_initial(pf2)

    fid = str(funktion.id)
    assert data1["functions"][fid]["technisch_vorhanden"] is True
    assert data2["functions"][fid]["technisch_vorhanden"] is False


def test_neue_version_nutzt_vorhandene_ki_ergebnisse(db):
    """Bei vorhandenen Ergebnissen wird keine neue KI-Prüfung gestartet."""
    ProjectStatus.objects.create(name="Offen", is_default=True)
    projekt = BVProject.objects.create(title="P")
    funktion = Anlage2Function.objects.create(name="Anmelden")
    pf1 = BVProjectFile.objects.create(
        project=projekt,
        anlage_nr=2,
        upload=SimpleUploadedFile("a.txt", b"a"),
        version=1,
    )
    FunktionsErgebnis.objects.create(
        anlage_datei=pf1,
        funktion=funktion,
        quelle="ki",
    )
    pf2 = BVProjectFile.objects.create(
        project=projekt,
        anlage_nr=2,
        upload=SimpleUploadedFile("b.txt", b"b"),
        version=2,
    )
    tasks = pf2.get_analysis_tasks()
    assert tasks == [("core.llm_tasks.worker_run_anlage2_analysis", pf2.pk)]


def test_new_version_copies_ai_results(db):
    """KI-Ergebnisse werden in neue Versionen übernommen."""
    ProjectStatus.objects.create(name="Offen", is_default=True)
    projekt = BVProject.objects.create(title="P")
    funktion = Anlage2Function.objects.create(name="Anmelden")
    with patch("core.signals.start_analysis_for_file", return_value="tid"):
        pf1 = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=2,
            upload=SimpleUploadedFile("a.docx", b"a"),
            text_content="a",
            verification_json={"Anmelden": {"ki_begruendung": "x"}},
            processing_status=BVProjectFile.COMPLETE,
        )
    AnlagenFunktionsMetadaten.objects.create(anlage_datei=pf1, funktion=funktion)
    FunktionsErgebnis.objects.create(
        anlage_datei=pf1,
        funktion=funktion,
        quelle="ki",
        technisch_verfuegbar=True,
    )

    doc = Document()
    doc.add_paragraph("neu")
    tmp = NamedTemporaryFile(delete=False, suffix=".docx")
    doc.save(tmp.name)
    tmp.close()
    with open(tmp.name, "rb") as fh:
        upload = SimpleUploadedFile("b.docx", fh.read())
    Path(tmp.name).unlink(missing_ok=True)
    with patch("core.signals.start_analysis_for_file", return_value="tid"):
        pf2 = _save_project_file(projekt, upload=upload, anlage_nr=2)

    assert pf2.verification_json == pf1.verification_json
    assert pf2.processing_status == BVProjectFile.COMPLETE
    assert FunktionsErgebnis.objects.filter(
        anlage_datei=pf2, funktion=funktion, quelle="ki", technisch_verfuegbar=True
    ).exists()
    assert AnlagenFunktionsMetadaten.objects.filter(
        anlage_datei=pf2, funktion=funktion
    ).exists()


def test_manual_ai_check_disabled(client, db):
    """Manuelle KI-Prüfung ist gesperrt, wenn Ergebnisse existieren."""
    ProjectStatus.objects.create(name="Offen", is_default=True)
    user = User.objects.create_user("u")
    client.force_login(user)
    projekt = BVProject.objects.create(title="P")
    funktion = Anlage2Function.objects.create(name="Anmelden")
    pf1 = BVProjectFile.objects.create(
        project=projekt,
        anlage_nr=2,
        upload=SimpleUploadedFile("a.docx", b"a"),
        text_content="a",
    )
    AnlagenFunktionsMetadaten.objects.create(anlage_datei=pf1, funktion=funktion)
    FunktionsErgebnis.objects.create(anlage_datei=pf1, funktion=funktion, quelle="ki")

    url = reverse("projekt_functions_check", args=[projekt.pk])
    resp = client.post(url)
    assert resp.status_code == 400

    feature_url = reverse("anlage2_feature_verify", args=[pf1.pk])
    resp2 = client.post(feature_url, {"function_id": funktion.pk})
    assert resp2.status_code == 400
