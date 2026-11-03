from django.conf import settings
from django.middleware.security import SecurityMiddleware

import mesh_things


class InternalHostSecurityMiddleware(SecurityMiddleware):
    """SecurityMiddleware that skips the HTTPS redirect for other containers.

    Services such as the quality worker call the API by its compose service name
    over plain HTTP, bypassing the TLS proxy, so a redirect to HTTPS would fail.
    """

    def process_request(self, request):
        if request.get_host().partition(":")[0] == settings.INTERNAL_HOST:
            return None
        return super().process_request(request)


class ApiVersionMiddleware:
    """Send the API version on every response, so a client can tell it is out of date."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["API-Version"] = mesh_things.__version__
        return response
