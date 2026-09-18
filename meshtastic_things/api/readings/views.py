from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
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
from registry.models import Mesh

from .influx_client import get_client
from .measurement_catalog import get_measurement_types
from .serializers import (
    DeviceQualityResponseSerializer,
    LatestReadingsResponseSerializer,
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


def _require_owned_mesh(request, mesh_id) -> None:
    """Reject a mesh the caller does not own, without revealing whether it exists.
    """
    if request.user.is_superuser:
        return
    if not Mesh.objects.filter(pk=mesh_id, owner_id=request.user.id).exists():
        raise NotFound("Device not found")


def _resolve_device_uuid(request, device_uuid) -> tuple[str, int]:
    resolved = getattr(request.user, "devices_by_uuid", {}).get(str(device_uuid))
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
        _require_owned_mesh(request, mesh_id)
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
    one call, each annotated with its unit from the measurement catalog.

    Args:
        payload_kind: Restrict to one family, for example
            `telemetry:environment_metrics`. Defaults to every one.
        lookback: How far back to search for a value, as a relative duration, a
            date or a timestamp. Defaults to `-30d`.
    """

    @extend_schema(parameters=LATEST_PARAMS, responses={200: LATEST_RESPONSE})
    def get(self, request, mesh_id, node_id):
        _require_owned_mesh(request, mesh_id)
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
    share of readings within their plausible range, and how complete each
    channel was. Figures stay empty until the quality checks have run for the
    device.

    Args:
        start: Start of the range, as a relative duration such as `-24h`, a date
            such as `2026-09-01`, or a timestamp such as `2026-09-01T13:45:00Z`.
            Defaults to `-1h`.
        stop: End of the range, in the same forms as `start`, or `now()`.
            Defaults to `now()`.
    """

    @extend_schema(parameters=RANGE_PARAMS, responses=DeviceQualityResponseSerializer)
    def get(self, request, mesh_id, node_id):
        _require_owned_mesh(request, mesh_id)
        params = request.query_params
        start = params.get("start", "-1h")
        stop = params.get("stop", "now()")
        try:
            metrics = get_client().device_metrics(mesh_id, node_id, start, stop)
        except ValueError as e:
            raise ValidationError(str(e))
        body = {"mesh_id": mesh_id, "node_id": node_id, "start": start, "stop": stop, **metrics}
        return Response(DeviceQualityResponseSerializer(body).data)


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
    """Most recent readings, addressed by the device's registration ID."""

    @extend_schema(parameters=LATEST_PARAMS, responses={200: LATEST_RESPONSE})
    def get(self, request, device_uuid):
        mesh_id, node_id = _resolve_device_uuid(request, device_uuid)
        return super().get(request, mesh_id, node_id)
