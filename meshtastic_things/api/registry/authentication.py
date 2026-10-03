from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import authentication, exceptions

from .auth import hash_api_key
from .models import Owner
from .throttling import client_ident

FAILED_AUTH_RATE_LIMIT = 30
FAILED_AUTH_RATE_WINDOW_SECONDS = 60


class OwnerBearerAuthentication(authentication.BaseAuthentication):
    """
    Authenticates the caller as the Owner whose API key was presented, via
    `Authorization: Bearer <api_key>`. Falls back to an `access_token` query
    parameter and only checked when no Authorization header is
    present.
    """

    keyword = b"bearer"

    def authenticate(self, request):
        token = self._token_from_header(request) or request.query_params.get("access_token")
        if not token:
            return None

        cache_key = f"registry:failed-auth:{client_ident(request)}"
        if (cache.get(cache_key) or 0) >= FAILED_AUTH_RATE_LIMIT:
            raise exceptions.Throttled(detail="Too many invalid credentials, slow down")

        owner = Owner.objects.filter(api_key_hash=hash_api_key(token)).first()
        if owner is None:
            self._record_failed_attempt(cache_key)
            raise exceptions.AuthenticationFailed("Invalid API key")
        return (owner, None)

    def _record_failed_attempt(self, cache_key: str) -> None:
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.set(cache_key, 1, FAILED_AUTH_RATE_WINDOW_SECONDS)

    def _token_from_header(self, request) -> str | None:
        parts = authentication.get_authorization_header(request).split()
        if len(parts) == 2 and parts[0].lower() == self.keyword:
            return parts[1].decode()
        return None

    def authenticate_header(self, request):
        return "Bearer"


class OwnerBearerAuthenticationScheme(OpenApiAuthenticationExtension):
    """Registers OwnerBearerAuthentication with drf-spectacular so /docs shows an
    Authorize button"""

    target_class = OwnerBearerAuthentication
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "API key"}


class OwnerResetPasswordAuthentication(authentication.BaseAuthentication):
    """
    Authenticates the caller as the Owner whose password-reset token was
    presented, via `Authorization: Bearer <token>`. The token is single-use
    and expires after `REGISTRY__PASSWORD_RESET_TTL_HOURS`.
    """

    keyword = b"bearer"

    def authenticate(self, request):
        token = self._token_from_header(request)
        if not token:
            return None

        owner = Owner.objects.filter(password_reset_token_hash=hash_api_key(token)).first()
        ttl = timedelta(hours=settings.PASSWORD_RESET_TTL_HOURS)
        expired = owner is None or owner.password_reset_sent_at is None or (
            timezone.now() > owner.password_reset_sent_at + ttl
        )
        if expired:
            raise exceptions.AuthenticationFailed(
                "Invalid or expired reset link - request a new one via "
                "POST /owners/request-password-reset"
            )
        return (owner, None)

    def _token_from_header(self, request) -> str | None:
        parts = authentication.get_authorization_header(request).split()
        if len(parts) == 2 and parts[0].lower() == self.keyword:
            return parts[1].decode()
        return None

    def authenticate_header(self, request):
        return "Bearer"


class OwnerResetPasswordAuthenticationScheme(OpenApiAuthenticationExtension):
    """Registers OwnerResetPasswordAuthentication with drf-spectacular so /docs shows
    an Authorize button distinct from the regular API-key bearer scheme"""

    target_class = OwnerResetPasswordAuthentication
    name = "resetTokenBearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer", "bearerFormat": "Password reset token"}
