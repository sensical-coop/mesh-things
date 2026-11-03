"""Every email has an HTML part next to its plain text."""
from pathlib import Path

from django.test import SimpleTestCase

TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "registry" / "emails"


class EmailTemplateTests(SimpleTestCase):
    def test_every_plain_text_email_has_an_html_version(self):
        missing = [p.stem for p in TEMPLATES.glob("*.txt") if not p.with_suffix(".html").exists()]

        self.assertEqual(missing, [])

    def test_plain_text_is_not_html_escaped(self):
        escaped = [p.stem for p in TEMPLATES.glob("*.txt") if "{% autoescape off %}" not in p.read_text()]

        self.assertEqual(escaped, [])
