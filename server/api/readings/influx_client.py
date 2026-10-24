import os
from datetime import date, datetime, timedelta, timezone

from influxdb_client import InfluxDBClient

from mesh_things.channels import ALARMS, QUALITY
from mesh_things.detectors import RANGE
from mesh_things.influx_query import bound_to_datetime

from common.alarm_counts import ALARM_COUNTS, ALARM_COUNTS_BUCKET, ALARMS_BUCKET, ALARMS_RETENTION_DAYS
from common.mesh_stats import (
    MESH_GATEWAY_PAIRS,
    MESH_GATEWAY_TRAFFIC,
    MESH_HOPS,
    MESH_NODE_PORTS,
    MESH_NODE_TRAFFIC,
    MESH_RELAYS,
    MESH_SIGNAL,
    MESH_STATS_BUCKET,
    MESH_TRAFFIC,
)

from mesh_things.influx_query import (  # noqa: F401
    ALLOWED_AGG,
    validate_duration as _validate_duration,
    validate_ident as _validate_ident,
    validate_mesh_id as _validate_mesh_id,
    validate_range_bound as _validate_range_bound,
)


# writer/point_builders.py stores these on every point. Ignore them
METADATA_FIELDS = ("packet_id", "timestamp_quality")
_METADATA_FIELDS_FLUX = "[" + ", ".join(f'"{f}"' for f in METADATA_FIELDS) + "]"
# Tags an export leaves out: the mesh is the export's own, node_id has its own column,
# and the rest say how a point arrived rather than what it measured.
_NON_EXPORTED_COLUMNS = {"result", "table", "mesh_id", "node_id", "channel_id", "gateway_id", "postprocessing_id"}


class InfluxQueryClient:
    def __init__(self, url: str, token: str, org: str, bucket: str):
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._query_api = self._client.query_api()
        self.bucket = bucket

    def ping(self) -> bool:
        return self._client.ping()

    def _bucket_for(self, measurement: str) -> str:
        """Alarms live in their own bucket, kept ALARMS_RETENTION_DAYS; everything else with the readings."""
        return ALARMS_BUCKET if measurement == ALARMS else self.bucket

    def timeseries(
        self,
        mesh_id: str,
        node_id: int,
        measurement: str,
        field: str | None,
        start: str,
        stop: str,
        window: str | None,
        agg: str,
    ) -> list[dict]:
        mesh_id = _validate_mesh_id(mesh_id)
        measurement = _validate_ident(measurement, "measurement")
        if field is not None:
            field = _validate_ident(field, "field")
        start = _validate_range_bound(start, "start")
        stop = _validate_range_bound(stop, "stop")
        if agg not in ALLOWED_AGG:
            raise ValueError(f"Invalid agg: {agg!r} (allowed: {sorted(ALLOWED_AGG)})")

        filters = f'r._measurement == "{measurement}" and r.mesh_id == "{mesh_id}" and r.node_id == "{int(node_id)}"'
        if field:
            filters += f' and r._field == "{field}"'

        # Aggregation is only defined over numbers
        imports, agg_stage, numeric_only = "", "", ""
        if window:
            window = _validate_duration(window, "window")
            imports = 'import "types"\n'
            numeric_only = (
                '|> filter(fn: (r) => types.isType(v: r._value, type: "float") '
                'or types.isType(v: r._value, type: "int"))'
            )
            agg_stage = f'|> aggregateWindow(every: {window}, fn: {agg}, createEmpty: false)'

        flux = f'''{imports}
from(bucket: "{self._bucket_for(measurement)}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => {filters})
  {numeric_only}
  {agg_stage}
  |> sort(columns: ["_time"])
'''
        return self._records_to_series(self._query_api.query(flux))

    def latest(self, mesh_id: str, node_id: int, measurement: str, lookback: str = "-30d") -> list[dict]:
        mesh_id = _validate_mesh_id(mesh_id)
        measurement = _validate_ident(measurement, "measurement")
        lookback = _validate_range_bound(lookback, "lookback")

        flux = f'''
from(bucket: "{self._bucket_for(measurement)}")
  |> range(start: {lookback})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.mesh_id == "{mesh_id}" and r.node_id == "{int(node_id)}")
  |> last()
'''
        return self._records_to_series(self._query_api.query(flux))

    def latest_all(self, mesh_id: str, node_id: int, lookback: str = "-30d") -> list[dict]:
        """No-?payload_kind= variant of latest() - combined query across every
        field; grouping by (_measurement, _field) avoids the schema-collision issue.

        last() runs before any other operator so InfluxDB can push it down to
        storage; otherwise every point in the lookback, alarms included, is read.
        """
        mesh_id = _validate_mesh_id(mesh_id)
        lookback = _validate_range_bound(lookback, "lookback")

        readings = []
        for bucket in (self.bucket, ALARMS_BUCKET):
            flux = f'''
from(bucket: "{bucket}")
  |> range(start: {lookback})
  |> filter(fn: (r) => r.mesh_id == "{mesh_id}" and r.node_id == "{int(node_id)}")
  |> last()
  |> filter(fn: (r) => not contains(value: r._field, set: {_METADATA_FIELDS_FLUX}))
  |> group(columns: ["_measurement", "_field"])
  |> sort(columns: ["_time"])
  |> last()
'''
            readings += self._records_to_readings(self._query_api.query(flux))
        return sorted(readings, key=lambda r: (r["measurement"], r["field"]))

    def device_metrics(self, mesh_id: str, node_id: int, start: str, stop: str, now: datetime | None = None) -> dict:
        """Aggregates the `quality` metrics and the alarms the quality tiers already write.

        Alarms are read one by one when the range lies within their retention,
        and from the daily counts, rounded to whole days, when it reaches back further.
        """
        mesh_id = _validate_mesh_id(mesh_id)
        start = _validate_range_bound(start, "start")
        stop = _validate_range_bound(stop, "stop")
        now = now or datetime.now(timezone.utc)
        start_at, stop_at = bound_to_datetime(start, now), bound_to_datetime(stop, now)

        quality_flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "quality" and r.mesh_id == "{mesh_id}" and r.node_id == "{int(node_id)}")
  |> last()
  |> group(columns: ["channel", "_field"])
  |> sort(columns: ["_time"])
  |> last()
'''
        channels = self._records_to_channel_quality(self._query_api.query(quality_flux))

        device = f'r.mesh_id == "{mesh_id}" and r.node_id == "{int(node_id)}"'
        if start_at >= now - timedelta(days=ALARMS_RETENTION_DAYS):
            alarms_flux = f'''
from(bucket: "{ALARMS_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "{ALARMS}" and r._field == "message" and {device})
  |> group(columns: ["detector"])
  |> count()
'''
            # Hours with a range alarm on any channel; range re-raises hourly while it holds.
            range_hours_flux = f'''
from(bucket: "{ALARMS_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "{ALARMS}" and r._field == "message" and r.detector == "{RANGE}" and {device})
  |> group()
  |> aggregateWindow(every: 1h, fn: count, createEmpty: false)
  |> count()
'''
        else:
            alarms_flux = f'''
from(bucket: "{ALARM_COUNTS_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "{ALARM_COUNTS}" and r._field == "alarms" and {device})
  |> group(columns: ["detector"])
  |> sum()
'''
            # Per day, the channel out of range longest stands in for the device.
            range_hours_flux = f'''
from(bucket: "{ALARM_COUNTS_BUCKET}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement == "{ALARM_COUNTS}" and r._field == "hours_active"
       and r.detector == "{RANGE}" and {device})
  |> group(columns: ["_time"])
  |> max()
  |> group()
  |> sum()
'''
        # Hours the device reported at all, so time before it existed or while it was off is not "in range".
        reported_hours_flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: {start}, stop: {stop})
  |> filter(fn: (r) => r._measurement != "quality" and {device})
  |> keep(columns: ["_start", "_stop", "_time"])
  |> map(fn: (r) => ({{r with _value: 1}}))
  |> aggregateWindow(every: 1h, fn: count, createEmpty: false)
  |> count()
'''
        alarms_by_detector = self._records_to_alarm_counts(self._query_api.query(alarms_flux))
        range_hours = self._sum(self._query_api.query(range_hours_flux))
        reported_hours = self._sum(self._query_api.query(reported_hours_flux))

        points_ingested = sum(c["observed"] or 0 for c in channels)
        range_ratio = max(0.0, 1 - range_hours / reported_hours) if reported_hours else None

        return {
            "points_ingested": points_ingested,
            "range_ratio": range_ratio,
            "alarms_by_detector": alarms_by_detector,
            "channels": channels,
        }

    def mesh_stats(self, mesh_id: str, start: str, hourly_start: str, window: str, activity_window: str) -> dict:
        """Traffic and congestion figures for a mesh, from the mesh stats bucket and node reports.

        Args:
            start: Start of the per-minute traffic.
            hourly_start: Start of the hourly figures, rounded down to a whole hour.
            window: Bucket size of the traffic and airtime series.
            activity_window: Bucket size of the active nodes and gateways series.

        Returns:
            {"traffic": {portnum: {"points": [...], **sums}}, "nodes": {node_id: sums},
             "gateways": {gateway_id: sums}, "hops": {hops: sums}, "signal": {(metric, bucket): sums},
             "gateway_pairs": {(a, b): sums}, "relays": {(gateway_id, relay): sums},
             "activity": {"nodes": [points], "gateways": [points]},
             "airtime": {field: {"mean", "peak", "points"}}}, where sums maps each field to its total.
        """
        mesh_id = _validate_mesh_id(mesh_id)
        start = _validate_range_bound(start, "start")
        hourly_start = _validate_range_bound(hourly_start, "hourly_start")
        window = _validate_duration(window, "window")
        activity_window = _validate_duration(activity_window, "activity_window")

        traffic = {
            portnum: {**totals, "points": []}
            for portnum, totals in self._sums(mesh_id, MESH_TRAFFIC, start, "portnum").items()
        }
        series = f'''
from(bucket: "{MESH_STATS_BUCKET}")
  |> range(start: {start})
  |> filter(fn: (r) => r._measurement == "{MESH_TRAFFIC}" and r.mesh_id == "{mesh_id}" and r._field == "receptions")
  |> group(columns: ["portnum"])
  |> aggregateWindow(every: {window}, fn: sum, createEmpty: false)
'''
        for table in self._query_api.query(series):
            for record in table.records:
                traffic.setdefault(record.values.get("portnum"), {"points": []})["points"].append(
                    {"time": record.get_time().isoformat(), "value": int(record.get_value())}
                )

        return {
            "traffic": traffic,
            "nodes": self._sums(mesh_id, MESH_NODE_TRAFFIC, hourly_start, "node_id"),
            "gateways": self._sums(mesh_id, MESH_GATEWAY_TRAFFIC, hourly_start, "gateway_id"),
            "hops": self._sums(mesh_id, MESH_HOPS, hourly_start, "hops"),
            "signal": self._sums(mesh_id, MESH_SIGNAL, hourly_start, "metric", "bucket"),
            "gateway_pairs": self._sums(mesh_id, MESH_GATEWAY_PAIRS, hourly_start, "gateway_a", "gateway_b"),
            "relays": self._sums(mesh_id, MESH_RELAYS, hourly_start, "gateway_id", "relay"),
            "activity": {
                "nodes": self._active(mesh_id, MESH_NODE_TRAFFIC, "packets", "node_id", hourly_start, activity_window),
                "gateways": self._active(
                    mesh_id, MESH_GATEWAY_TRAFFIC, "receptions", "gateway_id", hourly_start, activity_window
                ),
            },
            "airtime": self._airtime(mesh_id, start, window),
        }

    def node_traffic(self, mesh_id: str, node_id: int, hourly_start: str, window: str) -> dict:
        """One node's packets by portnum and over time, from the hourly mesh stats.

        Returns:
            {"ports": {portnum: packets}, "totals": {"packets", "receptions"}, "points": [packets per window]}
        """
        mesh_id = _validate_mesh_id(mesh_id)
        hourly_start = _validate_range_bound(hourly_start, "hourly_start")
        window = _validate_duration(window, "window")
        node = f'r.node_id == "{int(node_id)}"'
        ports = {
            portnum: int(fields.get("packets", 0))
            for portnum, fields in self._sums(mesh_id, MESH_NODE_PORTS, hourly_start, "portnum", where=node).items()
        }
        totals = self._sums(mesh_id, MESH_NODE_TRAFFIC, hourly_start, "node_id", where=node).get(str(int(node_id)), {})
        flux = f'''
from(bucket: "{MESH_STATS_BUCKET}")
  |> range(start: {hourly_start})
  |> filter(fn: (r) => r._measurement == "{MESH_NODE_TRAFFIC}" and r.mesh_id == "{mesh_id}" and {node}
       and r._field == "packets")
  |> aggregateWindow(every: {window}, fn: sum, createEmpty: false, timeSrc: "_start")
'''
        points = [
            {"time": record.get_time().isoformat(), "value": int(record.get_value())}
            for table in self._query_api.query(flux)
            for record in table.records
        ]
        return {"ports": ports, "totals": totals, "points": points}

    def _sums(self, mesh_id: str, measurement: str, since: str, *tags: str, where: str = "true") -> dict:
        """Each field of a mesh stats measurement summed per tag value (or tuple of values)."""
        group = ", ".join(f'"{t}"' for t in (*tags, "_field"))
        flux = f'''
from(bucket: "{MESH_STATS_BUCKET}")
  |> range(start: {since})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.mesh_id == "{mesh_id}" and {where})
  |> group(columns: [{group}])
  |> sum()
'''
        found: dict = {}
        for table in self._query_api.query(flux):
            for record in table.records:
                key = tuple(record.values.get(t) for t in tags)
                found.setdefault(key[0] if len(key) == 1 else key, {})[record.get_field()] = record.get_value()
        return found

    def _active(self, mesh_id: str, measurement: str, field: str, tag: str, since: str, every: str) -> list[dict]:
        """How many distinct `tag` values had a non-zero `field` in each bucket, stamped at its start."""
        flux = f'''
from(bucket: "{MESH_STATS_BUCKET}")
  |> range(start: {since})
  |> filter(fn: (r) => r._measurement == "{measurement}" and r.mesh_id == "{mesh_id}" and r._field == "{field}")
  |> group(columns: ["{tag}"])
  |> aggregateWindow(every: {every}, fn: sum, createEmpty: false, timeSrc: "_start")
  |> filter(fn: (r) => r._value > 0)
  |> group(columns: ["_time"])
  |> count()
  |> group()
  |> sort(columns: ["_time"])
'''
        return [
            {"time": record.get_time().isoformat(), "value": int(record.get_value())}
            for table in self._query_api.query(flux)
            for record in table.records
        ]

    def _airtime(self, mesh_id: str, start: str, window: str) -> dict:
        """The channel utilization and airtime nodes report, across the mesh's nodes."""
        airtime = f'''
from(bucket: "{self.bucket}")
  |> range(start: {start})
  |> filter(fn: (r) => r.mesh_id == "{mesh_id}" and r._measurement == "device_metrics"
       and (r._field == "channel_utilization" or r._field == "air_util_tx"))
  |> group(columns: ["_field"])'''
        fields: dict[str, dict] = {}
        for stage, key in (("mean()", "mean"), ("max()", "peak")):
            for table in self._query_api.query(f"{airtime}\n  |> {stage}"):
                for record in table.records:
                    fields.setdefault(record.get_field(), {"points": []})[key] = record.get_value()
        for table in self._query_api.query(
            f"{airtime}\n  |> aggregateWindow(every: {window}, fn: mean, createEmpty: false)"
        ):
            for record in table.records:
                fields.setdefault(record.get_field(), {"points": []})["points"].append(
                    {"time": record.get_time().isoformat(), "value": record.get_value()}
                )
        return fields

    def day_rows(self, mesh_id: str, day: date, node_ids: list[int] | None = None) -> dict[str, dict]:
        """A mesh's readings for one UTC day, per measurement, as rows of one time and
        node with a column per field and per descriptive tag (a node's name, for example).

        Points sharing a time and node, such as one packet heard by several gateways,
        share a row. `quality` is left out, and alarms live in another bucket.

        Returns:
            {measurement: {"tags": [...], "fields": [...], "rows": [...]}}, rows sorted
            by time then node, each a dict with `time`, `node_id` and its values.
        """
        mesh_id = _validate_mesh_id(mesh_id)
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        stop = start + timedelta(days=1)
        filters = f'r.mesh_id == "{mesh_id}" and r._measurement != "{QUALITY}"'
        if node_ids:
            filters += " and (" + " or ".join(f'r.node_id == "{int(n)}"' for n in node_ids) + ")"

        flux = f'''
from(bucket: "{self.bucket}")
  |> range(start: {start:%Y-%m-%dT%H:%M:%SZ}, stop: {stop:%Y-%m-%dT%H:%M:%SZ})
  |> filter(fn: (r) => {filters})
  |> filter(fn: (r) => not contains(value: r._field, set: {_METADATA_FIELDS_FLUX}))
'''
        found: dict[str, dict] = {}
        for record in self._query_api.query_stream(flux):
            values = record.values
            node_id = values.get("node_id")
            table = found.setdefault(record.get_measurement(), {"tags": set(), "fields": set(), "rows": {}})
            row = table["rows"].setdefault((record.get_time(), node_id), {})
            row[record.get_field()] = record.get_value()
            table["fields"].add(record.get_field())
            for tag, value in values.items():
                if tag.startswith("_") or tag in _NON_EXPORTED_COLUMNS or value is None:
                    continue
                row[tag] = value
                table["tags"].add(tag)

        out = {}
        for measurement, table in found.items():
            rows = []
            for (time, node_id), row in sorted(table["rows"].items(), key=lambda item: (item[0][0], int(item[0][1]))):
                rows.append({"time": time.isoformat().replace("+00:00", "Z"), "node_id": int(node_id), **row})
            out[measurement] = {"tags": sorted(table["tags"]), "fields": sorted(table["fields"]), "rows": rows}
        return out

    @staticmethod
    def _records_to_channel_quality(tables) -> list[dict]:
        by_channel: dict[str, dict] = {}
        for table in tables:
            for record in table.records:
                channel = record.values.get("channel")
                by_channel.setdefault(channel, {})[record.get_field()] = record.get_value()
        return [
            {
                "channel": channel,
                "completeness_ratio": fields.get("completeness_ratio"),
                "observed": fields.get("observed"),
                "expected": fields.get("expected"),
                "largest_gap_seconds": fields.get("largest_gap_seconds"),
            }
            for channel, fields in sorted(by_channel.items())
        ]

    @staticmethod
    def _sum(tables) -> float:
        return sum(record.get_value() or 0 for table in tables for record in table.records)

    @staticmethod
    def _records_to_alarm_counts(tables) -> dict[str, int]:
        counts: dict[str, int] = {}
        for table in tables:
            for record in table.records:
                counts[record.values.get("detector")] = int(record.get_value())
        return counts

    @staticmethod
    def _records_to_series(tables) -> list[dict]:
        series: dict[str, list[dict]] = {}
        for table in tables:
            for record in table.records:
                field = record.get_field()
                series.setdefault(field, []).append(
                    {"time": record.get_time().isoformat(), "value": record.get_value()}
                )
        return [{"field": field, "points": points} for field, points in sorted(series.items())]

    @staticmethod
    def _records_to_readings(tables) -> list[dict]:
        readings = []
        for table in tables:
            for record in table.records:
                readings.append(
                    {
                        "measurement": record.get_measurement(),
                        "field": record.get_field(),
                        "value": record.get_value(),
                        "time": record.get_time().isoformat(),
                    }
                )
        return sorted(readings, key=lambda r: (r["measurement"], r["field"]))


_client: InfluxQueryClient | None = None


def get_client() -> InfluxQueryClient:
    """Lazily-instantiated per-process singleton - each gunicorn worker gets its
    own InfluxDBClient on first use."""
    global _client
    if _client is None:
        _client = InfluxQueryClient(
            url=os.environ["INFLUX__URL"],
            token=os.environ["INFLUX__TOKEN"],
            org=os.environ["INFLUX__ORG"],
            bucket=os.environ["INFLUX__BUCKET"],
        )
    return _client
