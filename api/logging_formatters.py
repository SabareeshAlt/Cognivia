import logging


class SafeRequestFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return super().format(record)
