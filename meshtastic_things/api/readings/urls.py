from django.urls import path

from . import views

# Mounted under `readings/`. A device can be addressed by its registration ID
# or, store-natively, by mesh and node number.
urlpatterns = [
    path("devices/<uuid:device_uuid>", views.DeviceReadingsView.as_view()),
    path("devices/<uuid:device_uuid>/latest", views.DeviceLatestView.as_view()),
    path("devices/<uuid:device_uuid>/quality", views.DeviceQualityView.as_view()),
    path("meshes/<uuid:mesh_id>/nodes/<int:node_id>", views.ReadingsView.as_view()),
    path("meshes/<uuid:mesh_id>/nodes/<int:node_id>/latest", views.LatestView.as_view()),
    path("meshes/<uuid:mesh_id>/nodes/<int:node_id>/quality", views.QualityView.as_view()),
]
