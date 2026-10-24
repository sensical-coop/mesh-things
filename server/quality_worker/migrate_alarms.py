"""Move the alarms stored among the readings into the alarm buckets.

Before alarms had their own bucket they were stored with the readings, kept as
long as them. This counts every past day into the daily counts, copies the
last ALARMS_RETENTION_DAYS into the alarms bucket, then deletes them from the
readings. Safe to rerun: counts are replaced and copies overwrite themselves.

  python -m quality_worker.migrate_alarms
"""
import structlog

from common.alarm_counts import ALARM_COUNTS_BUCKET, ALARMS_BUCKET, ALARMS_RETENTION_DAYS, DAY, daily_counts

from .influx_io import get_influx_io
from .tasks import _utcnow

log = structlog.get_logger()


def main() -> None:
    influx = get_influx_io()
    first = influx.first_alarm_time()
    if first is None:
        log.info("No alarms stored among the readings, nothing to move")
        return
    today = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    day = first.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < today:
        alarms = influx.read_alarms(influx.bucket, day, day + DAY)
        # Their repeats were never marked, and absence re-alarmed while a device stayed
        # silent, so the hours with an alarm stand in for the hours silent.
        rows = daily_counts(alarms, day, silences={}, know_repeats=False)
        influx.write_alarm_counts(ALARM_COUNTS_BUCKET, day, rows)
        log.info("Counted alarms", day=day.date().isoformat(), alarms=len(alarms), rows=len(rows))
        day += DAY
    influx.copy_alarms(ALARMS_BUCKET, today - ALARMS_RETENTION_DAYS * DAY)
    influx.delete_alarms()
    log.info("Alarms moved out of the readings bucket")


if __name__ == "__main__":
    main()
