from django.conf import settings
from rest_framework import serializers

from mesh_things import exports


class PointSerializer(serializers.Serializer):
    time = serializers.CharField()
    value = serializers.JSONField(allow_null=True)  # float | str | bool | None


class SeriesSerializer(serializers.Serializer):
    channel = serializers.CharField()
    points = PointSerializer(many=True)


class ReadingsResponseSerializer(serializers.Serializer):
    mesh_id = serializers.CharField()
    node_id = serializers.IntegerField()
    payload_kind = serializers.CharField()
    series = SeriesSerializer(many=True)


class LatestReadingSerializer(serializers.Serializer):
    payload_kind = serializers.CharField()
    field_name = serializers.CharField()
    channel = serializers.CharField()
    value = serializers.JSONField(allow_null=True)
    time = serializers.CharField()
    unit = serializers.CharField(allow_null=True)
    quantity_kind = serializers.CharField(allow_null=True)
    vocabulary_uri = serializers.CharField(allow_null=True)
    # "measured", "device" or "computed"
    origin = serializers.CharField()


class LatestReadingsResponseSerializer(serializers.Serializer):
    mesh_id = serializers.CharField()
    node_id = serializers.IntegerField()
    readings = LatestReadingSerializer(many=True)


class ChannelQualitySerializer(serializers.Serializer):
    channel = serializers.CharField()
    completeness_ratio = serializers.FloatField(allow_null=True)
    observed = serializers.FloatField(allow_null=True)
    expected = serializers.FloatField(allow_null=True)
    largest_gap_seconds = serializers.FloatField(allow_null=True)


class DeviceQualityResponseSerializer(serializers.Serializer):
    mesh_id = serializers.CharField()
    node_id = serializers.IntegerField()
    start = serializers.CharField()
    stop = serializers.CharField()
    points_ingested = serializers.FloatField()
    range_ratio = serializers.FloatField(allow_null=True)
    alarms_by_detector = serializers.DictField(child=serializers.IntegerField())
    channels = ChannelQualitySerializer(many=True)


class MeshStatsSummarySerializer(serializers.Serializer):
    packets = serializers.IntegerField(help_text="Distinct packets, counted once however many gateways heard them.")
    receptions = serializers.IntegerField(help_text="Packets counted once per gateway that heard them.")
    receptions_per_packet = serializers.FloatField(allow_null=True)
    bytes = serializers.IntegerField(help_text="Payload bytes of the distinct packets.")
    decoded_packets = serializers.IntegerField(
        help_text="Packets that decrypted to a known portnum. Rejected nodes' packets are never decrypted."
    )
    rejected_packets = serializers.IntegerField(
        help_text="Packets from nodes the owner rejected. Included in `packets`, never in `nodes`."
    )
    active_nodes = serializers.IntegerField(help_text="Nodes that sent at least one packet since `hourly_start`.")
    channel_utilization_mean = serializers.FloatField(allow_null=True)
    channel_utilization_peak = serializers.FloatField(allow_null=True)


class MeshTrafficSerializer(serializers.Serializer):
    portnum = serializers.IntegerField(allow_null=True, help_text="Null for packets that could not be decrypted.")
    name = serializers.CharField(help_text="The portnum's Meshtastic name, for example `TELEMETRY_APP`.")
    packets = serializers.IntegerField()
    receptions = serializers.IntegerField()
    points = PointSerializer(many=True, help_text="Receptions per `window`.")


class MeshAirtimeSerializer(serializers.Serializer):
    channel = serializers.CharField()
    mean = serializers.FloatField(allow_null=True)
    peak = serializers.FloatField(allow_null=True)
    points = PointSerializer(many=True)


class MeshNodeTrafficSerializer(serializers.Serializer):
    node_id = serializers.IntegerField()
    device_uuid = serializers.UUIDField(allow_null=True, help_text="Registration ID, when the node is registered.")
    packets = serializers.IntegerField()
    receptions = serializers.IntegerField()


class MeshGatewayTrafficSerializer(serializers.Serializer):
    node_id = serializers.IntegerField()
    device_uuid = serializers.UUIDField(allow_null=True)
    receptions = serializers.IntegerField()
    share = serializers.FloatField(help_text="Fraction of all receptions since `hourly_start`.")
    direct_receptions = serializers.IntegerField(help_text="Receptions heard straight from the sender, with no hop.")
    rx_snr_mean = serializers.FloatField(allow_null=True, help_text="Mean SNR in dB of receptions heard over the air.")
    rx_rssi_mean = serializers.FloatField(allow_null=True, help_text="Mean RSSI in dBm of receptions heard over the air.")


class MeshHopsSerializer(serializers.Serializer):
    hops = serializers.IntegerField(allow_null=True, help_text="Hops taken. Null for firmware that does not report it.")
    packets = serializers.IntegerField()


class MeshSignalBucketSerializer(serializers.Serializer):
    bucket = serializers.FloatField(help_text="Lower bound of the bucket.")
    receptions = serializers.IntegerField()


class MeshSignalSerializer(serializers.Serializer):
    snr = MeshSignalBucketSerializer(many=True, help_text="Receptions per 2.5 dB of SNR.")
    rssi = MeshSignalBucketSerializer(many=True, help_text="Receptions per 10 dBm of RSSI.")


class MeshGatewayPairSerializer(serializers.Serializer):
    gateway_a = serializers.IntegerField()
    gateway_b = serializers.IntegerField()
    device_uuid_a = serializers.UUIDField(allow_null=True)
    device_uuid_b = serializers.UUIDField(allow_null=True)
    common_packets = serializers.IntegerField(help_text="Packets both gateways heard.")
    snr_diff_mean = serializers.FloatField(
        allow_null=True, help_text="Mean SNR of `gateway_a` minus `gateway_b`, in dB, over packets both heard over the air."
    )
    rssi_diff_mean = serializers.FloatField(allow_null=True, help_text="The same for RSSI, in dBm.")


class MeshRelayCandidateSerializer(serializers.Serializer):
    node_id = serializers.IntegerField()
    device_uuid = serializers.UUIDField()


class MeshRelaySerializer(serializers.Serializer):
    gateway_id = serializers.IntegerField()
    device_uuid = serializers.UUIDField(allow_null=True)
    relay = serializers.IntegerField(help_text="Last byte of the relaying node's number, as the firmware reports it.")
    receptions = serializers.IntegerField()
    candidates = MeshRelayCandidateSerializer(
        many=True, help_text="Registered nodes of the mesh whose number ends in `relay`."
    )


class MeshActivitySerializer(serializers.Serializer):
    nodes = PointSerializer(many=True, help_text="Nodes that sent at least one packet, per `activity_window`.")
    gateways = PointSerializer(many=True, help_text="Gateways that heard at least one packet, per `activity_window`.")


class MeshStatsResponseSerializer(serializers.Serializer):
    mesh_id = serializers.CharField()
    range = serializers.CharField()
    window = serializers.CharField(help_text="Bucket size of the traffic and airtime series.")
    activity_window = serializers.CharField(help_text="Bucket size of the `activity` series.")
    hourly_start = serializers.DateTimeField(
        help_text="Start of the hourly figures: nodes, gateways, hops and signal."
    )
    generated_at = serializers.DateTimeField()
    summary = MeshStatsSummarySerializer()
    traffic = MeshTrafficSerializer(many=True)
    airtime = MeshAirtimeSerializer(many=True)
    nodes = MeshNodeTrafficSerializer(many=True)
    gateways = MeshGatewayTrafficSerializer(many=True)
    hops = MeshHopsSerializer(many=True)
    signal = MeshSignalSerializer()
    gateway_pairs = MeshGatewayPairSerializer(many=True)
    relays = MeshRelaySerializer(many=True)
    activity = MeshActivitySerializer()


class NodePortSerializer(serializers.Serializer):
    portnum = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    packets = serializers.IntegerField()


class NodeTrafficResponseSerializer(serializers.Serializer):
    mesh_id = serializers.CharField()
    node_id = serializers.IntegerField()
    range = serializers.CharField()
    window = serializers.CharField()
    hourly_start = serializers.DateTimeField()
    packets = serializers.IntegerField()
    receptions = serializers.IntegerField()
    ports = NodePortSerializer(many=True)
    points = PointSerializer(many=True, help_text="Packets sent per `window`.")


class ArchivePartitionSerializer(serializers.Serializer):
    dt = serializers.DateField()
    hour = serializers.IntegerField(min_value=0, max_value=23)
    size = serializers.IntegerField(help_text="Object size in bytes.")
    last_modified = serializers.DateTimeField()


class ArchiveManifestSerializer(serializers.Serializer):
    mesh_id = serializers.UUIDField()
    prefix = serializers.CharField()
    partitions = ArchivePartitionSerializer(many=True)


class ArchiveCredentialsSerializer(serializers.Serializer):
    access_key_id = serializers.CharField()
    secret_access_key = serializers.CharField()
    session_token = serializers.CharField()
    expires_at = serializers.DateTimeField()
    endpoint = serializers.CharField(
        allow_null=True, help_text="S3 endpoint to connect to. Null means the provider's default (AWS)."
    )
    region = serializers.CharField()
    bucket = serializers.CharField()
    prefix = serializers.CharField()
    s3_path = serializers.CharField()


class ExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=exports.FORMATS)
    start = serializers.DateField(help_text="First day, as `YYYY-MM-DD` (UTC).")
    stop = serializers.DateField(help_text="Last day, included, as `YYYY-MM-DD` (UTC).")
    node_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=0),
        required=False,
        allow_empty=False,
        max_length=100,
        help_text="Limit a CSV export to these node numbers. Defaults to every device of the mesh.",
    )

    def validate(self, data):
        if data["stop"] < data["start"]:
            raise serializers.ValidationError({"stop": ["Must not be before start."]})
        if (data["stop"] - data["start"]).days + 1 > settings.EXPORT_MAX_DAYS:
            raise serializers.ValidationError({"stop": [f"An export covers at most {settings.EXPORT_MAX_DAYS} days."]})
        if data["format"] == exports.PARQUET and data.get("node_ids"):
            raise serializers.ValidationError(
                {"node_ids": ["Only CSV exports can be limited to devices; Parquet files hold the whole mesh."]}
            )
        return data


class ExportSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    mesh_id = serializers.UUIDField()
    format = serializers.ChoiceField(choices=exports.FORMATS)
    start = serializers.DateField()
    stop = serializers.DateField()
    node_ids = serializers.ListField(child=serializers.IntegerField(), allow_null=True)
    status = serializers.ChoiceField(choices=exports.STATUSES)
    days_done = serializers.IntegerField()
    days_total = serializers.IntegerField()
    size = serializers.IntegerField(allow_null=True, help_text="Zip size in bytes, once ready.")
    error = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(help_text="Time at which the file is deleted and the export becomes `expired`.")
    filename = serializers.CharField()
    url = serializers.CharField(allow_null=True, help_text="Download link while ready, valid until `expires_at`.")
