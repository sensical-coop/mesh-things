"""Production settings - fail at startup on misconfiguration rather than
serving requests with an unsafe one."""
from django.core.exceptions import ImproperlyConfigured

from common.env import env_bool, env_int, env_list, env_str

from .base import *  # noqa: F401,F403
from .base import ENV_PREFIX, IS_READINGS

# DEBUG in production leaks settings and stack traces.
DEBUG = False

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
    EMAIL_BACKEND = env_str("KEYAPI__EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
    EMAIL_HOST = env_str("KEYAPI__EMAIL_HOST", "")
    EMAIL_PORT = env_int("KEYAPI__EMAIL_PORT", 587)
    EMAIL_HOST_USER = env_str("KEYAPI__EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env_str("KEYAPI__EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("KEYAPI__EMAIL_USE_TLS", True)
    EMAIL_USE_SSL = env_bool("KEYAPI__EMAIL_USE_SSL", False)
    DEFAULT_FROM_EMAIL = env_str("KEYAPI__DEFAULT_FROM_EMAIL", "noreply@example.com")

    _SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_BACKEND == _SMTP_BACKEND and EMAIL_HOST in {"", "mailhog", "localhost"}:
        raise ImproperlyConfigured(
            f"KEYAPI__EMAIL_HOST={EMAIL_HOST!r} is not a production mail server. "
        )

    EMAIL_VERIFICATION_TTL_HOURS = env_int("KEYAPI__EMAIL_VERIFICATION_TTL_HOURS", 24)
    PASSWORD_RESET_TTL_HOURS = env_int("KEYAPI__PASSWORD_RESET_TTL_HOURS", 1)

    # Verification and reset links
    PUBLIC_BASE_URL = env_str("KEYAPI__PUBLIC_BASE_URL", "")
    if not PUBLIC_BASE_URL:
        raise ImproperlyConfigured(
            "KEYAPI__PUBLIC_BASE_URL must be the externally reachable base URL "
            "(e.g. https://api.yourdomain.com)"
        )

# Behind Caddy by default
if env_bool(f"{ENV_PREFIX}__BEHIND_TLS", True):
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if not IS_READINGS:
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
