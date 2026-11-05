"""SQLite persistence. These tests never open backend/data/veritas.db."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.database.connection import DEFAULT_DATABASE_PATH, get_database_path, initialize_database
from app.database.repository import (
    DuplicateAnalysisJobError,
    DuplicateCampaignError,
    get_analysis_job,
    insert_campaign,
    save_analysis_job,
)
from app.intelligence import campaign_store
from app.intelligence.graph_engine import build_graph
from app.intelligence.post_ingestion import Post

BASE = datetime(2026, 11, 5, 10, tzinfo=timezone.utc)


def _post(post_id, account, minutes=0, **fields):
    return Post(
        post_id=post_id,
        platform="platform_a",
        account_id=account,
        timestamp=BASE + timedelta(minutes=minutes),
        **fields,
    )


def _campaign(posts, provenance="synthetic_demo_data"):
    graph = build_graph(posts)
    graph["provenance"] = provenance
    summary = {"total_records": len(posts), "accepted": len(posts), "rejected": 0, "errors": [], "platforms": {"platform_a": len(posts)}}
    graph["import_summary"] = summary
    campaign = {
        "status": "completed" if posts else "no_valid_records",
        "provenance": provenance,
        "source_file": "synthetic_demo_data.csv",
        "import_summary": summary,
        "posts": [post.to_dict() for post in posts],
    }
    return campaign, graph


def test_database_initialization_creates_the_requested_tables(temporary_database):
    names = {
        row[0]
        for row in sqlite3.connect(temporary_database).execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {
        "campaigns",
        "accounts",
        "posts",
        "media_assets",
        "analysis_jobs",
        "graph_edges",
        "campaign_sources",
        "x_accounts",
        "x_post_details",
        "x_media",
        "post_relationships",
        "x_sync_runs",
    } <= names


def test_tests_do_not_modify_the_development_database(temporary_database):
    before = DEFAULT_DATABASE_PATH.stat().st_mtime if DEFAULT_DATABASE_PATH.exists() else None
    campaign, graph = _campaign([_post("p1", "a", media_hash="hash-one"), _post("p2", "b", minutes=5, media_hash="hash-one")])
    campaign_store.save_campaign(campaign, graph)
    after = DEFAULT_DATABASE_PATH.stat().st_mtime if DEFAULT_DATABASE_PATH.exists() else None
    assert get_database_path() == temporary_database
    assert after == before


def test_campaign_posts_and_edges_round_trip():
    posts = [
        _post("p1", "alpha", text="shared caption about the reservoir report", media_hash="abc123"),
        _post("p2", "beta", minutes=4, text="shared caption about the reservoir report", media_hash="abc123"),
        _post("p3", "gamma", minutes=30, text="unrelated note about trains"),
    ]
    campaign, graph = _campaign(posts)
    campaign_id = campaign_store.save_campaign(campaign, graph)

    stored = campaign_store.get_campaign(campaign_id)
    assert stored == campaign
    assert stored["posts"][0]["timestamp"].endswith("Z")
    assert stored["posts"][2]["media_hash"] is None

    stored_graph = campaign_store.get_graph(campaign_id)
    assert stored_graph["edges"] == graph["edges"]
    assert stored_graph["nodes"] == graph["nodes"]
    assert stored_graph["clusters"] == graph["clusters"]
    assert stored_graph["algorithm"] == graph["algorithm"]
    assert stored_graph["campaign_id"] == campaign_id

    with sqlite3.connect(temporary_path()) as connection:
        assets = connection.execute("SELECT media_hash FROM media_assets ORDER BY media_hash").fetchall()
    assert [row[0] for row in assets] == ["abc123", "abc123"]


def temporary_path():
    return get_database_path()


def test_duplicate_campaign_id_is_rejected_and_the_original_remains():
    campaign, graph = _campaign([_post("p1", "alpha")])
    campaign_store.save_campaign(campaign, graph)
    with pytest.raises(DuplicateCampaignError):
        insert_campaign(campaign, graph)
    assert campaign_store.get_campaign(campaign["campaign_id"])["posts"][0]["post_id"] == "p1"


def test_reimporting_a_file_creates_a_second_campaign():
    campaign, graph = _campaign([_post("p1", "alpha", media_hash="same")])
    first = campaign_store.save_campaign(dict(campaign), dict(graph))
    second_campaign, second_graph = _campaign([_post("p1", "alpha", media_hash="same")])
    second = campaign_store.save_campaign(second_campaign, second_graph)
    assert first != second
    assert {item["campaign_id"] for item in campaign_store.list_campaigns()} == {first, second}


def test_records_survive_a_new_connection_and_startup(temporary_database):
    campaign, graph = _campaign([
        _post("p1", "alpha", media_hash="persist"),
        _post("p2", "beta", minutes=2, media_hash="persist"),
    ])
    campaign_id = campaign_store.save_campaign(campaign, graph)
    edge_count = len(graph["edges"])
    assert edge_count >= 1

    initialize_database()
    reopened = sqlite3.connect(temporary_database)
    try:
        stored_edges = reopened.execute("SELECT edge_id, signals_json FROM graph_edges WHERE campaign_id = ?", (campaign_id,)).fetchall()
        stored_posts = reopened.execute("SELECT post_id, timestamp FROM posts WHERE campaign_id = ? ORDER BY position", (campaign_id,)).fetchall()
    finally:
        reopened.close()

    assert len(stored_edges) == edge_count
    assert [row[0] for row in stored_posts] == ["p1", "p2"]
    assert all(row[1].endswith("Z") for row in stored_posts)
    assert campaign_store.get_graph(campaign_id)["edges"] == graph["edges"]


def test_analysis_job_persists_without_inventing_a_score():
    campaign, graph = _campaign([_post("p1", "alpha")])
    campaign_id = campaign_store.save_campaign(campaign, graph)
    save_analysis_job(
        job_id="job_0001",
        campaign_id=campaign_id,
        post_id="p1",
        platform="platform_a",
        status="unavailable",
        status_reason="detector_not_implemented",
        result=None,
    )
    stored = get_analysis_job("job_0001")
    assert stored["status"] == "unavailable"
    assert stored["result"] is None
    assert stored["created_at"].endswith("Z")
    with pytest.raises(DuplicateAnalysisJobError):
        save_analysis_job(job_id="job_0001", status="completed", result={"fake_score": 0.99})
    assert get_analysis_job("job_0001")["result"] is None
