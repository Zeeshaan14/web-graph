# JSON-structured logging for the running API -- before this, the only
# logging.basicConfig() call anywhere in this codebase was inside
# url_discovery/crawler.py's `if __name__ == "__main__":` demo block, so
# every logger.warning()/logger.debug() call sprinkled through crawler.py,
# content_extraction.py, pipeline.py etc. (all plain logging.getLogger(__name__)
# calls, propagating to the root logger by default) went nowhere when
# actually running as the API. See PRODUCTION_READINESS.md's
# "no observability" item.
#
# JSON, not plain text: a real deployment ships logs to an aggregator
# (CloudWatch, Datadog, whatever) that wants one parseable JSON object per
# line, not a format string it has to regex apart.

import json
import logging

from .config import settings
from .request_context import request_id_var


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload)


def configure_logging() -> None:
    """Called once, at import time, from api/main.py -- before anything
    else in the app has a chance to log (including the API_KEY-unset
    startup warning), so every log line this process ever emits uses the
    same JSON format from the very first one."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
