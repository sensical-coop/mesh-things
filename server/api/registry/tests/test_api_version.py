from django.conf import settings
from django.test import TestCase

import mesh_things


class ApiVersionTests(TestCase):
    def test_every_response_carries_the_package_version(self):
        for path in ("/health", "/no-such-route"):
            response = self.client.get(path)
            self.assertEqual(response["API-Version"], mesh_things.__version__, path)

    def test_the_schema_reports_the_same_version(self):
        self.assertEqual(settings.SPECTACULAR_SETTINGS["VERSION"], mesh_things.__version__)
