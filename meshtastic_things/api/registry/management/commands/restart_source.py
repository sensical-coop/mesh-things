from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from registry.data_lifecycle import restart_source
from registry.emqx_client import get_emqx_client
from registry.models import Source


class Command(BaseCommand):
    help = (
        "Restart a source's bridge on EMQX: re-apply it and make it subscribe to the remote topic "
        "again. Use it on a source that reports connected but receives nothing. Without an id, "
        "lists the sources with their status and message count."
    )

    def add_arguments(self, parser):
        parser.add_argument("source_id", nargs="?", help="Id of the source to restart.")

    def handle(self, *args, source_id: str | None, **options):
        client = get_emqx_client()
        if source_id is None:
            for source in Source.objects.order_by("created_at"):
                status = "paused" if source.paused_at else client.source_status(str(source.id))
                count = client.source_message_count(str(source.id))
                self.stdout.write(f"{source.id}  {status:<12}  messages={count}  {source}")
            return
        try:
            source = Source.objects.get(pk=source_id)
        except (Source.DoesNotExist, ValidationError):
            raise CommandError(f"No source {source_id}")
        if source.paused_at is not None:
            raise CommandError("Source is paused; renew its terms to restart it")
        restart_source(source)
        self.stdout.write(f"Restarted {source}: {client.source_status(str(source.id))}")
