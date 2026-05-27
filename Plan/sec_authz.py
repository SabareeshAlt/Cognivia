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
            
        if not getattr(user, "is_active", False):
            return json_error(request, "User account is disabled", 403)

        request.user = user
        return view_func(request, *args, **kwargs)

    return _wrapped

@require_http_methods(["GET"])
@jwt_required
@ratelimit(key="ip", rate="30/m", block=True)
def retrieval_diagnostics(request):
    user = getattr(request, "user", None)
    # Ensure deny-by-default and tighten to superuser only
    if not user or not getattr(user, "is_superuser", False):
        return json_error(request, "Admin access required", 403)
    try:
        _load_rag_modules()
        return JsonResponse(
            {
                "success": True,
                "trace_id": getattr(request, "request_id", "-"),
                "diagnostics": _diagnostics_fn(),
            }
        )
    except Exception as exc:
        return json_error(request, f"Diagnostics unavailable: {exc}", 500)
