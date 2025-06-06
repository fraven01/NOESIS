from django.test import TestCase
from core.forms import BVProjectForm
from core.models import BVProject


class BVProjectFormTests(TestCase):
    """Tests für das Formular BVProjectForm."""

    def test_clean_software_typen_bereinigt(self):
        form = BVProjectForm(
            data={"beschreibung": "", "software_typen": "  Alpha , Beta ,,  Gamma  "}
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["software_typen"], "Alpha, Beta, Gamma")

    def test_clean_software_typen_leer(self):
        form = BVProjectForm(data={"beschreibung": "", "software_typen": " , , "})
        self.assertFalse(form.is_valid())
        self.assertIn("Software-Typen dürfen nicht leer sein.", form.errors["software_typen"][0])

    def test_save_setzt_titel(self):
        form = BVProjectForm(
            data={"beschreibung": "desc", "software_typen": "Alpha, Beta"}
        )
        self.assertTrue(form.is_valid())
        projekt = form.save()
        self.assertEqual(projekt.title, "Alpha, Beta")
        self.assertEqual(projekt.software_typen, "Alpha, Beta")
