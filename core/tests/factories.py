import os
import django
import factory

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "noesis.settings")
django.setup()

from django.contrib.auth.models import User, Group
from pytest_factoryboy import register
from core.models import Area, Tile, ProjectStatus, BVProject, BVProjectFile


@register
class UserFactory(factory.django.DjangoModelFactory):
    """Factory für Benutzer."""

    class Meta:
        model = User
        # Deaktiviert automatisches Speichern nach post_generation (factory_boy Deprecation)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    # Passwort explizit setzen und speichern, damit Auth-Tests funktionieren
    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        value = extracted or "pw"
        self.set_password(value)
        if create:
            self.save()


@register
class GroupFactory(factory.django.DjangoModelFactory):
    """Factory für Gruppen."""

    class Meta:
        model = Group

    name = factory.Sequence(lambda n: f"group{n}")


@register
class AreaFactory(factory.django.DjangoModelFactory):
    """Factory für Bereiche."""

    class Meta:
        model = Area

    slug = factory.Sequence(lambda n: f"area-{n}")
    name = factory.Faker("word")


@register
class TileFactory(factory.django.DjangoModelFactory):
    """Factory für Tiles."""

    class Meta:
        model = Tile
        # Deaktiviert automatisches Speichern nach post_generation (factory_boy Deprecation)
        skip_postgeneration_save = True

    slug = factory.Sequence(lambda n: f"tile-{n}")
    name = factory.Faker("word")
    url_name = "home"

    @factory.post_generation
    def areas(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted:
            for area in extracted:
                self.areas.add(area)


@register
class ProjectStatusFactory(factory.django.DjangoModelFactory):
    """Factory für Projektstatus."""

    class Meta:
        model = ProjectStatus

    name = factory.Sequence(lambda n: f"Status {n}")
    key = factory.Sequence(lambda n: f"status_{n}")
    ordering = factory.Sequence(lambda n: n)


@register
class BVProjectFactory(factory.django.DjangoModelFactory):
    """Factory für BVProject."""

    class Meta:
        model = BVProject

    title = factory.Sequence(lambda n: f"Projekt {n}")
    beschreibung = ""
    status = factory.SubFactory(ProjectStatusFactory)


@register
class BVProjectFileFactory(factory.django.DjangoModelFactory):
    """Factory für BVProjectFile."""

    class Meta:
        model = BVProjectFile

    project = factory.SubFactory(BVProjectFactory)
    anlage_nr = 1
    upload = factory.django.FileField(filename="test.txt", data=b"data")
    text_content = "Text"
    analysis_json = {}
