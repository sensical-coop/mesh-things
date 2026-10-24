from rest_framework.throttling import AnonRateThrottle, BaseThrottle, SimpleRateThrottle


class SuperuserExempt:
    """Superusers are never throttled. Mixed in ahead of a throttle class."""

    def allow_request(self, request, view):
        if getattr(getattr(request, "user", None), "is_superuser", False):
            return True
        return super().allow_request(request, view)


def client_ident(request) -> str:
    """Return the caller's address, read through the reverse proxy like every DRF throttle."""
    return BaseThrottle().get_ident(request)


class OwnerRateThrottle(SuperuserExempt, SimpleRateThrottle):
    """Throttles authenticated traffic per Owner"""

    scope = "owner"

    def get_cache_key(self, request, view):
        if not (request.user and getattr(request.user, "is_authenticated", False)):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.id}


class AnonReadThrottle(SuperuserExempt, AnonRateThrottle):
    """Any anonymous GET request"""

    scope = "anon"

    def get_cache_key(self, request, view):
        if request.method != "GET":
            return None
        return super().get_cache_key(request, view)


class SignupThrottle(SuperuserExempt, SimpleRateThrottle):
    """POST /owners"""

    scope = "owner-signup"

    def get_cache_key(self, request, view):
        if request.method != "POST" or request.path != "/owners":
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginThrottle(SuperuserExempt, SimpleRateThrottle):
    """POST /owners/login, per source IP and email"""

    scope = "login"

    def get_cache_key(self, request, view):
        if request.method != "POST" or request.path != "/owners/login":
            return None
        email = request.data.get("email", "") if hasattr(request.data, "get") else ""
        ident = f"{self.get_ident(request)}:{str(email).strip().lower()}"
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ResendVerificationThrottle(SuperuserExempt, SimpleRateThrottle):
    """POST /owners/me/resend-verification"""

    scope = "resend-verification"

    def get_cache_key(self, request, view):
        if request.method != "POST" or request.path != "/owners/me/resend-verification":
            return None
        if not (request.user and getattr(request.user, "is_authenticated", False)):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.id}


class OperatorRequestThrottle(SuperuserExempt, SimpleRateThrottle):
    """POST /owners/me/operator-request"""

    scope = "operator-request"

    def get_cache_key(self, request, view):
        if request.method != "POST" or request.path != "/owners/me/operator-request":
            return None
        if not (request.user and getattr(request.user, "is_authenticated", False)):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.id}


class RequestPasswordResetThrottle(SuperuserExempt, SimpleRateThrottle):
    """POST /owners/request-password-reset"""

    scope = "request-password-reset"

    def get_cache_key(self, request, view):
        if request.method != "POST" or request.path != "/owners/request-password-reset":
            return None
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}
