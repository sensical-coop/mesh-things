"""The grants that keep the readings role away from the mesh keys."""
import os
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from registry.management.commands.provision_read_role import (
    COLUMN_GRANTS,
    CONNECTION_LIMIT,
    TABLE_GRANTS,
)

# Reading either of these would let a compromised readings container decrypt
# mesh traffic, which is the whole point of the split.
KEY_MATERIAL = {"psk_b64", "admin_keys_b64"}


class GrantsTests(SimpleTestCase):
    def test_no_grant_ever_includes_key_material(self):
        granted = {column for columns in COLUMN_GRANTS.values() for column in columns}

        assert not granted & KEY_MATERIAL, f"key material granted: {granted & KEY_MATERIAL}"

    def test_the_tables_holding_key_material_are_column_restricted(self):
        """`meshes` and `devices` may only ever be granted per column - a whole-table grant on
        either hands over psk_b64/admin_keys_b64."""
        for table in ("meshes", "devices"):
            assert table in COLUMN_GRANTS, f"{table} must use column grants"
            assert table not in TABLE_GRANTS, f"{table} is granted whole, exposing key material"

    def test_owners_is_granted_whole_on_purpose(self):
        """Django selects every field of a model, so a column grant here refuses the
        authentication query itself."""
        assert "owners" in TABLE_GRANTS
        assert "owners" not in COLUMN_GRANTS

    def test_the_scoping_join_has_the_columns_it_needs(self):
        """Owner.visible_meshes reads owner_id and is_public, and Owner._device_addresses
        reads three columns."""
        assert set(COLUMN_GRANTS["meshes"]) >= {"id", "owner_id", "is_public"}
        assert set(COLUMN_GRANTS["devices"]) >= {"id", "mesh_id", "device_id"}

    def test_the_connection_limit_is_set(self):
        """The cap is what stops read load exhausting the connections the registry needs;
        unlimited would make the isolation advisory."""
        assert 0 < CONNECTION_LIMIT <= 100


class ProvisioningTests(SimpleTestCase):
    def test_it_does_nothing_without_a_password(self):
        """A deployment that has not set one must not end up with a password-less login role."""
        out = StringIO()
        with mock.patch.dict(os.environ, {"READINGS__DB_PASSWORD": ""}):
            call_command("provision_read_role", stdout=out)

        assert "skipping" in out.getvalue().lower()
