try:
    from django_ratelimit.decorators import ratelimit as _ratelimit
except Exception:  # pragma: no cover
    def _ratelimit(*args, **kwargs):
        def _decorator(func):
            return func

        return _decorator


ratelimit = _ratelimit
