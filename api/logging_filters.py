from .request_context import request_id_ctx_var


class RequestContextFilter:
    def filter(self, record):
        record.request_id = request_id_ctx_var.get()
        return True
