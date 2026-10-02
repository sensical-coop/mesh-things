"""Settings shared by every environment."""

from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

from common.env import env_bool, env_int, env_list, env_str
from common.gateway import public_base_url

BASE_DIR = Path(__file__).resolve().parent.parent.parent

REGISTRY_ROLE = "registry"
READINGS_ROLE = "readings"
APP_ROLE = env_str("APP_ROLE", REGISTRY_ROLE)
if APP_ROLE not in (REGISTRY_ROLE, READINGS_ROLE):
    raise ImproperlyConfigured(
        f"APP_ROLE is {APP_ROLE!r}; expected {REGISTRY_ROLE!r} or {READINGS_ROLE!r} - see env.example"
    )
IS_READINGS = APP_ROLE == READINGS_ROLE

ENV_PREFIX = APP_ROLE.upper()
# Compose service name other containers use to reach this API directly.
INTERNAL_HOST = f"{APP_ROLE}-api"

SECRET_KEY = env_str(f"{ENV_PREFIX}__SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured(f"{ENV_PREFIX}__SECRET_KEY must be set - see env.example")
DEBUG = env_bool(f"{ENV_PREFIX}__DEBUG", False)
ALLOWED_HOSTS = env_list(f"{ENV_PREFIX}__ALLOWED_HOSTS")

# The readings role needs registry's models to authenticate. It also shares
# the sessions table (read-only so a browser
# holding registry's session cookie can be recognized here too.
INSTALLED_APPS = [
    "registry",
    "readings",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "drf_spectacular",
]
MIDDLEWARE = [
    "api_project.middleware.InternalHostSecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

if not IS_READINGS:
    INSTALLED_APPS += [
        "django.contrib.admin",
        "django.contrib.messages",
        "django.contrib.staticfiles",
    ]
    MIDDLEWARE = [
        "api_project.middleware.InternalHostSecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]

ROOT_URLCONF = f"api_project.urls_{APP_ROLE}"
WSGI_APPLICATION = "api_project.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": []
            if IS_READINGS
            else [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# The readings role's DSN points at the read-only Postgres role
DATABASES = {
    "default": dj_database_url.parse(
        env_str(f"{ENV_PREFIX}__DB_DSN", "postgresql://unset:unset@localhost:5432/unset")
    )
}

AUTH_USER_MODEL = "registry.Owner"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env_str(
            f"{ENV_PREFIX}__REDIS_URL", "redis://redis:6379/1" if IS_READINGS else "redis://redis:6379/0"
        ),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# No trailing slash on any route
APPEND_SLASH = False

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "registry.authentication.OwnerBearerAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"]
    if IS_READINGS
    else ["registry.permissions.IsVerifiedOwner"],
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
    "DEFAULT_THROTTLE_CLASSES": ["registry.throttling.OwnerRateThrottle"]
    if IS_READINGS
    else [
        "registry.throttling.OwnerRateThrottle",
        "registry.throttling.AnonReadThrottle",
        "registry.throttling.SignupThrottle",
        "registry.throttling.ResendVerificationThrottle",
        "registry.throttling.RequestPasswordResetThrottle",
        "registry.throttling.OperatorRequestThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "owner": "120/min",
        "anon": "60/min",
        "owner-signup": "20/hour",
        "resend-verification": "3/hour",
        "request-password-reset": "5/hour",
        "operator-request": "3/day",
    },
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Mesh Things API",
    "VERSION": "1.0.0",
    "SERVERS": [{"url": public_base_url()}],
    # The catalog default and the per-device override share one choice set, so
    # they share one enum component rather than generating a near-duplicate each.
    "ENUM_NAME_OVERRIDES": {
        "DetectorEnum": "common.detectors.DETECTOR_CHOICES",
        "OperatorRequestStatusEnum": "registry.models.OperatorRequestStatus",
        "DataDeletionStatusEnum": "registry.models.DataDeletionStatus",
        "BackfillStatusEnum": "registry.models.BackfillStatus",
        "BackfillResultStatusEnum": [("done", "done"), ("failed", "failed")],
    },
}

# CORS: no origins allowed by default.
# Set a comma-separated allowlist in production
# if this API is ever called from a browser
CORS_ALLOWED_ORIGINS = env_list(f"{ENV_PREFIX}__CORS_ORIGINS")
if CORS_ALLOWED_ORIGINS:
    INSTALLED_APPS.insert(0, "corsheaders")
    MIDDLEWARE.insert(0, "corsheaders.middleware.CorsMiddleware")
    # A browser client requires Allow-Credentials whenever it sends requests
    # with credentials: 'include', which now applies to readings too since it
    # recognizes registry's session cookie (SessionAuthentication above).
    CORS_ALLOW_CREDENTIALS = True
    if not IS_READINGS:
        # readings has no CsrfViewMiddleware (its endpoints are read-only, so
        # CSRF enforcement never triggers). This only matters for registry.
        CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# Only registry sets cookies (login, CSRF)
# Needed whenever the frontend and API live on different subdomains of the
# same site
COOKIE_DOMAIN = env_str(f"{ENV_PREFIX}__COOKIE_DOMAIN") or None
if COOKIE_DOMAIN:
    SESSION_COOKIE_DOMAIN = COOKIE_DOMAIN
    CSRF_COOKIE_DOMAIN = COOKIE_DOMAIN

# Prefix under PUBLIC_FRONTEND_URL of the frontend's authenticated pages (meshes, devices, ...).
FRONTEND_CONSOLE_PATH = env_str("REGISTRY__FRONTEND_CONSOLE_PATH", "/console")

# Remote brokers and topic filters a source may not use. Brokers are host or host:port
# patterns (`*` wildcards); topics must match exactly. An empty topic list still blocks `#`.
SOURCES_BLOCKED_BROKERS = env_list("REGISTRY__SOURCES_BLOCKED_BROKERS")
SOURCES_BLOCKED_TOPICS = env_list("REGISTRY__SOURCES_BLOCKED_TOPICS", ["#"])
# Loopback, link-local and bare hostnames are always refused. Private network addresses
# are too unless this is set, e.g. for a self-hosted instance bridging a broker on its LAN.
SOURCES_ALLOW_PRIVATE_BROKERS = env_bool("REGISTRY__SOURCES_ALLOW_PRIVATE_BROKERS", False)

# Off for an instance run by its own mesh owner, where there is no second party to
# accept terms from. Turns off terms routes, recording, renewals, lapses and retention.
TERMS_ENFORCED = env_bool("REGISTRY__TERMS_ENFORCED", True)

# Blank keeps data indefinitely. When set, a terms acceptance (platform or source) lapses
# after this long unless renewed, which pauses ingestion and schedules its readings for deletion.
_retention_days = env_str("REGISTRY__DATA_RETENTION_DAYS")
DATA_RETENTION_DAYS = int(_retention_days) if _retention_days else None
# Data scheduled for deletion stays in place this long, so it can be exported or restored.
DATA_DELETION_GRACE_DAYS = env_int("REGISTRY__DATA_DELETION_GRACE_DAYS", 30)
TERMS_RENEWAL_NOTICE_DAYS = env_int("REGISTRY__TERMS_RENEWAL_NOTICE_DAYS", 30)
DATA_LIFECYCLE_INTERVAL_SECONDS = env_int("REGISTRY__DATA_LIFECYCLE_INTERVAL_SECONDS", 3600)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
