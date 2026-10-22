"""Helpers that read configuration from environment variables (no extra package needed)."""

import os
from urllib.parse import unquote, urlparse


def env_list(name):
    """A comma-separated environment variable as a list, ignoring blanks."""
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def env_bool(name, default=False):
    """True only when the variable is set to "true" (any case); unset uses the default."""
    value = os.environ.get(name)
    return default if value is None else value.strip().lower() == "true"


def parse_database_url(url):
    """Turn `postgres://user:password@host:port/name` into Django's DATABASES entry.

    Fails loudly: a silently wrong database is worse than a crash at startup.
    """
    parsed = urlparse(url or "")
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.path.strip("/"):
        raise ValueError("DATABASE_URL must look like postgres://user:password@host:port/name")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": parsed.port or "",
    }
