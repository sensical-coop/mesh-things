from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator


class OwnerOnlyFieldsSchemaTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        schema = SchemaGenerator(urlconf="api_project.urls_all").get_schema(request=None, public=True)
        cls.schemas = schema["components"]["schemas"]
        cls.create_mesh = schema["paths"]["/meshes"]["post"]["requestBody"]["content"]["application/json"]["schema"]

    def test_mesh_response_does_not_require_what_other_viewers_never_receive(self):
        required = set(self.schemas["Mesh"]["required"])
        self.assertTrue(required.isdisjoint({"psk_b64", "terms_accepted_version", "terms_expires_at", "paused_at"}))
        self.assertTrue({"id", "channel_id", "owner_id"} <= required)

    def test_creating_a_mesh_still_requires_its_key(self):
        self.assertEqual(self.create_mesh, {"$ref": "#/components/schemas/MeshCreate"})
        self.assertIn("psk_b64", self.schemas["MeshCreate"]["required"])

    def test_device_response_does_not_require_the_owner_only_fields(self):
        required = set(self.schemas["DeviceRead"]["required"])
        self.assertTrue(required.isdisjoint({"admin_keys_b64", "archive_enabled", "archive_enabled_at", "archive_enabled_by"}))
        self.assertTrue({"uuid", "node_id", "mesh_id", "is_gateway"} <= required)
