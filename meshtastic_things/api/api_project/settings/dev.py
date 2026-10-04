"""Local development settings.
"""
from common.env import env_bool, env_int, env_list, env_str

from .base import *  # noqa: F401,F403
from .base import ENV_PREFIX, IS_READINGS, SENDS_EMAIL

DEBUG = env_bool(f"{ENV_PREFIX}__DEBUG", True)
ALLOWED_HOSTS = env_list(f"{ENV_PREFIX}__ALLOWED_HOSTS", ["*"])

if SENDS_EMAIL:
    # Email defaults to MailHog (the `mailhog` service in docker-compose.dev.yml).
    EMAIL_BACKEND = env_str("REGISTRY__EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
    EMAIL_HOST = env_str("REGISTRY__EMAIL_HOST", "mailhog")
    EMAIL_PORT = env_int("REGISTRY__EMAIL_PORT", 1025)
    EMAIL_HOST_USER = env_str("REGISTRY__EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env_str("REGISTRY__EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("REGISTRY__EMAIL_USE_TLS", False)
    EMAIL_USE_SSL = env_bool("REGISTRY__EMAIL_USE_SSL", False)
    EMAIL_TIMEOUT = 10
    DEFAULT_FROM_EMAIL = env_str("REGISTRY__DEFAULT_FROM_EMAIL", "noreply@example.com")

if not IS_READINGS:
    EMAIL_VERIFICATION_TTL_HOURS = env_int("REGISTRY__EMAIL_VERIFICATION_TTL_HOURS", 24)
    PASSWORD_RESET_TTL_HOURS = env_int("REGISTRY__PASSWORD_RESET_TTL_HOURS", 1)
    PUBLIC_BASE_URL = env_str("REGISTRY__PUBLIC_BASE_URL", "http://localhost:8090")
    PUBLIC_FRONTEND_URL = env_str("REGISTRY__PUBLIC_FRONTEND_URL", "http://localhost:5173")

if env_bool(f"{ENV_PREFIX}__BEHIND_TLS", False):
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if not IS_READINGS:
        SESSION_COOKIE_SECURE = True
        CSRF_COOKIE_SECURE = True
