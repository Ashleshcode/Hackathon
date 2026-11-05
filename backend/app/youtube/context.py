"""Build the stored context for one video. Metadata never becomes a detector score."""

from __future__ import annotations

import hashlib
import json

from app.database.connection import session, utc_now
from app.youtube.client import YouTubeClient, YouTubeConnectorError
from app.youtube.env import youtube_api_key
from app.youtube.ids import require_video_id

METADATA_FIELDS = (
    ("title", "title"),
    ("channel_title", "channelTitle"),
    ("channel_id", "channelId"),
    ("published_at", "publishedAt"),
    ("description", "description"),
)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def metadata_from_item(item: dict) -> dict:
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    details = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
    metadata = {name: _text(snippet.get(source)) for name, source in METADATA_FIELDS}
    metadata["duration"] = _text(details.get("duration"))
    return metadata


def _context_id(video_id: str) -> str:
    digest = hashlib.sha256(video_id.encode("utf-8")).hexdigest()[:12]
    return f"yt_{digest}"


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _response(video_id: str, video_url: str | None, metadata: dict | None, context_id: str | None) -> dict:
    watch = _watch_url(video_id)
    return {
        "context_id": context_id,
        "implementation_status": "not_verified",
        "video_id": video_id,
        "metadata": metadata,
        "audiovisual_analysis": "not_performed",
        "audiovisual_analysis_reason": "YouTube audiovisual content is not downloaded or analysed.",
        "external_references": {
            "platform": "x",
            "query": f'url:"{watch}"',
            "implementation_status": "not_implemented",
            "posts": [],
        },
        "warnings": [
            "The channel listing is public metadata. It does not change the face-score result.",
            "This request does not include a verification badge or a Hotstar rating.",
        ],
    }


def _store(video_id: str, video_url: str, metadata: dict) -> str:
    context_id = _context_id(video_id)
    payload = json.dumps(metadata, ensure_ascii=False)
    now = utc_now()
    with session() as connection:
        connection.execute(
            """
            INSERT INTO youtube_contexts (
                context_id, video_id, video_url, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                video_url = excluded.video_url,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (context_id, video_id, video_url, payload, now, now),
        )
    return context_id


def lookup_context(body: dict, *, client: YouTubeClient | None = None) -> dict:
    if not isinstance(body, dict):
        from app.youtube.ids import InvalidYouTubeTarget

        raise InvalidYouTubeTarget("video_url", "Provide a JSON object with video_url or video_id.")
    video_id, video_url = require_video_id(body.get("video_id"), body.get("video_url"))
    owns_client = client is None
    if client is None:
        key = youtube_api_key()
        if not key:
            from app.youtube.client import ConnectorNotConfigured

            raise ConnectorNotConfigured()
        client = YouTubeClient(key)
    try:
        item = client.fetch_video(video_id)
    finally:
        if owns_client:
            client.close()
    if item is None:
        raise YouTubeConnectorError("youtube_video_not_found", f"YouTube has no video {video_id}.", 404)
    metadata = metadata_from_item(item)
    context_id = _store(video_id, video_url, metadata)
    return _response(video_id, video_url, metadata, context_id)
