import json
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import campaigns
from app.intelligence import graph_engine
from app.intelligence.post_ingestion import MAX_RECORDS, ImportFileError, import_posts

app = FastAPI()
app.include_router(campaigns.router)
client = TestClient(app)

HEADER = "post_id,platform,account_id,timestamp,text\n"


def good(post_id="p1", **overrides):
    return {
        "post_id": post_id,
        "platform": "platform_a",
        "account_id": "a1",
        "timestamp": "2026-11-05T10:00:00Z",
        "text": "Example",
        **overrides,
    }


def test_valid_csv_is_normalised():
    result = import_posts((HEADER + "p1, Platform_A ,a1,2026-11-05T12:00:00+02:00,Hello\n").encode(), "csv")
    post = result.posts[0]
    assert result.errors == []
    assert post.platform == "platform_a"
    assert post.timestamp == datetime(2026, 11, 5, 10, tzinfo=timezone.utc)
    assert post.to_dict()["timestamp"] == "2026-11-05T10:00:00Z"


def test_csv_keeps_good_rows_and_reports_bad_rows_by_line():
    content = HEADER + "p1,platform_a,a1,2026-11-05T10:00:00Z,ok\n" + "p2,platform_a,,2026-11-05T10:00:00Z,bad\n" + "p3,platform_a,a3,yesterday,bad\n"
    result = import_posts(content.encode(), "csv")
    assert [post.post_id for post in result.posts] == ["p1"]
    assert result.errors == [
        {"row": 3, "message": "Missing required field: account_id"},
        {"row": 4, "message": 'Invalid timestamp: "yesterday"'},
    ]
    assert result.summary()["rejected"] == 2


def test_csv_with_byte_order_mark_and_mixed_case_headers():
    content = "﻿Post_ID,Platform,Account_ID,Timestamp\np1,platform_a,a1,2026-11-05T10:00:00Z\n"
    assert len(import_posts(content.encode(), "csv").posts) == 1


def test_csv_row_with_too_many_columns_is_rejected():
    content = HEADER + "p1,platform_a,a1,2026-11-05T10:00:00Z,text,extra\n"
    result = import_posts(content.encode(), "csv")
    assert result.posts == []
    assert "more columns" in result.errors[0]["message"]


def test_csv_missing_required_column_fails_the_file():
    with pytest.raises(ImportFileError, match="account_id"):
        import_posts(b"post_id,platform,timestamp\np1,platform_a,2026-11-05T10:00:00Z\n", "csv")


def test_empty_csv_fails_the_file():
    with pytest.raises(ImportFileError, match="empty"):
        import_posts(b"", "csv")


def test_timestamp_without_timezone_is_rejected():
    result = import_posts(json.dumps([good(timestamp="2026-11-05T10:00:00")]).encode(), "json")
    assert "no timezone" in result.errors[0]["message"]


def test_duplicate_post_id_is_rejected_only_on_the_same_platform():
    records = [good("p1"), good("p1"), good("p1", platform="platform_b")]
    result = import_posts(json.dumps(records).encode(), "json")
    assert len(result.posts) == 2
    assert result.errors == [{"row": 2, "message": "Duplicate post_id on platform_a: p1"}]


def test_json_accepts_list_or_posts_object_and_numeric_ids():
    as_list = import_posts(json.dumps([good(post_id=123, account_id=45)]).encode(), "json")
    assert as_list.posts[0].post_id == "123"
    assert as_list.posts[0].account_id == "45"
    assert len(import_posts(json.dumps({"posts": [good()]}).encode(), "json").posts) == 1


@pytest.mark.parametrize(
    "bad, message",
    [
        ("not an object", "must be a JSON object"),
        (good(account_id=True), "account_id must be text"),
        (good(account_id=["a"]), "account_id must be text"),
        (good(text=5), "text must be text"),
    ],
)
def test_json_bad_records_are_row_errors(bad, message):
    result = import_posts(json.dumps([good(), bad]).encode(), "json")
    assert len(result.posts) == 1
    assert result.errors[0]["row"] == 2
    assert message in result.errors[0]["message"]


@pytest.mark.parametrize("content", [b"{not json", b'{"other": []}', b"42", b"\xff\xfe\xff"])
def test_malformed_json_fails_the_file(content):
    with pytest.raises(ImportFileError):
        import_posts(content, "json")


def test_record_limit():
    records = [good(f"p{i}") for i in range(MAX_RECORDS + 1)]
    with pytest.raises(ImportFileError, match="limit"):
        import_posts(json.dumps(records).encode(), "json")


def upload(content, filename="posts.csv", source_type="synthetic_demo_data", content_type="text/csv"):
    return client.post(
        "/api/campaigns/import",
        files={"file": (filename, content, content_type)},
        data={"source_type": source_type},
    )


def test_import_route_returns_and_stores_campaign_with_provenance():
    response = upload((HEADER + "p1,platform_a,a1,2026-11-05T10:00:00Z,Hi\np2,platform_a,,bad,x\n").encode())
    assert response.status_code == 200
    campaign = response.json()
    assert campaign["provenance"] == "synthetic_demo_data"
    assert campaign["source_file"] == "posts.csv"
    assert campaign["import_summary"]["accepted"] == 1
    assert campaign["import_summary"]["rejected"] == 1

    stored = client.get(f"/api/campaigns/{campaign['campaign_id']}")
    assert stored.json() == campaign
    graph = client.get(f"/api/campaigns/{campaign['campaign_id']}/graph").json()
    assert graph["provenance"] == "synthetic_demo_data"
    assert graph["import_summary"]["accepted"] == 1
    assert graph["algorithm"]["name"]


def test_import_route_with_no_valid_records():
    campaign = upload((HEADER + "p1,platform_a,,bad,x\n").encode()).json()
    assert campaign["status"] == "no_valid_records"
    assert client.get(f"/api/campaigns/{campaign['campaign_id']}/graph").json()["nodes"] == []


def test_import_route_errors_are_readable_strings():
    bad_type = upload(b"x", source_type="made_up")
    assert bad_type.status_code == 400 and "source_type" in bad_type.json()["detail"]
    bad_format = upload(b"x", filename="posts.txt", content_type="text/plain")
    assert bad_format.status_code == 415
    bad_file = upload(b"{oops", filename="posts.json", content_type="application/json")
    assert bad_file.status_code == 400 and "parsed" in bad_file.json()["detail"]


def test_too_dense_graph_returns_a_readable_error(monkeypatch):
    monkeypatch.setattr(graph_engine, "MAX_EDGES", 0)
    records = [good("p1", media_hash="h"), good("p2", account_id="a2", media_hash="h")]
    response = upload(json.dumps(records).encode(), filename="posts.json", content_type="application/json")
    assert response.status_code == 422
    assert "relationships" in response.json()["detail"]


def test_upload_size_limit(monkeypatch):
    monkeypatch.setattr(campaigns, "MAX_UPLOAD_BYTES", 10)
    assert upload(b"x" * 11).status_code == 413


def test_unknown_campaign_is_404():
    assert client.get("/api/campaigns/nope").status_code == 404
    assert client.get("/api/campaigns/nope/graph").status_code == 404
