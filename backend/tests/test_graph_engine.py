from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.intelligence import graph_engine
from app.intelligence.graph_engine import GraphTooLargeError, build_graph
from app.intelligence.post_ingestion import Post, import_posts
from app.intelligence.similarity import normalise_url, urls_in_post

BASE = datetime(2026, 11, 5, 10, tzinfo=timezone.utc)
DEMO = Path(__file__).parents[1] / "data" / "synthetic_demo_data.csv"
CAPTION = "Riverton reservoir leak leaves tap water unsafe while officials hide the report"


def post(post_id, account, minutes=0, platform="platform_a", **fields):
    return Post(post_id=post_id, platform=platform, account_id=account, timestamp=BASE + timedelta(minutes=minutes), **fields)


def signal_types(edge):
    return [signal["type"] for signal in edge["signals"]]


def test_empty_input():
    graph = build_graph([])
    assert (graph["nodes"], graph["edges"], graph["clusters"]) == ([], [], [])


def test_media_hash_match_creates_edge_with_evidence():
    graph = build_graph([post("p1", "a", media_hash="h1"), post("p2", "b", minutes=120, media_hash="h1")])
    edge = graph["edges"][0]
    assert signal_types(edge) == ["same_media_hash"]
    assert "h1" in edge["signals"][0]["evidence"]
    assert edge["signals"][0]["post_ids"] == ["p1", "p2"]


def test_similar_captions_link_and_report_similarity():
    graph = build_graph([post("p1", "a", text=CAPTION), post("p2", "b", minutes=120, text=f"{CAPTION} today")])
    signal = graph["edges"][0]["signals"][0]
    assert signal["type"] == "similar_caption"
    assert "similarity" in signal["evidence"]


def test_words_inside_a_shared_url_do_not_count_as_similar_captions():
    link = "https://example.invalid/riverton/budget/report/analysis/figures/summary"
    graph = build_graph(
        [
            post("p1", "a", minutes=500, text=f"Sourdough crust crackling beautifully today {link}"),
            post("p2", "b", text=f"Forty kilometres along the coast road {link}"),
        ]
    )
    assert signal_types(graph["edges"][0]) == ["shared_url"]


def test_too_many_relationships_are_refused(monkeypatch):
    monkeypatch.setattr(graph_engine, "MAX_EDGES", 2)
    with pytest.raises(GraphTooLargeError, match="3 relationships"):
        build_graph([post(f"p{i}", f"a{i}", media_hash="h") for i in range(3)])


def test_short_captions_never_match():
    graph = build_graph([post("p1", "a", text="so true"), post("p2", "b", text="so true")])
    assert graph["edges"] == []


def test_timing_alone_never_creates_an_edge():
    graph = build_graph([post("p1", "a", text="Sourdough crust crackling beautifully today"), post("p2", "b", text="Forty kilometres along the coast road")])
    assert graph["edges"] == []
    assert len(graph["nodes"]) == 2


def test_close_timing_is_added_only_inside_the_window():
    inside = build_graph([post("p1", "a", media_hash="h"), post("p2", "b", minutes=10, media_hash="h")])
    outside = build_graph([post("p1", "a", media_hash="h"), post("p2", "b", minutes=11, media_hash="h")])
    assert signal_types(inside["edges"][0]) == ["same_media_hash", "close_posting_time"]
    assert signal_types(outside["edges"][0]) == ["same_media_hash"]


def test_shared_url_from_field_or_text():
    graph = build_graph(
        [
            post("p1", "a", url="https://Example.invalid/story/"),
            post("p2", "b", minutes=300, text="Read this https://example.invalid/story#top."),
        ]
    )
    assert signal_types(graph["edges"][0]) == ["shared_url"]


def test_same_account_is_never_linked_to_itself():
    graph = build_graph([post("p1", "a", media_hash="h"), post("p2", "a", minutes=1, media_hash="h")])
    assert graph["edges"] == []
    assert graph["nodes"][0]["post_count"] == 2


def test_same_handle_on_two_platforms_stays_two_accounts():
    graph = build_graph([post("p1", "a", platform="platform_a"), post("p2", "a", platform="platform_b")])
    assert sorted(node["id"] for node in graph["nodes"]) == ["platform_a:a", "platform_b:a"]


def test_repeated_pairs_are_summarised_as_one_signal_per_type():
    graph = build_graph(
        [
            post("p1", "a", media_hash="h1"),
            post("p2", "a", minutes=500, media_hash="h2"),
            post("p3", "b", minutes=1000, media_hash="h1"),
            post("p4", "b", minutes=1500, media_hash="h2"),
        ]
    )
    assert len(graph["edges"]) == 1
    assert signal_types(graph["edges"][0]) == ["same_media_hash"]
    assert graph["edges"][0]["signals"][0]["post_pair_count"] == 2


def test_cluster_needs_three_accounts_and_multi_signal_edges():
    two = build_graph([post("p1", "a", media_hash="h"), post("p2", "b", media_hash="h")])
    assert two["clusters"] == []

    weak = build_graph([post(f"p{i}", f"a{i}", minutes=i * 100, media_hash="h") for i in range(3)])
    assert len(weak["edges"]) == 3
    assert weak["clusters"] == []

    strong = build_graph([post(f"p{i}", f"a{i}", minutes=i, media_hash="h") for i in range(3)])
    assert len(strong["clusters"]) == 1
    assert {node["cluster_id"] for node in strong["nodes"]} == {"cluster_1"}


def test_every_edge_has_evidence_and_refers_to_real_nodes():
    posts = import_posts(DEMO.read_bytes(), "csv").posts
    graph = build_graph(posts)
    ids = {node["id"] for node in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["source"] in ids and edge["target"] in ids
        assert edge["signals"]
        for signal in edge["signals"]:
            assert signal["evidence"] and signal["post_ids"]


def test_graph_makes_no_verdicts():
    graph = build_graph(import_posts(DEMO.read_bytes(), "csv").posts)
    assert not {"score", "verdict", "malicious"} & set(graph)
    assert any("don't establish intent" in limitation for limitation in graph["limitations"])


class TestDemoDataset:
    """The planted patterns documented in data/README.md."""

    result = import_posts(DEMO.read_bytes(), "csv")
    graph = build_graph(result.posts)

    def accounts_with_edges(self):
        return {name for edge in self.graph["edges"] for name in (edge["source"], edge["target"])}

    def test_size_and_platforms(self):
        assert self.result.errors == []
        assert 30 <= len(self.result.posts) <= 50
        assert set(self.result.summary()["platforms"]) == {"platform_a", "platform_b"}

    def test_coordinated_group_is_one_cluster(self):
        assert len(self.graph["clusters"]) == 1
        cluster = self.graph["clusters"][0]
        assert len(cluster["account_ids"]) == 8
        assert all("relay_news_" in account for account in cluster["account_ids"])
        assert cluster["signals"] == ["same_media_hash", "similar_caption", "close_posting_time"]

    def test_coordinated_group_spans_both_platforms(self):
        platforms = {account.split(":")[0] for account in self.graph["clusters"][0]["account_ids"]}
        assert platforms == {"platform_a", "platform_b"}

    def test_same_subject_group_has_no_edges(self):
        independent = {post.account_id for post in self.result.posts[10:20]}
        linked = {name.split(":")[1] for name in self.accounts_with_edges()}
        assert not independent & linked

    def test_unrelated_posts_in_the_same_time_window_have_no_edges(self):
        unrelated = {post.account_id for post in self.result.posts[22:]}
        linked = {name.split(":")[1] for name in self.accounts_with_edges()}
        assert not unrelated & linked

    def test_weak_link_is_an_edge_but_not_a_cluster(self):
        edges = [edge for edge in self.graph["edges"] if "budget_reader" in edge["id"]]
        assert len(edges) == 1
        assert signal_types(edges[0]) == ["shared_url"]
        node = next(node for node in self.graph["nodes"] if node["account_id"] == "budget_reader")
        assert node["cluster_id"] is None


def test_larger_graph_stays_consistent():
    posts = [post(f"p{i}", f"a{i % 50}", minutes=i, media_hash=f"h{i % 5}") for i in range(500)]
    graph = build_graph(posts)
    assert len(graph["nodes"]) == 50
    assert all(edge["signals"] for edge in graph["edges"])


def test_normalise_url_rejects_other_schemes():
    assert normalise_url("javascript:alert(1)") is None
    assert normalise_url("ftp://example.invalid/x") is None
    assert urls_in_post(None, None) == set()
