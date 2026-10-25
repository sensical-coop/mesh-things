from django.urls import path

from . import archive_views, export_views, views

# Mounted under `readings/`. A device can be addressed by its registration ID
# or, store-natively, by mesh and node number.
urlpatterns = [
    path("devices/<uuid:device_uuid>", views.DeviceReadingsView.as_view()),
    path("devices/<uuid:device_uuid>/latest", views.DeviceLatestView.as_view()),
    path("devices/<uuid:device_uuid>/quality", views.DeviceQualityView.as_view()),
    path("devices/<uuid:device_uuid>/traffic", views.DeviceTrafficView.as_view()),
    path("meshes/<uuid:mesh_id>/nodes/<int:node_id>", views.ReadingsView.as_view()),
    path("meshes/<uuid:mesh_id>/nodes/<int:node_id>/latest", views.LatestView.as_view()),
    path("meshes/<uuid:mesh_id>/nodes/<int:node_id>/quality", views.QualityView.as_view()),
    path("meshes/<uuid:mesh_id>/nodes/<int:node_id>/traffic", views.NodeTrafficView.as_view()),
    path("meshes/<uuid:mesh_id>/stats", views.MeshStatsView.as_view()),
    path("exports", export_views.ExportListView.as_view()),
    path("meshes/<uuid:mesh_id>/exports", export_views.ExportListCreateView.as_view()),
    path("meshes/<uuid:mesh_id>/exports/<uuid:export_id>", export_views.ExportDetailView.as_view()),
    path("archive/meshes/<uuid:mesh_id>", archive_views.ArchiveManifestView.as_view()),
    path("archive/meshes/<uuid:mesh_id>/credentials", archive_views.ArchiveCredentialsView.as_view()),
    path(
        "archive/meshes/<uuid:mesh_id>/partitions/<str:day>/<int:hour>",
        archive_views.ArchivePartitionView.as_view(),
    ),
]
