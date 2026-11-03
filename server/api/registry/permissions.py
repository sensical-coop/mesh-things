from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsVerifiedOwner(BasePermission):
    """Authenticated AND is_active (email-verified)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active)


class IsSuperuser(BasePermission):

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsOperator(BasePermission):
    """Operator role or superuser; manages shared ingest infrastructure."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_operator)


class ReadOnlyOrVerifiedOwner(BasePermission):
    """Reads are open to anyone; writes need a verified owner."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or IsVerifiedOwner().has_permission(request, view)
