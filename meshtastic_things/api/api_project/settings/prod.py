"""Production settings - fail at startup on misconfiguration rather than
serving requests with an unsafe one."""
from django.core.exceptions import ImproperlyConfigured

from common.env import env_bool, env_int, env_list, env_str

from .base import *  # noqa: F401,F403
from .base import ENV_PREFIX, IS_READINGS, REST_FRAMEWORK

# DEBUG in production leaks settings and stack traces.
DEBUG = False

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

ALLOWED_HOSTS = env_list(f"{ENV_PREFIX}__ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        f"{ENV_PREFIX}__ALLOWED_HOSTS must list the hostnames this API is served on "
        "(e.g. api.yourdomain.com)"
    )
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        f"{ENV_PREFIX}__ALLOWED_HOSTS is '*', which accepts any Host header. Name the "
        "real hostnames"
    )

if not IS_READINGS:
    EMAIL_BACKEND = env_str("REGISTRY__EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
    EMAIL_HOST = env_str("REGISTRY__EMAIL_HOST", "")
    EMAIL_PORT = env_int("REGISTRY__EMAIL_PORT", 587)
    EMAIL_HOST_USER = env_str("REGISTRY__EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env_str("REGISTRY__EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("REGISTRY__EMAIL_USE_TLS", True)
    EMAIL_USE_SSL = env_bool("REGISTRY__EMAIL_USE_SSL", False)
    DEFAULT_FROM_EMAIL = env_str("REGISTRY__DEFAULT_FROM_EMAIL", "noreply@example.com")

    _SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_BACKEND == _SMTP_BACKEND and EMAIL_HOST in {"", "mailhog", "localhost"}:
        raise ImproperlyConfigured(
            f"REGISTRY__EMAIL_HOST={EMAIL_HOST!r} is not a production mail server. "
        )

    EMAIL_VERIFICATION_TTL_HOURS = env_int("REGISTRY__EMAIL_VERIFICATION_TTL_HOURS", 24)
    PASSWORD_RESET_TTL_HOURS = env_int("REGISTRY__PASSWORD_RESET_TTL_HOURS", 1)

    # Verification link (clicked directly against the API, no frontend involved)
    PUBLIC_BASE_URL = env_str("REGISTRY__PUBLIC_BASE_URL", "")
    if not PUBLIC_BASE_URL:
        raise ImproperlyConfigured(
            "REGISTRY__PUBLIC_BASE_URL must be the externally reachable base URL "
            "(e.g. https://api.yourdomain.com)"
        )

    # Password reset link (opened in the frontend app, which then calls this
    # API with the token as a bearer credential)
    PUBLIC_FRONTEND_URL = env_str("REGISTRY__PUBLIC_FRONTEND_URL", "")
    if not PUBLIC_FRONTEND_URL:
        raise ImproperlyConfigured(
            "REGISTRY__PUBLIC_FRONTEND_URL must be the frontend app's base URL "
            "(e.g. https://app.yourdomain.com)"
        )

# Behind Caddy by default
if env_bool(f"{ENV_PREFIX}__BEHIND_TLS", True):
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if not IS_READINGS:
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
