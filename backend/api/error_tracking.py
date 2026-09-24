# Sentry initialization, pulled out of main.py so it's testable on its
# own without touching the FastAPI app/module-import machinery -- see
# tests/api/test_observability.py's TestSentryInitialization.
#
# Off entirely unless SENTRY_DSN is set (api/config.py) -- same
# off-by-default-until-configured shape as API_KEY. sentry_sdk
# auto-detects and instruments Starlette/FastAPI, and auto-enables its
# logging integration (captures an ERROR-level log call, including
# main.py's unhandled_exception_handler's logger.exception(), as a
# Sentry event) once initialized -- nothing further to wire up here.

import logging

import sentry_sdk

logger = logging.getLogger(__name__)


def init_error_tracking(dsn: str | None) -> None:
    if not dsn:
        return

    sentry_sdk.init(dsn=dsn, send_default_pii=False)
    logger.info("Sentry error tracking enabled.")
