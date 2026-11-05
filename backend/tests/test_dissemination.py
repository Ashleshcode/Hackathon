"""Historical propagation import, metrics, and API. Uses a temporary database."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.dissemination import dissemination_case
from app.database.connection import session
from app.dissemination.import_dataset import PropagationImportError, import_propagation_directory
from app.dissemination.metrics import propagation_metrics
from app.dissemination.parse import parse_tree_text
from app.dissemination.repository import get_case, get_graph, list_cases

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "twitter_propagation"


def _counts():
    with session() as connection:
        return {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in (
                "propagation_cases",
                "propagation_nodes",
                "propagation_edges",
                "graph_edges",
                "post_relationships",
            )
        }


def test_tree_parser_keeps_parent_to_child_direction_and_delays():
    parsed = parse_tree_text("100", "['ROOT', 'ROOT', '0.0']->['10', '100', '0.0']\n['10', '100', '0.0']->['11', '101', '2.5']\n")
    assert parsed.edges[1].parent.tweet_id == "100"
    assert parsed.edges[1].child.tweet_id == "101"
    assert parsed.edges[1].parent.user_id == "10"
    assert parsed.edges[1].child.delay_minutes == 2.5
    assert parsed.edges[0].child.tweet_id == "100"


def test_import_preserves_labels_roots_and_does_not_invent_reply_text():
    report = import_propagation_directory(FIXTURE)
    assert {item["dataset_name"] for item in report["datasets"]} == {"twitter15", "twitter16"}
    cases = {item["case_id"]: item for item in list_cases()}
    assert cases["prop_twitter15_100"]["label"] == "false"
    assert cases["prop_twitter15_100"]["has_source_text"] is True
    assert cases["prop_twitter15_200"]["label"] == "non-rumor"
    assert cases["prop_twitter15_200"]["has_source_text"] is False
    assert cases["prop_twitter15_300"]["label"] is None
    assert cases["prop_twitter16_500"]["label"] == "unverified"
    assert "prop_twitter15_400" not in cases
    assert "prop_twitter15_bad" not in cases

    case = get_case("prop_twitter15_100")
    graph = get_graph("prop_twitter15_100")
    assert case["source_text"] == "The source post text"
    assert case["propagated_post_text"] == "not_included_in_dataset"
    assert case["provenance"]["reference"].endswith("Twitter15_16_dataset")
    assert case["metrics"]["node_count"] == 4
    assert case["metrics"]["edge_count"] == 3
    assert case["metrics"]["maximum_depth"] == 2
    assert case["metrics"]["branching_factor"] == 1.5
    assert case["metrics"]["nodes_per_depth"] == {"0": 1, "1": 2, "2": 1}
    assert case["metrics"]["time_span_minutes"] == 9.5
    assert case["metrics"]["time_delay_distribution"]["values_minutes"] == [0.0, 2.5, 4.0, 9.5]
    edge = next(item for item in graph["edges"] if item["child_tweet_id"] == "101")
    assert edge["source"] == "100"
    assert edge["target"] == "101"
    assert edge["relationship"] == "propagation_parent_to_child"
    texts = {node["tweet_id"]: node["text"] for node in graph["nodes"]}
    assert texts["100"] == "The source post text"
    assert texts["101"] is None
    assert next(node for node in graph["nodes"] if node["tweet_id"] == "100")["is_root"] is True
    assert any("not a number" in warning for warning in get_case("prop_twitter15_200")["warnings"])
    assert "400" in case["provenance"]["missing_tree_ids"] or "400" in get_case("prop_twitter15_300")["provenance"]["missing_tree_ids"]


def test_duplicate_import_does_not_duplicate_rows():
    import_propagation_directory(FIXTURE)
    first = _counts()
    import_propagation_directory(FIXTURE)
    assert _counts() == first
    assert first["propagation_cases"] == 4
    assert first["propagation_edges"] == 6


def test_import_leaves_coordination_edges_in_place():
    with session() as connection:
        connection.execute(
            """
            INSERT INTO campaigns (campaign_id, status, provenance, import_summary_json, clusters_json, created_at)
            VALUES ('kept', 'completed', 'uploaded_dataset', '{}', '[]', '2026-01-01T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO graph_edges (campaign_id, edge_id, source_node, target_node, signals_json, position)
            VALUES ('kept', 'edge-1', 'account-a', 'account-b', '[]', 0)
            """
        )
    import_propagation_directory(FIXTURE)
    assert _counts()["graph_edges"] == 1
    assert _counts()["post_relationships"] == 0
    with session() as connection:
        edge = connection.execute("SELECT source_node, target_node FROM graph_edges").fetchone()
    assert edge["source_node"] == "account-a"
    assert edge["target_node"] == "account-b"


def test_failed_import_rolls_back():
    def boom(connection, _dataset, _imported_at):
        connection.execute(
            """
            INSERT INTO propagation_datasets (dataset_name, source_path, provenance_json, imported_at)
            VALUES ('twitter15', 'local', '{}', '2026-01-01T00:00:00Z')
            """
        )
        raise RuntimeError("boom")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.dissemination.import_dataset._import_dataset", boom)
    try:
        with pytest.raises(RuntimeError, match="boom"):
            import_propagation_directory(FIXTURE)
    finally:
        monkeypatch.undo()
    with session() as connection:
        assert connection.execute("SELECT COUNT(*) FROM propagation_datasets").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM propagation_cases").fetchone()[0] == 0


def test_missing_directory_is_rejected(tmp_path):
    with pytest.raises(PropagationImportError):
        import_propagation_directory(tmp_path)


def test_unknown_case_is_a_404():
    with pytest.raises(HTTPException) as caught:
        dissemination_case("prop_twitter15_missing")
    assert caught.value.status_code == 404


def test_depth_stops_on_a_cycle():
    nodes = [
        {"tweet_id": "a", "post_time_delay_minutes": 0.0},
        {"tweet_id": "b", "post_time_delay_minutes": 1.0},
    ]
    edges = [
        {"parent_tweet_id": "a", "child_tweet_id": "b"},
        {"parent_tweet_id": "b", "child_tweet_id": "a"},
    ]
    metrics = propagation_metrics(nodes, edges, "a")
    assert metrics["maximum_depth"] == 1
    assert metrics["unreachable_node_count"] == 0
