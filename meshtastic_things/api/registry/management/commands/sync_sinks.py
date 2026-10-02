from django.core.management.base import BaseCommand, CommandError

from registry.emqx_client import get_emqx_client
from registry.models import Sink


class Command(BaseCommand):
    help = (
        "Reconcile EMQX with the sinks in Postgres: re-apply every sink's rules and the namespace's "
        "rules, and remove sink users and rules in this instance's namespace that no sink owns. A "
        "sink whose user is gone needs its credentials rotated. Run after EMQX is redeployed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Report differences without changing EMQX.")
        parser.add_argument(
            "--install-authz",
            action="store_true",
            help=(
                "Create EMQX's built-in authorization database if missing and move it before every other "
                "authorization source. Changes the whole broker, so run it once, on purpose."
            ),
        )

    def handle(self, *args, check: bool, install_authz: bool, **options):
        client = get_emqx_client()
        if install_authz and not check:
            client.install_sink_authorization()
            self.stdout.write("Installed the built-in authorization database first")

        problem = client.sink_authorization_problem()
        if problem:
            self.stdout.write(f"authorization: {problem}")
        users, rules = client.managed_sink_ids()
        wanted = {str(sink.id): sink for sink in Sink.objects.all()}
        missing = sorted(set(wanted) - users)
        orphaned = sorted((users | rules) - set(wanted))
        for sink_id in missing:
            self.stdout.write(f"no user in EMQX: {sink_id}")
        for sink_id in orphaned:
            self.stdout.write(f"orphaned in EMQX: {sink_id}")

        if check:
            if problem or missing or orphaned:
                raise CommandError(f"{len(missing)} missing, {len(orphaned)} orphaned, authorization {problem or 'ok'}")
            self.stdout.write("EMQX matches the registry")
            return
        if problem:
            raise CommandError(f"Refusing to apply sinks: {problem}. Run with --install-authz first.")

        client.apply_sink_namespace()
        # Rules only: a password lives in EMQX alone, so a lost user needs its credentials rotated.
        for sink_id, sink in wanted.items():
            if sink.paused_at is not None:
                client.pause_sink(sink_id)
            else:
                client.apply_sink(sink_id)
        for sink_id in orphaned:
            client.delete_sink(sink_id)
        self.stdout.write(f"Applied {len(wanted)} sink(s), removed {len(orphaned)} orphan(s)")
        if missing:
            self.stdout.write(f"Rotate the credentials of: {', '.join(missing)}")
