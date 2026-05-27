import os

# To be added to rag_project/settings.py

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": False, # Ensure exceptions propagate so rate limits fail closed
        }
    }
}

RATELIMIT_USE_CACHE = "default"
RATELIMIT_FAIL_OPEN = False # Fail closed: reject if Redis is down (or throw 500, which effectively rejects)

# Existing ratelimit settings
RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT")
AUTH_REGISTER_RATELIMIT = os.getenv("AUTH_REGISTER_RATELIMIT")
AUTH_LOGIN_RATELIMIT = os.getenv("AUTH_LOGIN_RATELIMIT")
AUTH_REFRESH_RATELIMIT = os.getenv("AUTH_REFRESH_RATELIMIT")
RATELIMIT_VIEW = "api.error_views.ratelimited_error"
