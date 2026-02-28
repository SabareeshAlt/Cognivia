import uuid
import time

from .request_context import request_id_ctx_var
from .metrics import inc_counter, observe_histogram


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx_var.set(request_id)
        request.request_id = request_id

        response = self.get_response(request)
        response["X-Request-ID"] = request_id

        request_id_ctx_var.reset(token)
        return response


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.monotonic()
        response = self.get_response(request)
        elapsed = time.monotonic() - started
        path = request.path
        method = request.method
        status = str(response.status_code)
        labels = {"method": method, "path": path, "status": status}
        inc_counter("academerag_http_requests_total", labels=labels, value=1)
        observe_histogram("academerag_http_request_duration_seconds", elapsed, labels=labels)
        return response
