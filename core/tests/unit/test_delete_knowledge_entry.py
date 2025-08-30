"""Tests für das Löschen eines ``SoftwareKnowledge``-Eintrags."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from ...models import BVProject, SoftwareKnowledge, ProjectStatus

pytestmark = pytest.mark.unit


@pytest.fixture
def project(db):
    status = ProjectStatus.objects.create(
        name="Offen", key="offen", ordering=0, is_default=True
    )
    return BVProject.objects.create(title="P1", status=status)


@pytest.fixture
def knowledge(project):
    return SoftwareKnowledge.objects.create(project=project, software_name="Tool")


@pytest.mark.django_db
def test_delete_entry_removes_object(client, project, knowledge):
    """Berechtigter Benutzer kann einen Knowledge-Eintrag löschen."""

    get_user_model().objects.create_user(
        username="user", password="pass", is_staff=True
    )
    client.login(username="user", password="pass")
    url = reverse("delete_knowledge_entry", args=[knowledge.pk])
    response = client.post(url)
    assertRedirects(response, reverse("projekt_detail", args=[project.pk]))
    assert not SoftwareKnowledge.objects.filter(pk=knowledge.pk).exists()


@pytest.mark.django_db
def test_delete_entry_requires_permission(client, project, knowledge):
    """Unberechtigter Benutzer erhält einen 403-Status."""

    get_user_model().objects.create_user(
        username="user", password="pass", is_staff=True
    )
    other = get_user_model().objects.create_user(
        username="other", password="pass"
    )
    client.login(username="other", password="pass")
    url = reverse("delete_knowledge_entry", args=[knowledge.pk])
    response = client.post(url)
    assert response.status_code == 403
    assert SoftwareKnowledge.objects.filter(pk=knowledge.pk).exists()

