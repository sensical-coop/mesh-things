from contextlib import contextmanager
from datetime import date

import structlog
from botocore.exceptions import BotoCoreError, ClientError
from django.db import connection
from django.http import HttpResponseRedirect, StreamingHttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, OpenApiTypes, extend_schema
from registry.exceptions import BadGateway
from registry.models import Mesh
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import archive
from .serializers import ArchiveCredentialsSerializer, ArchiveManifestSerializer
from .throttling import ArchiveCredentialsThrottle, OwnerRateThrottle

log = structlog.get_logger()

MANIFEST_PARAMS = [
    OpenApiParameter("start", OpenApiTypes.DATE, OpenApiParameter.QUERY, description="Earliest day, as `YYYY-MM-DD`."),
    OpenApiParameter("stop", OpenApiTypes.DATE, OpenApiParameter.QUERY, description="Latest day, as `YYYY-MM-DD`."),
]


def _require_archive_access(request, mesh_id, credentials=False) -> None:
    """Superusers, or the mesh's owner while an operator. Anyone else is told the mesh
    does not exist, as the other readings routes do.

    Answers 404 too where the instance runs no archive (lite), and for credentials
    where the storage has no STS.
    """
    if not (archive.issues_credentials() if credentials else archive.is_enabled()):
        raise NotFound("Not found")
    user = request.user
    if user.is_superuser:
        return
    if not (user.is_operator and Mesh.objects.filter(pk=mesh_id, owner_id=user.id).exists()):
        raise NotFound("Mesh not found")


@contextmanager
def _storage():
    try:
        yield
    except (BotoCoreError, ClientError) as e:
        log.warning("archive_storage_failed", error=str(e))
        raise BadGateway("The archive storage could not be reached")


def _day(request, name) -> date | None:
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: ["Expected a date as YYYY-MM-DD."]})


class ArchiveManifestView(APIView):
    @extend_schema(parameters=MANIFEST_PARAMS, responses=ArchiveManifestSerializer)
    def get(self, request, mesh_id):
        """List the hourly Parquet files archived for a mesh, oldest first.

        Only devices whose archive is switched on are stored, from the moment it
        was switched on, so the list stays empty until one of them reports.
        Available to the mesh's owner while they are an operator, and to
        superusers.

        Args:
            start: Earliest day to include, as `YYYY-MM-DD`. Defaults to the first archived day.
            stop: Latest day to include, as `YYYY-MM-DD`. Defaults to the last archived day.
        """
        _require_archive_access(request, mesh_id)
        start, stop = _day(request, "start"), _day(request, "stop")
        with _storage():
            partitions = archive.list_partitions(mesh_id, start, stop)
        body = {"mesh_id": mesh_id, "prefix": archive.mesh_prefix(mesh_id), "partitions": partitions}
        return Response(ArchiveManifestSerializer(body).data)


class ArchiveCredentialsView(APIView):
    throttle_classes = [OwnerRateThrottle, ArchiveCredentialsThrottle]

    @extend_schema(request=None, responses={201: ArchiveCredentialsSerializer})
    def post(self, request, mesh_id):
        """Issue temporary S3 credentials that can read this mesh's archive and nothing else.

        Use them with DuckDB, pandas or any S3 client to query the archive as a
        partitioned dataset. The secret is shown in this response only. The
        credentials cannot be revoked and stay valid until `expires_at`, even if
        the caller loses access to the mesh in the meantime. Available to the
        mesh's owner while they are an operator, and to superusers.
        """
        _require_archive_access(request, mesh_id, credentials=True)
        with _storage():
            credentials = archive.issue_credentials(mesh_id, session_name=f"owner-{request.user.id}")
        log.info(
            "archive_credentials_issued",
            owner_id=str(request.user.id),
            mesh_id=str(mesh_id),
            expires_at=credentials["expires_at"].isoformat(),
        )
        return Response(ArchiveCredentialsSerializer(credentials).data, status=201)


class ArchivePartitionView(APIView):
    @extend_schema(
        responses={
            302: OpenApiResponse(description="Redirect to a temporary download link for the Parquet file."),
            404: OpenApiResponse(description="No such mesh, or nothing archived for that hour."),
        }
    )
    def get(self, request, mesh_id, day, hour):
        """Download one hour of a mesh's archive as a Parquet file.

        Answers with a redirect to a temporary link, valid for the same time as
        issued credentials, that any HTTP client can follow. The file does not
        carry `mesh_id` as a column. Available to the mesh's owner while they are
        an operator, and to superusers.
        """
        _require_archive_access(request, mesh_id)
        if hour > 23:
            raise NotFound("Partition not found")
        try:
            key = archive.partition_key(mesh_id, date.fromisoformat(day), hour)
        except ValueError:
            raise NotFound("Partition not found")
        with _storage():
            if not archive.object_exists(key):
                raise NotFound("Partition not found")
            return HttpResponseRedirect(archive.presigned_url(key))


def _without_db(chunks):
    """Release the request's DB connection before the first chunk, as a download can
    outlast any query by minutes. Never inside a transaction, which it would break."""
    if not connection.in_atomic_block:
        connection.close()
    yield from chunks


def _zip_name(mesh_id, partitions) -> str:
    """By the mesh's short id: readings may not read mesh labels (provision_read_role)."""
    first, last = partitions[0]["dt"], partitions[-1]["dt"]
    days = f"{first:%Y-%m-%d}" if first == last else f"{first:%Y-%m-%d}_{last:%Y-%m-%d}"
    return f"mesh-{str(mesh_id)[:8]}_{days}.zip"


class ArchiveZipView(APIView):
    @extend_schema(
        parameters=MANIFEST_PARAMS,
        responses={
            (200, "application/zip"): OpenApiResponse(
                OpenApiTypes.BINARY, description="The hourly Parquet files of the range, as one zip."
            ),
            404: OpenApiResponse(description="No such mesh, or nothing archived in the range."),
        },
    )
    def get(self, request, mesh_id):
        """Download a range of a mesh's archive as one zip, a folder per day.

        Each hour is `YYYY-MM-DD/YYYY-MM-DD_HH.parquet` (UTC), so a day or the whole
        archive is one download. The zip streams as the files are read, and holds
        what the file list shows at the time of the request. For querying in place,
        issue credentials instead. Available to the mesh's owner while they are an
        operator, and to superusers.

        Args:
            start: Earliest day to include, as `YYYY-MM-DD`. Defaults to the first archived day.
            stop: Latest day to include, as `YYYY-MM-DD`. Defaults to the last archived day.
        """
        _require_archive_access(request, mesh_id)
        start, stop = _day(request, "start"), _day(request, "stop")
        with _storage():
            partitions = archive.list_partitions(mesh_id, start, stop)
        if not partitions:
            raise NotFound("Nothing archived in that range")
        log.info("archive_zip_download", owner_id=str(request.user.id), mesh_id=str(mesh_id), files=len(partitions))
        chunks = _without_db(archive.zip_partitions(mesh_id, partitions))
        response = StreamingHttpResponse(chunks, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{_zip_name(mesh_id, partitions)}"'
        return response
