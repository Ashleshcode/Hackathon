"""Read X connector settings. The bearer token is never logged."""

import os

from app.database.connection import BACKEND_ROOT

TOKEN_ENV = "X_BEARER_TOKEN"


def load_backend_env() -> None:
    """Fill empty process variables from a local .env file.

    Existing process variables win. Values are not printed.
    """
    for path in (BACKEND_ROOT.parent / ".env", BACKEND_ROOT / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


def bearer_token() -> str | None:
    load_backend_env()
    value = os.environ.get(TOKEN_ENV, "").strip()
    return value or None


def _bounded_int(name: str, default: int, low: int, high: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return min(high, max(low, value))


def sync_limits() -> dict[str, int]:
    return {
        "max_pages": _bounded_int("X_SYNC_MAX_PAGES", 5, 1, 10),
        "max_posts": _bounded_int("X_SYNC_MAX_POSTS", 100, 1, 500),
        "page_size": _bounded_int("X_SYNC_PAGE_SIZE", 10, 10, 100),
    }
