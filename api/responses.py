from django.http import JsonResponse


def json_error(request, message: str, status: int, extra: dict | None = None) -> JsonResponse:
    payload = {"error": message, "success": False, "trace_id": getattr(request, "request_id", "-")}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)
