"""YouTube context returns listing fields only and never scores the video."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database.connection import connect
from app.main import app
from app.youtube.client import YouTubeClient
from app.youtube.context import lookup_context
from app.youtube.env import youtube_api_key

VIDEO_ID = "EtEvS__IoMs"
WATCH = f"https://www.youtube.com/watch?v={VIDEO_ID}"


def _item():
    return {
        "id": VIDEO_ID,
        "snippet": {
            "title": "Obsession | 30th October",
            "channelTitle": "JioHotstar",
            "channelId": "UCaaaaaaaaaaaa",
            "publishedAt": "2026-10-20T00:00:00Z",
            "description": "A trailer.",
            "thumbnails": {"high": {"url": "https://i.ytimg.example/a.jpg"}},
        },
        "contentDetails": {"duration": "PT1M45S", "definition": "hd"},
        "statistics": {"viewCount": "10"},
    }


def _transport(handler):
    return httpx.MockTransport(handler)


def test_missing_key_is_not_configured(monkeypatch):
    monkeypatch.setattr("app.youtube.context.youtube_api_key", lambda: None)
    client = TestClient(app)
    response = client.post("/api/youtube/context", json={"video_url": WATCH})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "youtube_connector_not_configured"
    assert "test-key" not in response.text


def test_playlist_channel_and_home_urls_are_rejected():
    client = TestClient(app)
    for url in (
        "https://www.youtube.com/playlist?list=PLaaaaaaaaaaaa",
        "https://www.youtube.com/channel/UCaaaaaaaaaaaa",
        "https://www.youtube.com/",
        "https://www.youtube.com/results?search_query=obsession",
    ):
        response = client.post("/api/youtube/context", json={"video_url": url})
        assert response.status_code == 422
        assert response.json()["detail"]["field"] == "video_url"


def test_watch_short_embed_and_short_link_parse():
    from app.youtube.ids import video_id_from_url

    assert video_id_from_url(WATCH) == VIDEO_ID
    assert video_id_from_url(f"https://youtu.be/{VIDEO_ID}?t=13") == VIDEO_ID
    assert video_id_from_url(f"https://www.youtube.com/shorts/{VIDEO_ID}") == VIDEO_ID
    assert video_id_from_url(f"https://www.youtube.com/embed/{VIDEO_ID}") == VIDEO_ID


def test_listing_fields_are_stored_and_scores_are_absent():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "www.googleapis.com"
        assert request.url.path == "/youtube/v3/videos"
        assert request.url.params["id"] == VIDEO_ID
        assert request.url.params["part"] == "snippet,contentDetails"
        assert request.url.params["key"] == "test-key"
        return httpx.Response(200, json={"items": [_item()]})

    youtube = YouTubeClient("test-key", transport=_transport(handler))
    result = lookup_context({"video_url": f"https://youtu.be/{VIDEO_ID}?t=13"}, client=youtube)
    assert result["video_id"] == VIDEO_ID
    assert result["implementation_status"] == "not_verified"
    assert result["audiovisual_analysis"] == "not_performed"
    assert result["external_references"]["implementation_status"] == "not_implemented"
    assert result["external_references"]["posts"] == []
    assert result["metadata"] == {
        "title": "Obsession | 30th October",
        "channel_title": "JioHotstar",
        "channel_id": "UCaaaaaaaaaaaa",
        "published_at": "2026-10-20T00:00:00Z",
        "description": "A trailer.",
        "duration": "PT1M45S",
    }
    assert "prediction" not in result
    assert "fake_score" not in result
    assert "thumbnails" not in result["metadata"]
    stored = connect().execute("SELECT context_id, metadata_json FROM youtube_contexts").fetchone()
    assert stored["context_id"] == result["context_id"]
    assert json.loads(stored["metadata_json"])["channel_title"] == "JioHotstar"


def test_a_missing_video_does_not_invent_metadata():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    youtube = YouTubeClient("test-key", transport=_transport(handler))
    with pytest.raises(Exception) as caught:
        lookup_context({"video_id": VIDEO_ID}, client=youtube)
    assert caught.value.code == "youtube_video_not_found"
    assert connect().execute("SELECT COUNT(*) FROM youtube_contexts").fetchone()[0] == 0


def test_the_api_key_is_not_read_from_the_environment_by_this_module_when_unset():
    assert youtube_api_key() is None
