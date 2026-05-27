import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

PROMETHEUS_MULTIPROC_DIR = os.environ.get('PROMETHEUS_MULTIPROC_DIR', str(BASE_DIR / 'prometheus_multiproc_dir'))
os.environ["PROMETHEUS_MULTIPROC_DIR"] = PROMETHEUS_MULTIPROC_DIR
if not os.path.exists(PROMETHEUS_MULTIPROC_DIR):
    os.makedirs(PROMETHEUS_MULTIPROC_DIR, exist_ok=True)


def env_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Environment variable '{name}' is required")
    return value.strip()


def env_bool(name: str) -> bool:
    value = env_required(name).lower()
    if value not in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        raise RuntimeError(f"Environment variable '{name}' must be a boolean value")
    return value in {"1", "true", "yes", "on"}


def env_int(name: str) -> int:
    value = env_required(name)
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable '{name}' must be an integer") from exc


def env_list(name: str) -> list[str]:
    items = [item.strip() for item in env_required(name).split(",") if item.strip()]
    if not items:
        raise RuntimeError(f"Environment variable '{name}' must contain at least one item")
    return items


DEBUG = env_bool("DJANGO_DEBUG")
SECRET_KEY = env_required("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "api",
    "django_prometheus",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "api.middleware.MetricsMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "api.middleware.RequestIDMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "rag_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "rag_project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_required("POSTGRES_DB"),
        "USER": env_required("POSTGRES_USER"),
        "PASSWORD": env_required("POSTGRES_PASSWORD"),
        "HOST": env_required("POSTGRES_HOST"),
        "PORT": env_required("POSTGRES_PORT"),
        "CONN_MAX_AGE": env_int("POSTGRES_CONN_MAX_AGE"),
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS")
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
if CORS_ALLOW_ALL_ORIGINS and CORS_ALLOW_CREDENTIALS:
    raise RuntimeError("CORS_ALLOW_ALL_ORIGINS=true is not allowed with credentialed requests")
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-client-version",
    "x-requested-with",
    "x-request-id",
]

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT")
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS")
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": False,
        }
    }
}

RATELIMIT_USE_CACHE = "default"
RATELIMIT_FAIL_OPEN = False

RATELIMIT_DEFAULT = env_required("RATELIMIT_DEFAULT")
AUTH_REGISTER_RATELIMIT = env_required("AUTH_REGISTER_RATELIMIT")
AUTH_LOGIN_RATELIMIT = env_required("AUTH_LOGIN_RATELIMIT")
AUTH_REFRESH_RATELIMIT = env_required("AUTH_REFRESH_RATELIMIT")
RATELIMIT_VIEW = "api.error_views.ratelimited_error"
MAX_QUESTION_LENGTH = env_int("MAX_QUESTION_LENGTH")
OLLAMA_HEALTHCHECK_URL = env_required("OLLAMA_HEALTHCHECK_URL")
RAG_READY_TIMEOUT_MS = env_int("RAG_READY_TIMEOUT_MS")

DJANGO_LOG_LEVEL = env_required("DJANGO_LOG_LEVEL")
API_LOG_LEVEL = env_required("API_LOG_LEVEL")

try:
    import pythonjsonlogger
    formatter_class = "pythonjsonlogger.jsonlogger.JsonFormatter"
except ImportError:
    formatter_class = "logging.Formatter"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "()": formatter_class,
            "format": "%(asctime)s %(levelname)s %(name)s %(request_id)s %(latency)s %(provider)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "filters": {
        "request_context": {
            "()": "api.logging_filters.RequestContextFilter",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": DJANGO_LOG_LEVEL,
        "filters": ["request_context"],
    },
    "loggers": {
        "api": {
            "handlers": ["console"],
            "level": API_LOG_LEVEL,
            "propagate": False,
            "filters": ["request_context"],
        },
        "django": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
            "filters": ["request_context"],
        },
    },
}
