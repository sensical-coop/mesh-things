"""Shared poll loop for the registry's Kafka consumers."""
import time

import structlog
from django.db import InterfaceError, OperationalError

log = structlog.get_logger()

POLL_TIMEOUT_MS = 1000
MAX_RECORDS = 500
# Breathing room for a database that is restarting, so a rewind doesn't spin.
RETRY_DELAY_SECONDS = 1


def consume_forever(consumer, handle, action: str, tick=None, tick_interval_seconds: float = 10) -> None:
    """Poll until interrupted, passing each record's value to `handle`.

    `tick`, if given, runs every `tick_interval_seconds` whether or not records arrived.
    """
    last_tick = time.monotonic()
    try:
        while True:
            if tick is not None and time.monotonic() - last_tick >= tick_interval_seconds:
                last_tick = time.monotonic()
                run_tick(tick, action)
            messages = consumer.poll(timeout_ms=POLL_TIMEOUT_MS, max_records=MAX_RECORDS)
            if not messages:
                continue
            if consume_batch(consumer, messages, handle, action):
                time.sleep(RETRY_DELAY_SECONDS)
    finally:
        consumer.close()


def run_tick(tick, action: str) -> None:
    """Run a periodic tick, logging failures so they don't stop the consumer."""
    try:
        tick()
    except Exception as e:
        log.warning(f"Periodic task failed while consuming to {action}", error=str(e))


def consume_batch(consumer, messages, handle, action: str) -> bool:
    """Handle one poll batch and advance the offset. True if it rewound.

    Bad data is skipped as it will not parse differently next time.

    IntegrityError is not retried.
    """
    retry_from = {}

    for topic_partition, records in messages.items():
        for record in records:
            if record.value is None:
                continue
            try:
                handle(record.value)
            except (OperationalError, InterfaceError) as e:
                # If we lose database connection, this rewinds to the failing record
                log.warning("Database unavailable, rewound to retry", action=action, error=str(e))
                retry_from[topic_partition] = record.offset
                break
            except Exception as e:
                log.warning(f"Failed to {action}", error=str(e), raw=record.value)

    for topic_partition, offset in retry_from.items():
        consumer.seek(topic_partition, offset)
    # Safe after seek (rewind): the "problematic" partitions commit the offset they will
    # resume from, the clean ones commit their full progress.
    consumer.commit()
    return bool(retry_from)
