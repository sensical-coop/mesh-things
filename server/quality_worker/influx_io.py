"""InfluxDB reads for the batch tier, and the quality metrics it writes."""
import os
from datetime import datetime, timezone

import structlog
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from mesh_things.channels import ALARMS, QUALITY
from mesh_things.influx_query import split_channel, validate_ident, validate_mesh_id, validate_range_bound

from common.alarm_counts import ALARM_COUNTS

log = structlog.get_logger()

class InfluxIO:
    def __init__(self, url: str, token: str, org: str, bucket: str):
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._query_api = self._client.query_api()
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self.bucket = bucket

    def ping(self) -> bool:
        return self._client.ping()

    def read_channel(self, mesh_id: str, device_id: int, channel: str, lookback: str) -> list[tuple[datetime, float]]:
        """One channel ("<measurement>.<field>") over a window.
        """
        mesh_id = validate_mesh_id(mesh_id)
        lookback = validate_range_bound(lookback, "lookback")
        measurement, field = split_channel(channel)

        flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: {lookback})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}"
       and r.mesh_id == "{mesh_id}" and r.node_id == "{int(device_id)}")
  |> sort(columns: ["_time"])
'''
        series = []
        for table in self._query_api.query(flux):
            for record in table.records:
                value = record.get_value()
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    series.append((record.get_time(), float(value)))
        return series

    def read_range(
        self, mesh_id: str, device_id: int, channel: str, start: str, stop: str
    ) -> list[tuple[datetime, float]]:
        """One channel between two RFC 3339 instants, as one time-ordered series.

        A reading heard through several gateways is stored in several series;
        they are merged and each timestamp kept once.
        """
        mesh_id = validate_mesh_id(mesh_id)
        start = validate_range_bound(start, "start")
        stop = validate_range_bound(stop, "stop")
        measurement, field = split_channel(channel)

        flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r._field == "{field}"
       and r.mesh_id == "{mesh_id}" and r.node_id == "{int(device_id)}")
  |> group()
  |> sort(columns: ["_time"])
'''
        by_time = {}
        for table in self._query_api.query(flux):
            for record in table.records:
                value = record.get_value()
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    by_time[record.get_time()] = float(value)
        return sorted(by_time.items())

    def write_quality_metric(self, mesh_id: str, device_id: int, channel: str, fields: dict) -> None:
        """Completeness/ratio metrics as their own timeseries."""
        mesh_id = validate_mesh_id(mesh_id)
        point = (
            Point(QUALITY)
            .tag("mesh_id", mesh_id)
            .tag("node_id", str(int(device_id)))
            .tag("channel", channel)
            .time(datetime.now(timezone.utc), WritePrecision.NS)
        )
        for name, value in fields.items():
            if value is not None:
                point = point.field(name, float(value))
        self._write_api.write(bucket=self.bucket, record=point)

    def read_alarms(self, bucket: str, start: datetime, stop: datetime, detector: str | None = None) -> list[dict]:
        """Alarms stored in `bucket` between two instants, oldest first."""
        detector_filter = f' and r.detector == "{validate_ident(detector, "detector")}"' if detector else ""
        flux = f'''
from(bucket: "{bucket}")
  |> range(start: {_rfc3339(start)}, stop: {_rfc3339(stop)})
  |> filter(fn: (r) => r._measurement == "{ALARMS}" and r._field == "message"{detector_filter})
  |> group()
  |> sort(columns: ["_time"])
'''
        return [
            {
                "time": record.get_time(),
                "mesh_id": record.values.get("mesh_id"),
                "node_id": record.values.get("node_id"),
                "channel": record.values.get("channel"),
                "detector": record.values.get("detector"),
                "repeat": record.values.get("repeat") == "true",
            }
            for table in self._query_api.query(flux)
            for record in table.records
        ]

    def first_reading_after(self, mesh_id: str, node_id: str, start: datetime, stop: datetime) -> datetime | None:
        """Return the next time a device reported anything between two instants, if it did."""
        mesh_id = validate_mesh_id(mesh_id)
        flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: {_rfc3339(start)}, stop: {_rfc3339(stop)})
  |> filter(fn: (r) => r.mesh_id == "{mesh_id}" and r.node_id == "{int(node_id)}"
       and r._measurement != "{QUALITY}" and r._measurement != "{ALARMS}")
  |> keep(columns: ["_time"])
  |> group()
  |> sort(columns: ["_time"])
  |> limit(n: 1)
'''
        for table in self._query_api.query(flux):
            for record in table.records:
                return record.get_time()
        return None

    def write_alarm_counts(self, bucket: str, day_start: datetime, rows: list[dict]) -> None:
        """One point per row, at midnight of its day. Rewriting a day replaces it."""
        points = []
        for row in rows:
            point = (
                Point(ALARM_COUNTS)
                .tag("mesh_id", row["mesh_id"])
                .tag("node_id", str(row["node_id"]))
                .tag("detector", row["detector"])
                .time(day_start, WritePrecision.S)
            )
            if row.get("channel"):
                point = point.tag("channel", row["channel"])
            for field in ("alarms", "new_conditions", "hours_active"):
                if row.get(field) is not None:
                    point = point.field(field, float(row[field]))
            points.append(point)
        if points:
            self._write_api.write(bucket=bucket, record=points)

    def first_alarm_time(self) -> datetime | None:
        """The oldest alarm still stored among the readings, from before alarms had their own bucket."""
        flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: 0)
  |> filter(fn: (r) => r._measurement == "{ALARMS}" and r._field == "message")
  |> group()
  |> min(column: "_time")
'''
        for table in self._query_api.query(flux):
            for record in table.records:
                return record.get_time()
        return None

    def copy_alarms(self, bucket: str, start: datetime) -> None:
        """Copy the alarms stored among the readings since `start` into `bucket`, inside InfluxDB."""
        flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: {_rfc3339(start)})
  |> filter(fn: (r) => r._measurement == "{ALARMS}")
  |> to(bucket: "{bucket}")
'''
        self._query_api.query(flux)

    def delete_alarms(self) -> None:
        """Remove every alarm stored among the readings."""
        self._client.delete_api().delete(
            start=datetime(1970, 1, 1, tzinfo=timezone.utc),
            stop=datetime.now(timezone.utc),
            predicate=f'_measurement="{ALARMS}"',
            bucket=self.bucket,
        )


def _rfc3339(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_io: InfluxIO | None = None


def get_influx_io() -> InfluxIO:
    global _io
    if _io is None:
        _io = InfluxIO(
            url=os.environ["INFLUX__URL"],
            token=os.environ["INFLUX__TOKEN"],
            org=os.environ["INFLUX__ORG"],
            bucket=os.environ["INFLUX__BUCKET"],
        )
    return _io
