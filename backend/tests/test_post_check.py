from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import campaigns
from app.intelligence import graph_engine

app = FastAPI()
app.include_router(campaigns.router)
client = TestClient(app)

DEMO = Path(__file__).parents[1] / "data" / "synthetic_demo_data.csv"
CAPTION = "Riverton residents warned: the tap water tested unsafe after the reservoir leak. Officials are hiding the report."
PAGE_URL = "https://x.com/page_author/status/999"


@pytest.fixture()
def campaign_id():
    with DEMO.open("rb") as file:
        response = client.post(
            "/api/campaigns/import",
            files={"file": ("synthetic_demo_data.csv", file, "text/csv")},
            data={"source_type": "synthetic_demo_data"},
        )
    return response.json()["campaign_id"]


def check(campaign_id, **overrides):
    body = {"url": PAGE_URL, "platform": "x", "account": "@page_author", "timestamp": "2026-10-20T09:03:00Z", "post_text": CAPTION, **overrides}
    return client.post(f"/api/campaigns/{campaign_id}/check-post", json=body)


def signal_types(result):
    return {signal["type"] for signal in result["coordination"]["signals"]}


def test_matching_caption_and_time_return_engine_evidence(campaign_id):
    result = check(campaign_id).json()
    assert result["coordination"]["status"] == "signals_found"
    assert signal_types(result) == {"similar_caption", "close_posting_time"}
    assert result["coordination"]["related_post_count"] == 10
    signal = result["coordination"]["signals"][0]
    assert signal["related_account"].startswith("relay_news_")
    assert signal["evidence"].startswith(f"With {signal['related_account']}: ")
    assert "similarity" in signal["evidence"] or "within 10 min" in signal["evidence"]


def test_same_caption_outside_window_has_no_timing_signal(campaign_id):
    result = check(campaign_id, timestamp="2026-10-25T09:03:00Z").json()
    assert signal_types(result) == {"similar_caption"}


def test_timing_alone_links_nothing(campaign_id):
    result = check(campaign_id, post_text="Completely separate thoughts about mountain railways and vintage clocks").json()
    assert result["coordination"] == {"status": "none_found", "related_post_count": 0, "signals": []}


def test_same_subject_in_different_words_links_nothing(campaign_id):
    result = check(campaign_id, post_text="Our neighbourhood tap ran cloudy near the Riverton reservoir, so we boiled ours today").json()
    assert result["coordination"]["status"] == "none_found"


def test_missing_timestamp_is_not_invented(campaign_id):
    result = check(campaign_id, timestamp=None).json()
    assert result["timestamp_known"] is False
    assert signal_types(result) == {"similar_caption"}
    assert any("timestamp" in limitation for limitation in result["limitations"])
    posts = client.get(f"/api/campaigns/{result['campaign_id']}").json()["posts"]
    assert next(post for post in posts if post["url"] == PAGE_URL)["timestamp"] is None


def test_timestamp_without_timezone_counts_as_unknown(campaign_id):
    result = check(campaign_id, timestamp="2026-10-20").json()
    assert result["timestamp_known"] is False
    assert "close_posting_time" not in signal_types(result)


def test_missing_account_does_not_merge_pages(campaign_id):
    first = check(campaign_id, account=None).json()
    second = check(campaign_id, account=None, url="https://x.com/other/status/1000").json()
    assert first["coordination"]["status"] == "signals_found"
    nodes = client.get(f"/api/campaigns/{second['campaign_id']}/graph").json()["nodes"]
    checked = next(node for node in nodes if node["is_checked_post"])
    assert checked["label"].startswith("unknown_account_")


def test_original_campaign_is_not_changed_and_copy_shows_post(campaign_id):
    before = client.get(f"/api/campaigns/{campaign_id}").json()
    result = check(campaign_id).json()
    assert result["campaign_id"] != campaign_id
    assert client.get(f"/api/campaigns/{campaign_id}").json() == before

    copy = client.get(f"/api/campaigns/{result['campaign_id']}").json()
    assert len(copy["posts"]) == len(before["posts"]) + 1
    assert copy["parent_campaign_id"] == campaign_id
    assert copy["provenance"] == "synthetic_demo_data"
    assert copy["extension_post"]["url"] == PAGE_URL

    graph = client.get(f"/api/campaigns/{result['campaign_id']}/graph").json()
    assert [node["account_id"] for node in graph["nodes"] if node["is_checked_post"]] == ["@page_author"]
    edges = [edge for edge in graph["edges"] if "@page_author" in edge["id"]]
    assert edges
    assert all(edge["signals"] for edge in edges)


def test_post_already_in_dataset_is_not_duplicated_or_matched_to_itself(campaign_id):
    url = "https://example.invalid/post/d002"
    result = check(campaign_id, url=url, account="@someone_else").json()
    assert result["post_in_dataset"] is True
    assert result["campaign_id"] == campaign_id
    assert "d002" not in {
        post_id for signal in result["coordination"]["signals"] if signal["related_account"] == "relay_news_02" for post_id in signal["post_ids"]
    }
    assert "shared_url" not in signal_types(result)
    assert all(signal["related_account"] != "relay_news_02" for signal in result["coordination"]["signals"])


def test_account_other_posts_are_not_counted_as_this_post(campaign_id):
    result = check(campaign_id, account="budget_reader", platform="platform_a").json()
    assert all(signal["related_account"] != "budget_reader" for signal in result["coordination"]["signals"])


def test_no_score_or_verdict_fields(campaign_id):
    result = check(campaign_id).json()
    assert set(result["coordination"]) == {"status", "related_post_count", "signals"}
    assert any("don't establish intent" in limitation for limitation in result["limitations"])
    assert not {"score", "verdict", "malicious"} & set(result)


def test_list_shows_imported_campaigns_only(campaign_id):
    copy_id = check(campaign_id).json()["campaign_id"]
    listed = client.get("/api/campaigns").json()
    ids = [item["campaign_id"] for item in listed]
    assert ids[0] == campaign_id
    assert copy_id not in ids
    assert listed[0] == {"campaign_id": campaign_id, "source_file": "synthetic_demo_data.csv", "provenance": "synthetic_demo_data", "post_count": 34}


def test_errors(campaign_id, monkeypatch):
    assert check("nope").status_code == 404
    copy_id = check(campaign_id).json()["campaign_id"]
    assert check(copy_id).status_code == 409
    assert check(campaign_id, url="javascript:alert(1)").status_code == 422
    assert check(campaign_id, post_text="x" * 5001).status_code == 422

    monkeypatch.setattr(graph_engine, "MAX_EDGES", 0)
    response = check(campaign_id)
    assert response.status_code == 422
    assert "relationships" in response.json()["detail"]
