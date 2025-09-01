import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from ..base import NoesisTestCase
from ...models import BVProject, BVProjectFile

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("seed_db")]


class CompareVersionsAnlage1Tests(NoesisTestCase):
    def _create_versions(self) -> tuple[str, BVProjectFile]:
        """Erzeugt zwei Versionen einer Anlage und liefert URL und aktuelle Datei."""

        # Arrange
        user = User.objects.create_user("u1", password="pass")
        self.client.login(username="u1", password="pass")
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        parent = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("p.txt", b"data"),
            analysis_json={"questions": {"1": {"answer": "alt"}}},
            question_review={"1": {"hinweis": "H"}},
        )
        current = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("c.txt", b"data"),
            parent=parent,
            analysis_json={"questions": {"1": {"answer": "neu"}}},
        )
        url = reverse("compare_versions", args=[current.pk])
        return url, current

    def test_gap_and_diff_display(self) -> None:
        """Prüft, ob Unterschiede, Antworten und Hinweise angezeigt werden."""

        # Arrange
        url, _ = self._create_versions()

        # Act
        resp = self.client.get(url)

        # Assert
        content = resp.content.decode()
        assert resp.status_code == 200
        assert "Hinweis: H" in content
        assert "alt" in content and "neu" in content
        assert "Gap hinzufügen" not in content
        assert "bg-warning/20" in content

    def test_negotiate_sets_flag(self) -> None:
        """Verhandlungsflag wird nach POST gesetzt."""

        # Arrange
        url, current = self._create_versions()

        # Act
        self.client.post(url, {"action": "negotiate"})
        current.refresh_from_db()

        # Assert
        assert current.verhandlungsfaehig, "Verhandlungsstatus sollte gesetzt werden"

    def test_negotiate_question_marks_ok(self) -> None:
        """POST mit question setzt das Review und nicht den Datei-Status."""

        # Arrange
        url, current = self._create_versions()

        # Act
        self.client.post(url, {"action": "negotiate", "question": "1"})
        current.refresh_from_db()

        # Assert
        assert current.question_review["1"]["ok"] is True
        assert not current.verhandlungsfaehig
