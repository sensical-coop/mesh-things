from django.conf import settings
from django.middleware.security import SecurityMiddleware


class InternalHostSecurityMiddleware(SecurityMiddleware):
    """SecurityMiddleware that skips the HTTPS redirect for other containers.

    Services such as the quality worker call the API by its compose service name
    over plain HTTP, bypassing the TLS proxy, so a redirect to HTTPS would fail.
    """

    def process_request(self, request):
        if request.get_host().partition(":")[0] == settings.INTERNAL_HOST:
            return None
        return super().process_request(request)
