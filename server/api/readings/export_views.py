import structlog
from drf_spectacular.utils import OpenApiResponse, extend_schema
from registry.models import Mesh
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from . import archive, exports
from .archive_views import storage
from .serializers import ExportRequestSerializer, ExportSerializer
from .throttling import ExportsThrottle, OwnerRateThrottle

log = structlog.get_logger()


class ExportInProgress(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "You already have an export queued or running. Request another once it has finished."
    default_code = "export_in_progress"


def _require_mesh_owner(request, mesh_id) -> None:
    """Superusers, or the mesh's owner. Anyone else is told the mesh does not exist.

    Answers 404 too where the instance has no bucket (lite).
    """
    if not archive.is_enabled():
        raise NotFound("Not found")
    user = request.user
    if not (user.is_superuser or Mesh.objects.filter(pk=mesh_id, owner_id=user.id).exists()):
        raise NotFound("Mesh not found")


def _data(job: dict) -> dict:
    return ExportSerializer({**job, "filename": exports.filename(job), "url": exports.download_url(job)}).data


class ExportListView(APIView):
    @extend_schema(responses=ExportSerializer(many=True))
    def get(self, request):
        """List the caller's exports of every mesh from the last 30 days, newest first.

        A ready export becomes `expired` 24 hours after it finished, when its file
        is deleted; request it again to rebuild it. Empty on an instance without
        object storage.
        """
        if not archive.is_enabled():
            return Response([])
        return Response([_data(job) for job in exports.list_for(request.user.id)])


class ExportListCreateView(APIView):
    def get_throttles(self):
        if self.request.method == "POST":
            return [OwnerRateThrottle(), ExportsThrottle()]
        return super().get_throttles()

    @extend_schema(responses=ExportSerializer(many=True))
    def get(self, request, mesh_id):
        """List the caller's exports of a mesh from the last 30 days, newest first.

        A ready export becomes `expired` 24 hours after it finished, when its file
        is deleted. Available to the mesh's owner and to superusers.
        """
        _require_mesh_owner(request, mesh_id)
        return Response([_data(job) for job in exports.list_for(request.user.id, mesh_id)])

    @extend_schema(
        request=ExportRequestSerializer,
        responses={
            202: ExportSerializer,
            200: OpenApiResponse(ExportSerializer, description="The identical export already queued or running."),
            403: OpenApiResponse(description="Parquet exports need the operator role."),
            404: OpenApiResponse(description="No such mesh, or nothing archived in the range (Parquet)."),
            429: OpenApiResponse(description="Another export is queued or running."),
        },
    )
    def post(self, request, mesh_id):
        """Request a download of a mesh's readings over a range of days, as one zip.

        The zip is built in the background: poll the export until its status is
        `ready`, then download it from `url`. The owner is also emailed when it is
        ready or has failed. A CSV export reads every stored reading, a file per
        measurement and day with a column per field, plus `channels.csv` with each
        channel's unit. A Parquet export holds the hourly archive files, only for
        devices whose archive is on. Each owner has one export queued or running at a
        time, and repeating that same request returns it. Available to the mesh's
        owner and to superusers; Parquet also needs the operator role.

        Args:
            format: `csv` or `parquet`. Required.
            start: First day, as `YYYY-MM-DD` in UTC. Required.
            stop: Last day, included, as `YYYY-MM-DD` in UTC. Required. At most a year after `start`.
            node_ids: Node numbers to limit a CSV export to. Defaults to every device of the mesh.
        """
        _require_mesh_owner(request, mesh_id)
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["format"] == exports.PARQUET:
            if not (request.user.is_superuser or request.user.is_operator):
                raise PermissionDenied("Parquet exports need the operator role")
            with storage():
                if not archive.list_partitions(mesh_id, data["start"], data["stop"]):
                    raise NotFound("Nothing archived in that range")
        try:
            job, created = exports.create(
                request.user.id, mesh_id, data["format"], data["start"], data["stop"], data.get("node_ids")
            )
        except exports.ExportLimitReached:
            raise ExportInProgress()
        return Response(_data(job), status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK)


class ExportDetailView(APIView):
    @extend_schema(responses=ExportSerializer)
    def get(self, request, mesh_id, export_id):
        """Return one of the caller's exports: its status, progress in days and, once ready, a download link.

        The link is valid until `expires_at`, 24 hours after the export finished,
        and works for anyone who has it. The status then becomes `expired`.
        """
        _require_mesh_owner(request, mesh_id)
        job = exports.get(export_id)
        if not job or job["owner_id"] != str(request.user.id) or job["mesh_id"] != str(mesh_id):
            raise NotFound("Export not found")
        return Response(_data(job))
