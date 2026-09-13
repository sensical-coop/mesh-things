from api_project.urls_readings import api_urlpatterns as readings_urlpatterns
from api_project.urls_registry import api_urlpatterns as registry_urlpatterns

urlpatterns = [*registry_urlpatterns, *readings_urlpatterns]
