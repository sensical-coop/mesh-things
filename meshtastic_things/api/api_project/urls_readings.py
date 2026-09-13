"""Routes served by the readings role."""
from django.urls import include, path

from readings import views

api_urlpatterns = [
    path("readings/", include("readings.urls")),
]

urlpatterns = [
    # Container probe only
    path("health", views.HealthView.as_view()),
    *api_urlpatterns,
]

handler404 = "api_project.errors.not_found"
handler500 = "api_project.errors.server_error"
