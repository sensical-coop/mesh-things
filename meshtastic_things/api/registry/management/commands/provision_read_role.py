"""Create the read-only Postgres role for readings

Runs on every start of the registry role, after migrate, so grants are
re-applied as new tables appear.
"""
import os

import structlog
from django.core.management.base import BaseCommand
from django.db import connection

log = structlog.get_logger()

ROLE = "queryapi_ro"

# Column grants
COLUMN_GRANTS = {
    "meshes": ("id", "owner_id"),
    "devices": ("id", "device_id", "mesh_id", "is_allowed"),
}
# Whole-table grants
TABLE_GRANTS = ("owners", "measurement_types")

CONNECTION_LIMIT = int(os.environ.get("QUERYAPI__DB_MAX_CONNECTIONS", "10"))


class Command(BaseCommand):
    help = "Create or update the read-only role used by the readings tier."

    def handle(self, *args, **options):
        password = os.environ.get("QUERYAPI__DB_PASSWORD", "")
        if not password:
            self.stdout.write("QUERYAPI__DB_PASSWORD not set - skipping read-role provisioning.")
            return

        database = connection.settings_dict["NAME"]
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %(role)s) THEN
                        EXECUTE format('CREATE ROLE %%I LOGIN', %(role)s);
                    END IF;
                END $$;
                """,
                {"role": ROLE},
            )
            # Password and limit are re-applied so a rotated password takes effect.
            cursor.execute(f'ALTER ROLE "{ROLE}" WITH PASSWORD %s CONNECTION LIMIT %s', [password, CONNECTION_LIMIT])
            cursor.execute(f'GRANT CONNECT ON DATABASE "{database}" TO "{ROLE}"')
            cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{ROLE}"')

            # Revoke first so a narrowed grant actually narrows.
            cursor.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{ROLE}"')
            for table, columns in COLUMN_GRANTS.items():
                cursor.execute(f'GRANT SELECT ({", ".join(columns)}) ON "{table}" TO "{ROLE}"')
            for table in TABLE_GRANTS:
                cursor.execute(f'GRANT SELECT ON "{table}" TO "{ROLE}"')

        log.info(
            "read_role_provisioned",
            role=ROLE,
            connection_limit=CONNECTION_LIMIT,
            tables=sorted([*COLUMN_GRANTS, *TABLE_GRANTS]),
        )
        self.stdout.write(f"Provisioned {ROLE} (CONNECTION LIMIT {CONNECTION_LIMIT})")
