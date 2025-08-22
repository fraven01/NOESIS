from django.contrib.auth.models import User
from django.test import TransactionTestCase


class NoesisTestCase(TransactionTestCase):
    """Basisklasse für Tests mit vorkonfigurierten Benutzern."""

    @classmethod
    def setUpClass(cls) -> None:  # pragma: no cover - setup code
        super().setUpClass()
        cls.setUpTestData()

    @classmethod
    def setUpTestData(cls) -> None:  # pragma: no cover - setup code
        cls.user = User.objects.get(username="baseuser")
        cls.superuser = User.objects.get(username="basesuper")
