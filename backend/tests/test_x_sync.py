"""X recent-search sync. HTTP is mocked, so these tests do not call api.x.com."""

import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_database_path, initialize_database
from app.intelligence import campaign_store
from app.intelligence.graph_engine import build_graph
from app.intelligence.post_ingestion import Post
from app.main import app
from app.x.client import XClient

TOKEN = "test-token"
VARIANT_URL = "https://video.example.test/secret-clip.mp4"
BASE = datetime(2026, 11, 5, 10, tzinfo=timezone.utc)


def _post(post_id, account, minutes=0, **fields):
    return Post(
        post_id=post_id,
        platform="platform_a",
        account_id=account,
        timestamp=BASE + timedelta(minutes=minutes),
        **fields,
    )


def _campaign_id():
    posts = [
        _post("p1", "alpha", text="shared caption about the reservoir report", media_hash="abc123"),
        _post("p2", "beta", minutes=4, text="shared caption about the reservoir report", media_hash="abc123"),
    ]
    graph = build_graph(posts)
    summary = {
        "total_records": 2,
        "accepted": 2,
        "rejected": 0,
        "errors": [],
        "platforms": {"platform_a": 2},
    }
    graph["provenance"] = "synthetic_demo_data"
    graph["import_summary"] = summary
    campaign = {
        "status": "completed",
        "provenance": "synthetic_demo_data",
        "source_file": "synthetic_demo_data.csv",
        "import_summary": summary,
        "posts": [post.to_dict() for post in posts],
    }
    return campaign_store.save_campaign(campaign, graph)


def _tweet(post_id, author_id="42", text="A public post", **extra):
    tweet = {
        "id": post_id,
        "text": text,
        "author_id": author_id,
        "created_at": "2026-11-05T09:00:00.000Z",
        "conversation_id": "100",
        "public_metrics": {"like_count": 3, "repost_count": 1},
    }
    tweet.update(extra)
    return tweet


def _payload(tweets, users=None, media=None, included_tweets=None, next_token=None):
    body = {
        "data": tweets,
        "includes": {
            "users": users if users is not None else [{"id": "42", "name": "Ada", "username": "ada"}],
            "media": media or [],
            "tweets": included_tweets or [],
        },
        "meta": {"result_count": len(tweets)},
    }
    if next_token:
        body["meta"]["next_token"] = next_token
    return body


def _user(author_id="42", username="ada", name="Ada", **extra):
    user = {"id": author_id, "username": username, "name": name}
    user.update(extra)
    return user


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(
        "app.models.deepfake_detector.get_shared_detector",
        lambda: SimpleNamespace(device="cpu", model_name="test-detector"),
    )
    with TestClient(app) as client:
        yield client


def _install(monkeypatch, handler):
    monkeypatch.setenv("X_BEARER_TOKEN", TOKEN)
    monkeypatch.setattr("app.x.client.RETRY_DELAY_SECONDS", 0)

    def build():
        return XClient(TOKEN, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("app.x.sync.build_client", build)


def _sync(api, campaign_id, handler, monkeypatch, **body):
    _install(monkeypatch, handler)
    payload = {"max_results": 10, "max_pages": 1, "query": "cats"}
    payload.update(body)
    return api.post(f"/api/campaigns/{campaign_id}/sync/x", json=payload)


def _rows(sql, params=()):
    connection = sqlite3.connect(get_database_path())
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def _graph(campaign_id):
    return (
        _rows(
            """
            SELECT node_id, account_id, platform, post_count
            FROM accounts WHERE campaign_id = ? ORDER BY position
            """,
            (campaign_id,),
        ),
        _rows(
            """
            SELECT edge_id, source_node, target_node, signals_json
            FROM graph_edges WHERE campaign_id = ? ORDER BY position
            """,
            (campaign_id,),
        ),
    )


def test_missing_bearer_token_does_not_call_x(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        raise AssertionError("X was called without a token")

    _install(monkeypatch, handler)
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    response = api.post(f"/api/campaigns/{campaign_id}/sync/x", json={"query": "cats"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "x_connector_not_configured"
    assert TOKEN not in response.text
    assert _rows("SELECT COUNT(*) FROM x_sync_runs")[0][0] == 0


def test_successful_search_stores_metadata(api, monkeypatch):
    campaign_id = _campaign_id()
    before = _graph(campaign_id)

    def handler(request):
        assert request.url.host == "api.x.com"
        assert request.url.path == "/2/tweets/search/recent"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)
        assert request.url.params["tweet.fields"]
        assert "attachments.media_keys" in request.url.params["expansions"]
        assert "variants" in request.url.params["media.fields"]
        return httpx.Response(200, json=_payload([_tweet("900", text="Observed text")]))

    response = _sync(api, campaign_id, handler, monkeypatch)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["complete"] is True
    assert body["search_window"] == "preceding_seven_days"
    assert body["posts_fetched"] == 1
    assert body["posts_inserted"] == 1
    assert body["posts_already_known"] == 0
    assert body["analysis"] == "not_performed"
    assert body["coordination_graph"] == "unchanged"
    assert TOKEN not in response.text
    stored = api.get(f"/api/campaigns/{campaign_id}/x").json()
    assert stored["posts"][0]["text"] == "Observed text"
    assert stored["posts"][0]["created_at"] == "2026-11-05T09:00:00.000Z"
    assert stored["posts"][0]["author"]["username"] == "ada"
    assert stored["posts"][0]["public_metrics"]["like_count"] == 3
    assert stored["posts"][0]["provenance"]["implementation_status"] == "not_verified"
    assert _graph(campaign_id) == before
    assert _rows("SELECT COUNT(*) FROM analysis_jobs")[0][0] == 0
    campaign = api.get(f"/api/campaigns/{campaign_id}").json()
    assert campaign["status"] == "completed"
    assert campaign["provenance"] == "synthetic_demo_data"


def test_empty_search_is_complete_and_inserts_nothing(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        return httpx.Response(200, json={"meta": {"result_count": 0}})

    body = _sync(api, campaign_id, handler, monkeypatch).json()
    assert body["complete"] is True
    assert body["posts_fetched"] == 0
    assert body["posts_inserted"] == 0
    assert _rows("SELECT COUNT(*) FROM posts WHERE platform = 'x'")[0][0] == 0


def test_multiple_pages_follow_the_official_token(api, monkeypatch):
    campaign_id = _campaign_id()
    calls = []

    def handler(request):
        calls.append(request.url.params.get("next_token"))
        if len(calls) == 1:
            return httpx.Response(200, json=_payload([_tweet("1")], next_token="page-2"))
        return httpx.Response(200, json=_payload([_tweet("2", text="Second")]))

    response = _sync(api, campaign_id, handler, monkeypatch, max_pages=3)
    assert response.status_code == 200
    body = response.json()
    assert calls == [None, "page-2"]
    assert body["pages_retrieved"] == 2
    assert body["posts_fetched"] == 2
    assert body["complete"] is True
    assert body["more_pages_available"] is False
    assert body["stopped_by_limit"] is False


def test_pagination_limit_is_not_reported_as_complete(api, monkeypatch):
    campaign_id = _campaign_id()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=_payload([_tweet("1")], next_token="more"))

    body = _sync(api, campaign_id, handler, monkeypatch, max_pages=1).json()
    assert calls == [1]
    assert body["status"] == "partial"
    assert body["complete"] is False
    assert body["stopped_by_limit"] is True
    assert body["more_pages_available"] is True
    assert body["pages_retrieved"] == 1
    assert body["posts_inserted"] == 1


def test_duplicate_posts_and_repeated_sync_do_not_duplicate_rows(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        return httpx.Response(200, json=_payload([_tweet("900")]))

    first = _sync(api, campaign_id, handler, monkeypatch).json()
    second = _sync(api, campaign_id, handler, monkeypatch, query=None).json()
    assert first["posts_inserted"] == 1
    assert second["posts_inserted"] == 0
    assert second["posts_already_known"] == 1
    assert second["query"] == "cats"
    assert _rows("SELECT COUNT(*) FROM posts WHERE platform = 'x'")[0][0] == 1
    assert _rows("SELECT COUNT(*) FROM x_sync_runs WHERE status = 'completed'")[0][0] == 2


def test_duplicate_accounts_are_updated_in_place(api, monkeypatch):
    campaign_id = _campaign_id()
    state = {"pass": 0}

    def handler(_request):
        state["pass"] += 1
        name = "Ada" if state["pass"] == 1 else "Ada Lovelace"
        return httpx.Response(
            200,
            json=_payload(
                [_tweet("1", text="One"), _tweet("2", text="Two")],
                users=[_user(name=name)],
            ),
        )

    first = _sync(api, campaign_id, handler, monkeypatch).json()
    second = _sync(api, campaign_id, handler, monkeypatch).json()
    assert first["accounts_inserted"] == 1
    assert first["posts_inserted"] == 2
    assert second["accounts_inserted"] == 0
    assert second["accounts_updated"] == 1
    assert _rows("SELECT COUNT(*) FROM x_accounts")[0][0] == 1
    assert _rows("SELECT display_name FROM x_accounts")[0][0] == "Ada Lovelace"


def test_post_without_media_stores_no_media_row(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        return httpx.Response(200, json=_payload([_tweet("900")]))

    body = _sync(api, campaign_id, handler, monkeypatch).json()
    assert body["media_references"] == 0
    assert body["media"] == []
    assert _rows("SELECT COUNT(*) FROM x_media")[0][0] == 0


def test_media_metadata_is_stored_without_download_or_analysis(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(request):
        assert request.url.host == "api.x.com"
        return httpx.Response(
            200,
            json=_payload(
                [_tweet("900", attachments={"media_keys": ["13_900"]})],
                media=[
                    {
                        "media_key": "13_900",
                        "type": "video",
                        "duration_ms": 1000,
                        "width": 320,
                        "height": 240,
                        "preview_image_url": "https://img.example.test/preview.jpg",
                        "variants": [{"bit_rate": 320000, "content_type": "video/mp4", "url": VARIANT_URL}],
                    }
                ],
            ),
        )

    response = _sync(api, campaign_id, handler, monkeypatch)
    assert VARIANT_URL not in response.text
    body = response.json()
    assert body["media"] == [
        {
            "post_id": "900",
            "media_key": "13_900",
            "type": "video",
            "variant_access": "present",
            "analysed": False,
        }
    ]
    stored = _rows("SELECT variants_json FROM x_media")
    assert VARIANT_URL in stored[0][0]
    view = api.get(f"/api/campaigns/{campaign_id}/x")
    assert VARIANT_URL not in view.text
    assert view.json()["posts"][0]["media"][0]["analysed"] is False
    assert _rows("SELECT COUNT(*) FROM analysis_jobs")[0][0] == 0
    assert _rows("SELECT COUNT(*) FROM media_assets WHERE storage_name IS NOT NULL")[0][0] == 0


def test_relationship_types_stay_out_of_the_coordination_graph(api, monkeypatch):
    campaign_id = _campaign_id()
    before = _graph(campaign_id)

    def handler(_request):
        return httpx.Response(
            200,
            json=_payload(
                [
                    _tweet("10", referenced_tweets=[{"type": "retweeted", "id": "1"}, {"type": "liked", "id": "8"}]),
                    _tweet("11", text="Quote", referenced_tweets=[{"type": "quoted", "id": "2"}]),
                    _tweet("12", text="Reply", referenced_tweets=[{"type": "replied_to", "id": "3"}]),
                ],
                included_tweets=[_tweet("1", text="Original"), _tweet("2", text="Quoted source")],
            ),
        )

    body = _sync(api, campaign_id, handler, monkeypatch).json()
    kinds = {(item["type"], item["source_post_id"], item["referencing_post_id"]) for item in body["relationships"]}
    assert kinds == {
        ("reposted", "1", "10"),
        ("quoted", "2", "11"),
        ("replied_to", "3", "12"),
    }
    assert body["referenced_posts_resolved"] == 2
    assert body["referenced_posts_unresolved"] == 1
    assert _graph(campaign_id) == before
    resolved = {
        row[0]
        for row in _rows("SELECT post_id FROM posts WHERE platform = 'x' AND text IS NOT NULL")
    }
    assert "3" not in resolved
    assert "Original" in {row[0] for row in _rows("SELECT text FROM posts WHERE post_id = '1'")}


def test_unresolved_reference_does_not_invent_a_post(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        return httpx.Response(
            200,
            json=_payload([_tweet("10", referenced_tweets=[{"type": "quoted", "id": "404"}])]),
        )

    body = _sync(api, campaign_id, handler, monkeypatch).json()
    assert body["referenced_posts_unresolved"] == 1
    assert _rows("SELECT COUNT(*) FROM posts WHERE post_id = '404'")[0][0] == 0
    relationship = _rows(
        "SELECT source_post_id, referencing_post_id, relationship_type, referenced_resolved FROM post_relationships"
    )[0]
    assert relationship == ("404", "10", "quoted", 0)


def test_rate_limit_does_not_persist_posts(api, monkeypatch):
    campaign_id = _campaign_id()
    calls = []

    def handler(_request):
        calls.append(1)
        return httpx.Response(
            429,
            headers={"x-rate-limit-remaining": "0", "x-rate-limit-reset": "1700000000"},
            json={"title": "Too Many Requests"},
        )

    response = _sync(api, campaign_id, handler, monkeypatch)
    assert calls == [1]
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "x_rate_limited"
    assert response.json()["detail"]["retry_after"] == "1700000000"
    assert response.json()["detail"]["complete"] is False
    assert _rows("SELECT COUNT(*) FROM posts WHERE platform = 'x'")[0][0] == 0
    assert _rows("SELECT status FROM x_sync_runs") == [("failed",)]


def test_authentication_failure(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        return httpx.Response(401, json={"title": "Unauthorized", "detail": f"Bearer {TOKEN} rejected"})

    response = _sync(api, campaign_id, handler, monkeypatch)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "x_authentication_failed"
    assert TOKEN not in response.text
    assert _rows("SELECT COUNT(*) FROM posts WHERE platform = 'x'")[0][0] == 0


def test_permission_and_credit_failures(api, monkeypatch):
    campaign_id = _campaign_id()
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(403, json={"title": "Forbidden", "detail": "Client Forbidden"})
        return httpx.Response(402, json={"title": "CreditsDepleted", "detail": "Credits depleted"})

    denied = _sync(api, campaign_id, handler, monkeypatch)
    credits = _sync(api, campaign_id, handler, monkeypatch)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "x_permission_denied"
    assert credits.status_code == 402
    assert credits.json()["detail"]["code"] == "x_credits_exhausted"
    assert calls["n"] == 2
    assert _rows("SELECT COUNT(*) FROM posts WHERE platform = 'x'")[0][0] == 0


def test_transient_network_error_is_retried(api, monkeypatch):
    campaign_id = _campaign_id()
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("temporary outage")
        return httpx.Response(200, json=_payload([_tweet("900")]))

    response = _sync(api, campaign_id, handler, monkeypatch)
    assert response.status_code == 200
    assert calls["n"] == 2
    assert response.json()["posts_inserted"] == 1


def test_database_transaction_failure_rolls_back(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        return httpx.Response(200, json=_payload([_tweet("900")]))

    def fail(connection, campaign, status, summary):
        raise sqlite3.OperationalError("disk I/O error")

    _install(monkeypatch, handler)
    monkeypatch.setattr("app.database.repository._record_x_sync", fail)
    response = api.post(
        f"/api/campaigns/{campaign_id}/sync/x",
        json={"query": "cats", "max_results": 10, "max_pages": 1},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "The X sync could not be saved."
    assert "disk I/O" not in response.text
    assert _rows("SELECT COUNT(*) FROM posts WHERE platform = 'x'")[0][0] == 0
    assert _rows("SELECT COUNT(*) FROM x_accounts")[0][0] == 0
    assert _rows("SELECT COUNT(*) FROM post_relationships")[0][0] == 0
    statuses = [row[0] for row in _rows("SELECT status FROM x_sync_runs")]
    assert "completed" not in statuses
    assert "partial" not in statuses


def test_ingested_rows_survive_restart(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        return httpx.Response(200, json=_payload([_tweet("900", text="Still here")]))

    created = _sync(api, campaign_id, handler, monkeypatch)
    assert created.status_code == 200
    initialize_database()
    with TestClient(app) as restarted:
        fetched = restarted.get(f"/api/campaigns/{campaign_id}/x")
    assert fetched.status_code == 200
    assert fetched.json()["posts"][0]["text"] == "Still here"
    assert fetched.json()["latest_sync"]["posts_inserted"] == 1


def test_older_than_seven_days_is_rejected_before_the_request(api, monkeypatch):
    campaign_id = _campaign_id()

    def handler(_request):
        raise AssertionError("recent search was called for an old start_time")

    response = _sync(
        api,
        campaign_id,
        handler,
        monkeypatch,
        start_time="2020-01-01T00:00:00Z",
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "outside_recent_search_window"


def test_existing_tables_gain_x_tables_without_dropping_rows(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE campaigns (
            campaign_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            provenance TEXT NOT NULL,
            source_file TEXT,
            parent_campaign_id TEXT,
            extension_post_json TEXT,
            import_summary_json TEXT NOT NULL,
            algorithm_json TEXT,
            limitations_json TEXT,
            clusters_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO campaigns VALUES ('C1','completed','synthetic_demo_data',NULL,NULL,NULL,'{}',NULL,'[]','[]','2026-11-05T00:00:00.000000Z')"
    )
    connection.commit()
    connection.close()
    initialize_database(path)
    connection = sqlite3.connect(path)
    try:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        provenance = connection.execute("SELECT provenance FROM campaigns").fetchone()[0]
    finally:
        connection.close()
    assert "post_relationships" in names
    assert "x_media" in names
    assert provenance == "synthetic_demo_data"
