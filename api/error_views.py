from django.http import JsonResponse


def ratelimited_error(request, exception):
    request_id = getattr(request, "request_id", "-")
    return JsonResponse(
        {
            "success": False,
            "error": "Rate limit exceeded. Please retry shortly.",
            "trace_id": request_id,
        },
        status=429,
    )
