"""Parse one YouTube video id from a URL the analyst submitted.

Playlist, channel, search, and home pages are rejected. A watch URL that also
carries a list parameter is still one video.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_VIDEO_ID = re.compile(r"^[\w-]{11}$")


class InvalidYouTubeTarget(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _host(hostname: str) -> str:
    return hostname.lower().removeprefix("www.").removeprefix("m.").removeprefix("mobile.")


def video_id_from_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise InvalidYouTubeTarget("video_url", "Provide an http or https YouTube video URL.")
    host = _host(parsed.hostname)
    if host == "youtu.be":
        piece = next((part for part in parsed.path.split("/") if part), "")
        if _VIDEO_ID.fullmatch(piece):
            return piece
        raise InvalidYouTubeTarget("video_url", "A youtu.be link must contain one 11-character video id.")
    if host not in {"youtube.com", "youtube-nocookie.com"}:
        raise InvalidYouTubeTarget("video_url", "The URL is not a YouTube video.")
    path = parsed.path.rstrip("/") or "/"
    if path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        if _VIDEO_ID.fullmatch(video_id):
            return video_id
        raise InvalidYouTubeTarget("video_url", "A watch URL must include one 11-character video id.")
    matched = re.fullmatch(r"/(?:embed|shorts)/([\w-]{11})", path)
    if matched:
        return matched.group(1)
    raise InvalidYouTubeTarget(
        "video_url",
        "Only a watch, short, embed, or youtu.be URL can be looked up. Channels, playlists, search, and the home page are rejected.",
    )


def require_video_id(video_id: str | None, video_url: str | None) -> tuple[str, str]:
    if video_id and video_url:
        parsed = video_id_from_url(video_url)
        if parsed != video_id:
            raise InvalidYouTubeTarget("video_id", "video_id does not match video_url.")
        return video_id, video_url
    if video_id:
        if not _VIDEO_ID.fullmatch(video_id):
            raise InvalidYouTubeTarget("video_id", "video_id must be 11 characters.")
        return video_id, f"https://www.youtube.com/watch?v={video_id}"
    if video_url:
        parsed = video_id_from_url(video_url)
        return parsed, video_url
    raise InvalidYouTubeTarget("video_url", "Provide video_url or video_id.")
