"""InfluxDB reads for the batch tier, and the quality metrics it writes."""
import os
from datetime import datetime, timezone

import structlog
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from common.channels import QUALITY
from common.influx_query import split_channel, validate_mesh_id, validate_range_bound

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
