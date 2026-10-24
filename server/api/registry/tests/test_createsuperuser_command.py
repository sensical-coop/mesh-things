from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from registry.models import Owner


class CreateSuperuserCommandTests(TestCase):
    def _run(self, **options) -> str:
        out = StringIO()
        call_command("createsuperuser", stdout=out, **options)
        return out.getvalue()

    def test_creates_new_owner_as_superuser_with_api_key(self):
        output = self._run(email="new@example.com", name="New Owner")

        owner = Owner.objects.get(email="new@example.com")
        self.assertTrue(owner.is_superuser)
        self.assertTrue(owner.is_staff)
        self.assertIsNotNone(owner.api_key_hash)
        self.assertIn("Save this API key", output)
        self.assertIn("Admin-panel login password", output)

    def test_without_name_for_unknown_owner_raises(self):
        with self.assertRaises(CommandError):
            call_command("createsuperuser", email="nobody@example.com", stdout=StringIO())

    def test_promotes_existing_owner_and_mints_a_key(self):
        existing = Owner.objects.create_user(email="x@example.com", name="X")
        self.assertFalse(existing.is_superuser)
        self.assertIsNone(existing.api_key_hash)

        output = self._run(email="x@example.com")

        existing.refresh_from_db()
        self.assertTrue(existing.is_superuser)
        self.assertIsNotNone(existing.api_key_hash)
        self.assertIn("Granted superuser", output)
        self.assertIn("Save this API key", output)

    def test_is_idempotent_and_does_not_mint_a_second_key(self):
        self._run(email="y@example.com", name="Y")
        owner = Owner.objects.get(email="y@example.com")
        first_hash = owner.api_key_hash

        output = self._run(email="y@example.com")

        owner.refresh_from_db()
        self.assertEqual(owner.api_key_hash, first_hash)
        self.assertIn("already a superuser", output)
        self.assertNotIn("Save this API key", output)

    def test_does_not_reset_password_on_rerun_without_explicit_flag(self):
        self._run(email="z@example.com", name="Z")
        owner = Owner.objects.get(email="z@example.com")
        first_password_hash = owner.password

        self._run(email="z@example.com")

        owner.refresh_from_db()
        self.assertEqual(owner.password, first_password_hash)
