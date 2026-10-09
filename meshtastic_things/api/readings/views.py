from datetime import datetime, timedelta, timezone

from django.core.cache import cache
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from meshtastic.protobuf import portnums_pb2
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.channels import (
    channel_name,
    measurement_of,
    origin_of_measurement,
    payload_kind_of_measurement,
    split_channel,
)
from common.influx_query import duration_seconds
from common.mesh_stats import UNKNOWN
from registry.models import Device, visible_meshes_for
from .influx_client import get_client
from .measurement_catalog import get_measurement_types
from .serializers import (
    DeviceQualityResponseSerializer,
    LatestReadingsResponseSerializer,
    MeshStatsResponseSerializer,
    ReadingsResponseSerializer,
)

_TIME_FORMS = (
    "a relative duration such as `-24h`, a date such as `2026-09-01`, or a "
    "timestamp such as `2026-09-01T13:45:00Z`"
)


def _query(name, description, **kwargs):
    return OpenApiParameter(name, OpenApiTypes.STR, OpenApiParameter.QUERY, description=description, **kwargs)


RANGE_PARAMS = [
    _query("start", f"Start of the range, as {_TIME_FORMS}.", default="-1h"),
    _query("stop", "End of the range, in the same forms as `start`, or `now()`.", default="now()"),
]

READINGS_PARAMS = RANGE_PARAMS + [
    _query(
        "payload_kind",
        "Family to read, for example `telemetry:environment_metrics`. Returns "
        "every channel in it. Required unless `channel` is given.",
    ),
    _query(
        "channel",
        "A single channel, for example `environment_metrics.temperature`. "
        "Takes precedence over `payload_kind`.",
    ),
    _query("window", "Bucket size to downsample into, for example `6h`. Off by default."),
    _query(
        "agg",
        "Aggregate applied to each bucket. Applies only when `window` is set.",
        enum=["mean", "max", "min", "last", "first", "sum", "count"],
        default="mean",
    ),
]

LATEST_PARAMS = [
    _query(
        "payload_kind",
        "Restrict to one family, for example `telemetry:environment_metrics`. "
        "Defaults to every one.",
    ),
    _query("lookback", f"How far back to search for a value, as {_TIME_FORMS}.", default="-30d"),
]

# latest_all returns a different body from the single-family case, so the schema
# advertises both rather than picking one.
LATEST_RESPONSE = OpenApiResponse(
    response=LatestReadingsResponseSerializer,
    description=(
        "With `payload_kind`, the `payload_kind`/`series` body the timeseries "
        "route returns. Without it, a flat `readings` list covering every channel."
    ),
)


class ReadingsAPIView(APIView):
    """Base for the reading endpoints."""

    permission_classes = [IsAuthenticated]


def _as_channels(measurement: str, series: list[dict]) -> list[dict]:
    """Storage speaks measurement/field; the API speaks channel."""
    return [{"channel": f"{measurement}.{s['field']}", "points": s["points"]} for s in series]


def _require_visible_mesh(request, mesh_id) -> None:
    """Reject a mesh the caller may not read, without revealing whether it exists.

    Readable means their own or public, and only public without credentials.
    """
    if request.user.is_superuser:
        return
    if not visible_meshes_for(request.user).filter(pk=mesh_id).exists():
        raise NotFound("Device not found")


def _resolve_device_uuid(request, device_uuid) -> tuple[str, int]:
    if request.user.is_authenticated:
        resolved = request.user.devices_by_uuid.get(str(device_uuid))
    else:
        resolved = (
            Device.objects.filter(pk=device_uuid, is_allowed=True, mesh__is_public=True)
            .values_list("mesh_id", "device_id")
            .first()
        )
        if resolved is not None:
            resolved = (str(resolved[0]), resolved[1])
    if resolved is None:
        raise NotFound("Device not found")
    return resolved


class HealthView(APIView):
    """Report whether the service and the timeseries database are reachable."""

    # Infra probe, not sensitive data.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        responses={
            200: OpenApiResponse(description="Both the service and InfluxDB are reachable."),
            503: OpenApiResponse(description="InfluxDB is unreachable."),
        }
    )
    def get(self, request):
        try:
            if not get_client().ping():
                raise RuntimeError("InfluxDB ping returned false")
        except Exception as e:
            return Response({"detail": f"InfluxDB unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"status": "ok"})


class ReadingsView(ReadingsAPIView):
    """Return a device's readings for one measurement over a time range.

    Downsampling covers numeric fields only, so text fields such as
    `timestamp_quality` are left out whenever `window` is set.

    Args:
        payload_kind: Family to read, for example `telemetry:environment_metrics`.
            Returns every channel in it. Required unless `channel` is given.
        channel: A single channel, for example `environment_metrics.temperature`.
            Takes precedence over `payload_kind`.
        start: Start of the range, as a relative duration such as `-24h`, a date
            such as `2026-09-01`, or a timestamp such as `2026-09-01T13:45:00Z`.
            Defaults to `-1h`.
        stop: End of the range, in the same forms as `start`, or `now()`.
            Defaults to `now()`.
        window: Bucket size to downsample into, for example `6h`. Off by default.
        agg: Aggregate applied to each bucket, one of `mean`, `max`, `min`,
            `last`, `first`, `sum` or `count`. Defaults to `mean` and applies
            only when `window` is set.
    """

    @extend_schema(parameters=READINGS_PARAMS, responses=ReadingsResponseSerializer)
    def get(self, request, mesh_id, node_id):
        _require_visible_mesh(request, mesh_id)
        params = request.query_params
        payload_kind, channel = params.get("payload_kind"), params.get("channel")
        if not payload_kind and not channel:
            raise ValidationError("payload_kind or channel is required")
        try:
            if channel:
                measurement, field = split_channel(channel)
            else:
                measurement, field = measurement_of(payload_kind), None
            series = get_client().timeseries(
                mesh_id,
                node_id,
                measurement,
                field,
                params.get("start", "-1h"),
                params.get("stop", "now()"),
                params.get("window"),
                params.get("agg", "mean"),
            )
        except ValueError as e:
            raise ValidationError(str(e))
        body = {
            "mesh_id": mesh_id,
            "node_id": node_id,
            "payload_kind": payload_kind or payload_kind_of_measurement(measurement),
            "series": _as_channels(measurement, series),
        }
        return Response(ReadingsResponseSerializer(body).data)


class LatestView(ReadingsAPIView):
    """Return a device's most recent readings.

    Without `payload_kind`, every channel the device has reported comes back in
    one call, each annotated with its unit from the measurement catalog. A
    device on a public mesh is readable without credentials.

    Args:
        payload_kind: Restrict to one family, for example
            `telemetry:environment_metrics`. Defaults to every one.
        lookback: How far back to search for a value, as a relative duration, a
            date or a timestamp. Defaults to `-30d`.
    """

    permission_classes = [AllowAny]

    @extend_schema(parameters=LATEST_PARAMS, responses={200: LATEST_RESPONSE})
    def get(self, request, mesh_id, node_id):
        _require_visible_mesh(request, mesh_id)
        params = request.query_params
        payload_kind = params.get("payload_kind")
        lookback = params.get("lookback", "-30d")
        try:
            if payload_kind:
                measurement = measurement_of(payload_kind)
                series = get_client().latest(mesh_id, node_id, measurement, lookback=lookback)
                body = {
                    "mesh_id": mesh_id,
                    "node_id": node_id,
                    "payload_kind": payload_kind,
                    "series": _as_channels(measurement, series),
                }
                return Response(ReadingsResponseSerializer(body).data)
            readings = get_client().latest_all(mesh_id, node_id, lookback=lookback)
        except ValueError as e:
            raise ValidationError(str(e))

        catalog = get_measurement_types()
        decorated = []
        for reading in readings:
            channel = channel_name(reading["measurement"], reading["field"])
            meta = catalog.get(channel, {})
            decorated.append(
                {
                    # The catalog is authoritative; a channel with no row yet
                    # still gets the namespace storage dropped.
                    "payload_kind": meta.get("payload_kind")
                    or payload_kind_of_measurement(reading["measurement"]),
                    "field_name": meta.get("field_name") or reading["field"],
                    "channel": channel,
                    "value": reading["value"],
                    "time": reading["time"],
                    "unit": meta.get("unit"),
                    "quantity_kind": meta.get("quantity_kind"),
                    "vocabulary_uri": meta.get("vocabulary_uri"),
                    "origin": origin_of_measurement(reading["measurement"]),
                }
            )
        body = {"mesh_id": mesh_id, "node_id": node_id, "readings": decorated}
        return Response(LatestReadingsResponseSerializer(body).data)


class QualityView(ReadingsAPIView):
    """Return data-quality figures for a device over a time range.

    Covers the number of readings recorded, alarms raised per detector, the
    share of the hours the device reported in that stayed within its
    configured ranges, and how complete each channel was. Figures stay empty
    until the quality checks have run for the device.

    Alarms are kept one by one for 30 days. A range reaching further back is
    answered from daily counts, so it is rounded to whole days and does not
    include the current day.

    Args:
        start: Start of the range, as a relative duration such as `-24h`, a date
            such as `2026-09-01`, or a timestamp such as `2026-09-01T13:45:00Z`.
            Defaults to `-1h`.
        stop: End of the range, in the same forms as `start`, or `now()`.
            Defaults to `now()`.
    """

    @extend_schema(parameters=RANGE_PARAMS, responses=DeviceQualityResponseSerializer)
    def get(self, request, mesh_id, node_id):
        _require_visible_mesh(request, mesh_id)
        params = request.query_params
        start = params.get("start", "-1h")
        stop = params.get("stop", "now()")
        try:
            metrics = get_client().device_metrics(mesh_id, node_id, start, stop)
        except ValueError as e:
            raise ValidationError(str(e))
        body = {"mesh_id": mesh_id, "node_id": node_id, "start": start, "stop": stop, **metrics}
        return Response(DeviceQualityResponseSerializer(body).data)


# Range -> bucket size, so every range yields at most a few hundred points per series.
MESH_STATS_RANGES = {"1h": "1m", "24h": "15m", "7d": "1h", "30d": "6h"}
MESH_STATS_TOP_NODES = 20
MESH_STATS_CACHE_SECONDS = 60


def _registrations(mesh_id, node_ids) -> dict[int, str]:
    """Registration ID of each of the nodes registered on the mesh."""
    rows = Device.objects.filter(
        mesh_id=mesh_id, device_id__in=[n for n in node_ids if n is not None], is_allowed=True
    ).values_list("device_id", "id")
    return {node: str(pk) for node, pk in rows}


def _portnum_name(portnum: int | None) -> str:
    if portnum is None:
        return "ENCRYPTED"
    try:
        return portnums_pb2.PortNum.Name(portnum)
    except ValueError:
        return f"PORTNUM_{portnum}"


def _int_or_none(value: str) -> int | None:
    return None if value == UNKNOWN else int(value)


def _mesh_stats(mesh_id, range_, now: datetime) -> dict:
    window = MESH_STATS_RANGES[range_]
    since = now - timedelta(seconds=duration_seconds(f"-{range_}"))
    hourly_start = since.replace(minute=0, second=0, microsecond=0)
    raw = get_client().mesh_stats(
        mesh_id, f"-{range_}", hourly_start.strftime("%Y-%m-%dT%H:%M:%SZ"), window
    )

    traffic = sorted(
        (
            {
                "portnum": _int_or_none(portnum),
                "name": _portnum_name(_int_or_none(portnum)),
                "packets": int(row.get("packets", 0)),
                "receptions": int(row.get("receptions", 0)),
                "points": row["points"],
            }
            for portnum, row in raw["traffic"].items()
        ),
        key=lambda t: -t["receptions"],
    )
    totals = {
        field: int(sum(row.get(field, 0) for row in raw["traffic"].values()))
        for field in ("packets", "receptions", "bytes", "rejected_packets")
    }
    totals["decoded_packets"] = totals["packets"] - int(raw["traffic"].get(UNKNOWN, {}).get("packets", 0))

    sent = {int(node): row for node, row in raw["nodes"].items() if row.get("packets")}
    busiest = sorted(sent.items(), key=lambda item: (-item[1]["packets"], item[0]))[:MESH_STATS_TOP_NODES]
    gateway_rows = {int(gateway): row for gateway, row in raw["gateways"].items()}
    registered = _registrations(mesh_id, [node for node, _ in busiest] + list(gateway_rows))
    nodes = [
        {
            "node_id": node,
            "device_uuid": registered.get(node),
            "packets": int(row.get("packets", 0)),
            "receptions": int(row.get("receptions", 0)),
        }
        for node, row in busiest
    ]
    gateway_total = sum(row.get("receptions", 0) for row in gateway_rows.values())
    gateways = []
    for gateway, row in sorted(gateway_rows.items(), key=lambda item: -item[1].get("receptions", 0)):
        heard = row.get("signal_receptions", 0)
        gateways.append(
            {
                "node_id": gateway,
                "device_uuid": registered.get(gateway),
                "receptions": int(row.get("receptions", 0)),
                "share": row.get("receptions", 0) / gateway_total if gateway_total else 0.0,
                "direct_receptions": int(row.get("direct_receptions", 0)),
                "rx_snr_mean": row.get("rx_snr_sum", 0) / heard if heard else None,
                "rx_rssi_mean": row.get("rx_rssi_sum", 0) / heard if heard else None,
            }
        )

    hops = sorted(
        ({"hops": _int_or_none(h), "packets": int(row.get("packets", 0))} for h, row in raw["hops"].items()),
        key=lambda h: (h["hops"] is None, h["hops"] or 0),
    )
    signal = {"snr": [], "rssi": []}
    for (metric, bucket), row in raw["signal"].items():
        if metric in signal:
            signal[metric].append({"bucket": float(bucket), "receptions": int(row.get("receptions", 0))})
    for buckets in signal.values():
        buckets.sort(key=lambda b: b["bucket"])

    airtime = [
        {"channel": channel_name("device_metrics", field), **values}
        for field, values in sorted(raw["airtime"].items())
    ]
    utilization = raw["airtime"].get("channel_utilization", {})
    return {
        "mesh_id": mesh_id,
        "range": range_,
        "window": window,
        "hourly_start": hourly_start,
        "generated_at": now,
        "summary": {
            **totals,
            "receptions_per_packet": totals["receptions"] / totals["packets"] if totals["packets"] else None,
            "active_nodes": len(sent),
            "channel_utilization_mean": utilization.get("mean"),
            "channel_utilization_peak": utilization.get("peak"),
        },
        "traffic": traffic,
        "airtime": airtime,
        "nodes": nodes,
        "gateways": gateways,
        "hops": hops,
        "signal": signal,
    }


class MeshStatsView(ReadingsAPIView):
    """Return traffic and congestion figures for a mesh over a fixed range.

    Counts every packet the mesh's registered gateways hear, including text
    messages, routing traffic and packets that could not be decrypted. A packet
    heard by several gateways is one packet and several receptions. Packets from
    nodes the owner rejected count towards the totals but are never listed as
    nodes. Channel utilization and airtime are the figures the nodes report
    about themselves.

    Busiest nodes, gateways, hops and signal are kept per hour, so they start at
    `hourly_start`, the whole hour on or before the start of the range. Figures
    from the last few minutes are still being counted and may grow.

    Results are computed at most once a minute per mesh and range, so a repeated
    call within that minute returns the same figures. A public mesh is readable
    without credentials.

    Args:
        range: Period to cover, ending now. One of `1h`, `24h`, `7d` or `30d`.
            Defaults to `24h`.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        parameters=[_query("range", "Period to cover, ending now.", enum=list(MESH_STATS_RANGES), default="24h")],
        responses=MeshStatsResponseSerializer,
    )
    def get(self, request, mesh_id):
        _require_visible_mesh(request, mesh_id)
        range_ = request.query_params.get("range", "24h")
        if range_ not in MESH_STATS_RANGES:
            raise ValidationError(f"range must be one of {', '.join(MESH_STATS_RANGES)}")
        key = f"mesh-stats:{mesh_id}:{range_}"
        body = cache.get(key)
        if body is None:
            body = MeshStatsResponseSerializer(_mesh_stats(str(mesh_id), range_, datetime.now(timezone.utc))).data
            cache.set(key, body, MESH_STATS_CACHE_SECONDS)
        return Response(body)


class DeviceQualityView(QualityView):
    """Data-quality figures for a device, addressed by its registration ID."""

    @extend_schema(parameters=RANGE_PARAMS, responses=DeviceQualityResponseSerializer)
    def get(self, request, device_uuid):
        mesh_id, node_id = _resolve_device_uuid(request, device_uuid)
        return super().get(request, mesh_id, node_id)


class DeviceReadingsView(ReadingsView):
    """Readings over a time range, addressed by the device's registration ID."""

    @extend_schema(parameters=READINGS_PARAMS, responses=ReadingsResponseSerializer)
    def get(self, request, device_uuid):
        mesh_id, node_id = _resolve_device_uuid(request, device_uuid)
        return super().get(request, mesh_id, node_id)


class DeviceLatestView(LatestView):
    """Most recent readings, addressed by the device's registration ID.

    A device on a public mesh is readable without credentials. Rejected
    registrations are not.
    """

    @extend_schema(parameters=LATEST_PARAMS, responses={200: LATEST_RESPONSE})
    def get(self, request, device_uuid):
        mesh_id, node_id = _resolve_device_uuid(request, device_uuid)
        return super().get(request, mesh_id, node_id)
