"""HTTP client for X API v2 recent search.

Recent search only returns public posts from the preceding seven days.
"""

from __future__ import annotations

import time

import httpx

from app.x.env import bearer_token

SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
TWEET_FIELDS = "created_at,author_id,conversation_id,public_metrics,attachments,referenced_tweets"
EXPANSIONS = "author_id,referenced_tweets.id,referenced_tweets.id.author_id,attachments.media_keys"
USER_FIELDS = "username,name,verified,verified_type"
MEDIA_FIELDS = "media_key,type,url,preview_image_url,variants,duration_ms,width,height,alt_text"
RETRY_DELAY_SECONDS = 0.25
MAX_ATTEMPTS = 3


class XConnectorError(Exception):
    def __init__(self, code: str, message: str, status_code: int, retry_after: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


class ConnectorNotConfigured(XConnectorError):
    def __init__(self):
        super().__init__(
            "x_connector_not_configured",
            "X ingestion is not configured. Set X_BEARER_TOKEN on the backend.",
            503,
        )


class XClient:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None):
        self._client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(20.0, connect=5.0),
            headers={"Authorization": f"Bearer {token}"},
        )

    def close(self) -> None:
        self._client.close()

    def search_page(
        self,
        query: str,
        *,
        page_size: int,
        next_token: str | None = None,
        start_time: str | None = None,
    ) -> dict:
        params = {
            "query": query,
            "max_results": str(page_size),
            "tweet.fields": TWEET_FIELDS,
            "expansions": EXPANSIONS,
            "user.fields": USER_FIELDS,
            "media.fields": MEDIA_FIELDS,
        }
        if next_token:
            params["next_token"] = next_token
        if start_time:
            params["start_time"] = start_time
        response = self._get_with_retries(params)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        if response.status_code == 200:
            return body
        raise _error_for_status(response, body)

    def _get_with_retries(self, params: dict) -> httpx.Response:
        last_network_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = self._client.get(SEARCH_URL, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                last_network_error = error
                if attempt + 1 == MAX_ATTEMPTS:
                    break
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            if response.status_code in {500, 502, 503, 504} and attempt + 1 < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            return response
        raise XConnectorError(
            "x_network_error",
            "The X API request failed after retries.",
            502,
        ) from last_network_error


def build_client(transport: httpx.BaseTransport | None = None) -> XClient:
    token = bearer_token()
    if not token:
        raise ConnectorNotConfigured()
    return XClient(token, transport=transport)


def _short_detail(body: dict) -> str:
    detail = body.get("detail") or body.get("title")
    if isinstance(detail, str) and detail.strip():
        text = " ".join(detail.split())
        if "bearer" in text.lower():
            return "The X API rejected the request."
        return text[:300]
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        message = errors[0].get("message") if isinstance(errors[0], dict) else None
        if isinstance(message, str) and message.strip() and "bearer" not in message.lower():
            return " ".join(message.split())[:300]
    return "The X API rejected the request."


def _mentions_credits(body: dict, response: httpx.Response) -> bool:
    blob = " ".join(
        str(body.get(key, "")) for key in ("title", "detail", "type", "reason")
    ).lower()
    errors = body.get("errors")
    if isinstance(errors, list):
        blob += " " + " ".join(str(item) for item in errors).lower()
    blob += " " + response.headers.get("x-access-level", "").lower()
    markers = ("credit", "usage cap", "usagecap", "payment required", "spend")
    return any(marker in blob for marker in markers)


def _error_for_status(response: httpx.Response, body: dict) -> XConnectorError:
    status = response.status_code
    if status == 401:
        return XConnectorError("x_authentication_failed", "X API authentication failed.", 401)
    if status == 429:
        reset = response.headers.get("x-rate-limit-reset") or response.headers.get("retry-after")
        return XConnectorError(
            "x_rate_limited",
            "X API rate limit was reached.",
            429,
            retry_after=reset,
        )
    if status == 402 or (status == 403 and _mentions_credits(body, response)):
        return XConnectorError("x_credits_exhausted", "X API credits are exhausted.", 402)
    if status == 403:
        return XConnectorError("x_permission_denied", "X API access was denied.", 403)
    if 400 <= status < 500:
        return XConnectorError("x_request_rejected", _short_detail(body), 400)
    return XConnectorError("x_server_error", "The X API request failed after retries.", 502)
