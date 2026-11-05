"""One videos.list call. This client does not download a stream or a thumbnail."""

from __future__ import annotations

import httpx

LIST_URL = "https://www.googleapis.com/youtube/v3/videos"
PART = "snippet,contentDetails"


class YouTubeConnectorError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ConnectorNotConfigured(YouTubeConnectorError):
    def __init__(self):
        super().__init__(
            "youtube_connector_not_configured",
            "YouTube context is not configured. Set YOUTUBE_API_KEY on the backend.",
            503,
        )


class YouTubeClient:
    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None):
        self._api_key = api_key
        self._client = httpx.Client(transport=transport, timeout=httpx.Timeout(20.0, connect=5.0))

    def close(self) -> None:
        self._client.close()

    def fetch_video(self, video_id: str) -> dict | None:
        response = self._client.get(
            LIST_URL,
            params={"part": PART, "id": video_id, "key": self._api_key},
        )
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if response.status_code == 200:
            items = body.get("items")
            if not isinstance(items, list) or not items:
                return None
            item = items[0]
            return item if isinstance(item, dict) else None
        reason = _error_reason(body)
        if response.status_code in {400, 403} and reason in {"keyInvalid", "badRequest"}:
            raise YouTubeConnectorError(
                "youtube_api_rejected",
                "YouTube rejected the API key.",
                502,
            )
        raise YouTubeConnectorError(
            "youtube_api_error",
            "YouTube did not return this video.",
            502,
        )


def _error_reason(body: dict) -> str:
    error = body.get("error")
    if not isinstance(error, dict):
        return ""
    errors = error.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        reason = errors[0].get("reason")
        return reason if isinstance(reason, str) else ""
    return ""
