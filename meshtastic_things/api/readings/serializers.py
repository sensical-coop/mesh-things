from django.conf import settings
from rest_framework import serializers


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
    format = serializers.ChoiceField(choices=["csv", "parquet"])
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
        if data["format"] == "parquet" and data.get("node_ids"):
            raise serializers.ValidationError(
                {"node_ids": ["Only CSV exports can be limited to devices; Parquet files hold the whole mesh."]}
            )
        return data


class ExportSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    mesh_id = serializers.UUIDField()
    format = serializers.ChoiceField(choices=["csv", "parquet"])
    start = serializers.DateField()
    stop = serializers.DateField()
    node_ids = serializers.ListField(child=serializers.IntegerField(), allow_null=True)
    status = serializers.ChoiceField(choices=["queued", "running", "ready", "failed", "expired"])
    days_done = serializers.IntegerField()
    days_total = serializers.IntegerField()
    size = serializers.IntegerField(allow_null=True, help_text="Zip size in bytes, once ready.")
    error = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(help_text="When the file is deleted and the export becomes `expired`.")
    filename = serializers.CharField()
    url = serializers.CharField(allow_null=True, help_text="Download link while ready, valid until `expires_at`.")
