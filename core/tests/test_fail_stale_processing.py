from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.models import BVProject, BVProjectFile, ProjectStatus


class FailStaleProcessingCommandTests(TestCase):
    """Tests für den fail_stale_processing-Command."""

    def test_marks_old_entries_failed(self) -> None:
        status = ProjectStatus.objects.create(name="Init", key="init")
        projekt = BVProject.objects.create(title="Test", status=status)
        upload = SimpleUploadedFile("test.txt", b"x")
        pf = BVProjectFile.objects.create(
            project=projekt,
            anlage_nr=1,
            upload=upload,
            processing_status=BVProjectFile.PROCESSING,
        )
        BVProjectFile.objects.filter(pk=pf.pk).update(
            created_at=timezone.now() - timedelta(minutes=120)
        )
        call_command("fail_stale_processing", minutes=60)
        pf.refresh_from_db()
        self.assertEqual(pf.processing_status, BVProjectFile.FAILED)
