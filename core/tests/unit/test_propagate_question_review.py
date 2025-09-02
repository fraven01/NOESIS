import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from ..base import NoesisTestCase
from ...models import BVProject, BVProjectFile
from ...utils import propagate_question_review

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("seed_db")]


class PropagateQuestionReviewTests(NoesisTestCase):
    def test_sets_verhandlungsfaehig_flag(self):
        projekt = BVProject.objects.create(software_typen="A", beschreibung="x")
        parent = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("p.txt", b"x"),
            analysis_json={"questions": {"1": {"answer": "alt"}}},
            question_review={"1": {"ok": True}},
            verhandlungsfaehig=True,
        )

        current_changed = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("c.txt", b"x"),
            analysis_json={"questions": {"1": {"answer": "neu"}}},
            parent=parent,
        )
        propagate_question_review(parent, current_changed)
        current_changed.refresh_from_db()
        assert current_changed.question_review["1"]["ok"] is False
        assert not current_changed.verhandlungsfaehig

        current_same = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=SimpleUploadedFile("s.txt", b"x"),
            analysis_json={"questions": {"1": {"answer": "alt"}}},
            parent=parent,
        )
        propagate_question_review(parent, current_same)
        current_same.refresh_from_db()
        assert current_same.question_review["1"]["ok"] is True
        assert current_same.verhandlungsfaehig
