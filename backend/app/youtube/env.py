"""Read the YouTube API key. The key is never logged or returned."""

import os

KEY_ENV = "YOUTUBE_API_KEY"


def youtube_api_key() -> str | None:
    from app.x import env as xenv

    xenv.load_backend_env()
    value = os.environ.get(KEY_ENV, "").strip()
    return value or None
