from django.test import SimpleTestCase

from registry.auth import generate_api_key, hash_api_key


class AuthTests(SimpleTestCase):
    def test_generate_api_key_is_high_entropy_and_unique(self):
        keys = {generate_api_key() for _ in range(100)}
        self.assertEqual(len(keys), 100)
        self.assertTrue(all(len(k) > 20 for k in keys))

    def test_hash_api_key_is_deterministic_and_not_reversible_looking(self):
        key = "some-test-key"
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, key)
        self.assertEqual(len(h1), 64)  # sha256 hex digest

    def test_hash_api_key_differs_for_different_keys(self):
        self.assertNotEqual(hash_api_key("key-a"), hash_api_key("key-b"))
