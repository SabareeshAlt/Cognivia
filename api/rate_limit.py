try:
    from django_ratelimit.decorators import ratelimit as _ratelimit
except Exception:  # pragma: no cover
    def _ratelimit(*args, **kwargs):
        def _decorator(func):
            def _wrapped(request, *args, **kwargs):
                from django.http import JsonResponse
                import logging
                logging.getLogger(__name__).critical("Rate limiting is disabled or missing. Failing closed.")
                return JsonResponse({"error": "Service Unavailable - Rate Limiter Offline"}, status=503)
            return _wrapped
        return _decorator


ratelimit = _ratelimit
