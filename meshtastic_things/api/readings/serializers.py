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
