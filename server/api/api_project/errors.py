"""JSON errors for requests that never reach a view."""
from django.http import JsonResponse


def not_found(request, exception=None):
    return JsonResponse({"detail": "Not found. See / for the service index."}, status=404)


def server_error(request):
    return JsonResponse({"detail": "Internal server error"}, status=500)
