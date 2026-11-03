"""Routes served by the registry role: owners, meshes, devices, the
measurement catalog and postprocessing blueprints.

`/schema` and `/docs` describe both roles, because the readings role
publishes no document of its own.
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# The described API surface, reused by urls_all for schema generation.
api_urlpatterns = [
    path("", include("registry.urls")),
]

urlpatterns = [
    path("admin", RedirectView.as_view(pattern_name="admin:index")), # Important trailing slash here
    path("admin/", admin.site.urls),
    path("schema", SpectacularAPIView.as_view(urlconf="api_project.urls_all"), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema")),
    *api_urlpatterns,
]

handler404 = "api_project.errors.not_found"
handler500 = "api_project.errors.server_error"
