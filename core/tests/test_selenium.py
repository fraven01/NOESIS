"""Selenium-basierter Test für den Datei-Upload."""

import os
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile, mkdtemp

import pytest
from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from docx import Document
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from core.models import BVProject, ProjectStatus

pytestmark = pytest.mark.selenium


@unittest.skipUnless(
    os.environ.get("NOESIS_RUN_SELENIUM"), "NOESIS_RUN_SELENIUM nicht gesetzt"
)
class FileUploadDuplicateTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"--user-data-dir={mkdtemp()}")
        try:
            cls.driver = webdriver.Chrome(options=options)
        except Exception:
            raise unittest.SkipTest("Chrome WebDriver not available")
        cls.driver.implicitly_wait(5)
        cls.user = User.objects.create_superuser(
            "selenium", email="s@example.com", password="pass"
        )
        status = ProjectStatus.objects.create(name="Neu", key="neu", is_default=True)
        cls.projekt = BVProject.objects.create(
            software_typen="A", beschreibung="x", status=status
        )

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        super().tearDownClass()

    def _login(self):
        self.driver.get(self.live_server_url + reverse("login"))
        self.driver.find_element(By.ID, "id_username").send_keys(self.user.username)
        pwd = self.driver.find_element(By.ID, "id_password")
        pwd.send_keys("pass")
        pwd.submit()

    def test_duplicate_files_show_warning(self):
        self._login()
        WebDriverWait(self.driver, 10).until(
            EC.text_to_be_present_in_element((By.TAG_NAME, "h1"), "Meine Projekte")
        )
        self.assertEqual(
            self.driver.current_url,
            self.live_server_url + reverse("dashboard"),
        )
        url = self.live_server_url + reverse("projekt_file_upload", args=[self.projekt.pk])
        self.driver.get(url)
        input_el = self.driver.find_element(By.ID, "id_upload")

        doc = Document()
        doc.add_paragraph("x")
        f1 = NamedTemporaryFile(prefix="Anlage_1", suffix=".docx", delete=False)
        doc.save(f1.name)
        f1.close()
        f2 = NamedTemporaryFile(prefix="Anlage_1", suffix=".docx", delete=False)
        doc.save(f2.name)
        f2.close()

        input_el.send_keys(f1.name + "\n" + f2.name)

        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "duplicate-warning"))
        )
        warning = self.driver.find_element(By.ID, "duplicate-warning")
        self.assertTrue(warning.is_displayed())
        submit_btn = self.driver.find_element(By.CSS_SELECTOR, "form button[type=submit]")
        self.assertFalse(submit_btn.is_enabled())

        Path(f1.name).unlink(missing_ok=True)
        Path(f2.name).unlink(missing_ok=True)
