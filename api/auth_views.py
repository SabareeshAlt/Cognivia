import json
import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
try:
    from rest_framework_simplejwt.tokens import RefreshToken
    SIMPLEJWT_AVAILABLE = True
except Exception:  # pragma: no cover
    RefreshToken = None
    SIMPLEJWT_AVAILABLE = False

from .auth_utils import jwt_required
from .rate_limit import ratelimit
from .responses import json_error

User = get_user_model()
logger = logging.getLogger(__name__)


def _issue_tokens(user):
    if not SIMPLEJWT_AVAILABLE:
        raise RuntimeError("djangorestframework-simplejwt is not installed")
    if not getattr(user, "is_active", False):
        raise ValueError("User account is disabled")
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate=getattr(settings, "AUTH_REGISTER_RATELIMIT", "10/m"), block=True, cache="default")
def register(request):
    if not SIMPLEJWT_AVAILABLE:
        return json_error(request, "Auth dependency missing: djangorestframework-simplejwt", 503)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error(request, "Invalid JSON", 400)

    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()
    name = (data.get("name") or "").strip()

    if not email or not password:
        return json_error(request, "Email and password are required", 400)
    if len(password) < 8:
        return json_error(request, "Password must be at least 8 characters", 400)
    if not any(char.isdigit() for char in password):
        return json_error(request, "Password must contain at least one number", 400)
    if not any(char.isupper() for char in password):
        return json_error(request, "Password must contain at least one uppercase letter", 400)
    if User.objects.filter(username=email).exists():
        return json_error(request, "User already exists", 409)

    user = User.objects.create_user(
        username=email,
        email=email,
        first_name=name,
        password=password,
    )
    tokens = _issue_tokens(user)
    return JsonResponse(
        {
            "success": True,
            "user": {"id": user.id, "email": user.email, "name": user.first_name},
            "tokens": tokens,
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate=getattr(settings, "AUTH_LOGIN_RATELIMIT", "15/m"), block=True, cache="default")
def login(request):
    if not SIMPLEJWT_AVAILABLE:
        return json_error(request, "Auth dependency missing: djangorestframework-simplejwt", 503)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error(request, "Invalid JSON", 400)

    email = (data.get("email") or "").strip().lower()
    password = (data.get("password") or "").strip()

    user = authenticate(request, username=email, password=password)
    if user is None:
        return json_error(request, "Invalid credentials", 401)
    if not getattr(user, "is_active", False):
        return json_error(request, "Account is disabled", 403)

    tokens = _issue_tokens(user)
    return JsonResponse(
        {
            "success": True,
            "user": {"id": user.id, "email": user.email, "name": user.first_name},
            "tokens": tokens,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate=getattr(settings, "AUTH_REFRESH_RATELIMIT", "20/m"), block=True, cache="default")
def refresh(request):
    if not SIMPLEJWT_AVAILABLE:
        return json_error(request, "Auth dependency missing: djangorestframework-simplejwt", 503)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return json_error(request, "Invalid JSON", 400)

    refresh_token = (data.get("refresh") or "").strip()
    if not refresh_token:
        return json_error(request, "Refresh token is required", 400)

    try:
        refresh_obj = RefreshToken(refresh_token)
        user_id = refresh_obj.get("user_id")
        user = User.objects.filter(id=user_id).first()
        if user is None:
            return json_error(request, "Invalid refresh token", 401)
        if not getattr(user, "is_active", False):
            return json_error(request, "Account is disabled", 403)
        new_refresh = RefreshToken.for_user(user)
        # Rotate-safe behavior: invalidate old refresh when blacklist app is enabled.
        try:
            refresh_obj.blacklist()
        except Exception as exc:
            logger.debug("Refresh token blacklist skipped: %s", exc)
        return JsonResponse(
            {
                "success": True,
                "tokens": {
                    "access": str(new_refresh.access_token),
                    "refresh": str(new_refresh),
                },
                "trace_id": getattr(request, "request_id", "-"),
            }
        )
    except Exception:
        return json_error(request, "Invalid refresh token", 401)


@require_http_methods(["GET"])
@jwt_required
def me(request):
    user = request.user
    return JsonResponse(
        {
            "success": True,
            "user": {"id": user.id, "email": user.email, "name": user.first_name},
        }
    )
