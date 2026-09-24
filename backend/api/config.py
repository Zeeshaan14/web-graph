# Central, env-driven configuration. The first piece of this project's
# "config layer" (see PRODUCTION_READINESS.md's P1 item) -- seeded here
# because auth/rate-limiting/concurrency (this module's actual reason for
# existing right now) have nothing to read their settings from
# otherwise. NOT yet a home for every existing hardcoded constant in this
# codebase (REQUEST_DELAY_SECONDS, MAX_RESPONSE_BYTES, CORS origins'
# eventual full migration, ...) -- pulling those in is its own separate,
# larger pass, not bundled into this one.

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # A single shared secret, checked on every route except /health (see
    # api/auth.py). None (the default) means auth is OFF -- local dev via
    # `uv run uvicorn api.main:app --reload` stays exactly as frictionless
    # as it's always been; a deployment sets API_KEY to turn this on.
    # Deliberately not "required with no default": that would break the
    # documented local dev workflow for anyone who hasn't set it, which
    # is worse than an honest, logged-at-startup opt-in.
    api_key: str | None = None

    # Comma-separated, not list[str] -- lets a plain env var set this
    # without needing JSON-array syntax. Parsed in api/main.py.
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Requests per minute, per client IP -- see api/rate_limiting.py.
    rate_limit_per_minute: int = 30

    # How many expensive requests (crawl/extract/detect) run at once,
    # process-wide -- independent of any single request's own
    # concurrency (e.g. /discover-urls's own max_concurrency only bounds
    # fan-out WITHIN that one crawl). See api/concurrency.py.
    max_concurrent_requests: int = 10

    # Root logger level -- see api/logging_config.py. INFO by default:
    # loud enough to see one line per request, quiet enough not to drown
    # in every DEBUG trace line already scattered through crawler.py etc.
    log_level: str = "INFO"

    # Unset (the default) means error tracking is OFF -- api/main.py only
    # calls sentry_sdk.init() when this is present, same
    # off-by-default-until-configured shape as api_key above. Getting a
    # DSN means signing up for Sentry (or a compatible self-hosted
    # instance) -- not something this project can default to having.
    sentry_dsn: str | None = None


settings = Settings()
