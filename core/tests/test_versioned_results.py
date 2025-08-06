from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import (
    Anlage2Function,
    AnlagenFunktionsMetadaten,
    BVProject,
    BVProjectFile,
    FunktionsErgebnis,
)
from core.views import _verification_to_initial
from .test_general import create_statuses


def test_funktions_ergebnisse_sind_versionsabhaengig(db):
    """Prüft, dass Ergebnisse pro Anlagen-Version getrennt gespeichert werden."""
    create_statuses()
    projekt = BVProject.objects.create(title="P")
    funktion = Anlage2Function.objects.create(name="Login")
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


def test_bvprojectfile_anlage_nr_can_be_null(db):
    """Erlaubt das Anlegen einer Datei ohne Anlagen-Nummer."""
    create_statuses()
    projekt = BVProject.objects.create(title="P2")
    pf = BVProjectFile.objects.create(
        project=projekt,
        anlage_nr=None,
        upload=SimpleUploadedFile("a.txt", b"a"),
    )
    pf.refresh_from_db()
    assert pf.anlage_nr is None
    assert BVProjectFile.objects.filter(anlage_nr__isnull=True).exists()
