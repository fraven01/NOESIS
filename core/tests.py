from django.test import TestCase

from .models import BVProject


class BVProjectModelTest(TestCase):
    """Tests für das BVProject-Modell."""

    def test_duplicate_titles_allowed(self):
        """Mehrere Projekte mit identischen Software-Typen können gespeichert werden."""
        BVProject.objects.create(software_typen="Test")
        BVProject.objects.create(software_typen="Test")
        self.assertEqual(BVProject.objects.filter(software_typen="Test").count(), 2)
