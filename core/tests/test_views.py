import os
import shutil
import tempfile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from core.models import BVProject, Recording


class ProjectViewTests(TestCase):
    """Integrationstests für Projektansichten."""

    def setUp(self):
        self.user = User.objects.create_user(username="user", password="pass")
        self.client.login(username="user", password="pass")

    def test_projekt_create_and_edit(self):
        resp = self.client.post(
            reverse("projekt_create"),
            {"beschreibung": "desc", "software_typen": "Alpha"},
        )
        projekt = BVProject.objects.get()
        self.assertRedirects(resp, reverse("projekt_detail", args=[projekt.pk]))
        self.assertEqual(projekt.title, "Alpha")

        resp = self.client.post(
            reverse("projekt_edit", args=[projekt.pk]),
            {"beschreibung": "neu", "software_typen": "Alpha, Beta"},
        )
        self.assertRedirects(resp, reverse("projekt_detail", args=[projekt.pk]))
        projekt.refresh_from_db()
        self.assertEqual(projekt.software_typen, "Alpha, Beta")
        self.assertEqual(projekt.title, "Alpha, Beta")


class AdminDeleteTests(TestCase):
    """Testet den Admin-Löschworkflow für Aufnahmen."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.admin = User.objects.create_superuser(
            username="admin", email="a@example.com", password="pass"
        )
        self.client.login(username="admin", password="pass")

        audio = SimpleUploadedFile("a.wav", b"a")
        trans = SimpleUploadedFile("a.md", b"t")
        self.rec1 = Recording.objects.create(
            user=self.admin,
            bereich=Recording.WORK,
            audio_file=audio,
            transcript_file=trans,
        )
        self.rec2 = Recording.objects.create(
            user=self.admin,
            bereich=Recording.WORK,
            audio_file=SimpleUploadedFile("b.wav", b"b"),
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media_root)

    def test_admin_deletes_recordings(self):
        resp = self.client.post(
            reverse("admin_talkdiary"), {"delete": [self.rec1.id, self.rec2.id]}
        )
        self.assertRedirects(resp, reverse("admin_talkdiary"))
        self.assertFalse(Recording.objects.filter(id=self.rec1.id).exists())
        self.assertFalse(Recording.objects.filter(id=self.rec2.id).exists())
        self.assertFalse(
            os.path.exists(os.path.join(self.media_root, self.rec1.audio_file.name))
        )
