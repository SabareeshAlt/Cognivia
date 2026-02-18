from functools import wraps

from django.contrib.auth import get_user_model
try:
    from rest_framework_simplejwt.tokens import AccessToken
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    SIMPLEJWT_AVAILABLE = True
except Exception:  # pragma: no cover
    AccessToken = None
    InvalidToken = Exception
    TokenError = Exception
    SIMPLEJWT_AVAILABLE = False


from .responses import json_error

User = get_user_model()


def get_bearer_token(request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip()


def get_user_from_request(request):
    if not SIMPLEJWT_AVAILABLE:
        return None

    token = get_bearer_token(request)
    if not token:
        return None

    try:
        access = AccessToken(token)
        user_id = access.get("user_id")
        if not user_id:
            return None
        return User.objects.filter(id=user_id).first()
    except (InvalidToken, TokenError, ValueError):
        return None


def jwt_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not SIMPLEJWT_AVAILABLE:
            return json_error(
                request,
                "Authentication backend not available. Install djangorestframework-simplejwt.",
                503,
            )

        user = get_user_from_request(request)
        if user is None:
            return json_error(request, "Authentication required", 401)

        request.user = user
        return view_func(request, *args, **kwargs)

    return _wrapped
