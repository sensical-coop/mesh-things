from django.core.management.base import BaseCommand, CommandError

from registry.emqx_client import get_emqx_client
from registry.models import Source


class Command(BaseCommand):
    help = (
        "Reconcile EMQX with the sources in Postgres: re-apply every source's bridge and remove "
        "bridges in this instance's namespace that no source owns. Run after EMQX is redeployed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Report differences without changing EMQX.")

    def handle(self, *args, check: bool, **options):
        client = get_emqx_client()
        managed = client.managed_source_ids()
        wanted = {str(source.id): source for source in Source.objects.all()}
        missing = sorted(set(wanted) - managed)
        orphaned = sorted(managed - set(wanted))

        for source_id in missing:
            self.stdout.write(f"missing in EMQX: {source_id}")
        for source_id in orphaned:
            self.stdout.write(f"orphaned in EMQX: {source_id}")

        if check:
            if missing or orphaned:
                raise CommandError(f"{len(missing)} missing, {len(orphaned)} orphaned")
            self.stdout.write("EMQX matches the registry")
            return

        # Re-applying every source also repairs ones whose EMQX config drifted.
        for source in wanted.values():
            client.apply_source(source)
        for source_id in orphaned:
            client.delete_source(source_id)
        self.stdout.write(f"Applied {len(wanted)} source(s), removed {len(orphaned)} orphan(s)")
