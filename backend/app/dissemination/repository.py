"""Store propagation trees apart from the coordination graph."""

from __future__ import annotations

import json

from app.database.connection import session
from app.dissemination.metrics import propagation_metrics

REFERENCE = "https://github.com/gszswork/Twitter15_16_dataset"


def _provenance(row) -> dict:
    body = json.loads(row["provenance_json"])
    body["dataset_name"] = row["dataset_name"]
    body["imported_at"] = row["imported_at"]
    return body


def upsert_dataset(connection, dataset_name: str, source_path: str, provenance: dict, imported_at: str) -> None:
    connection.execute(
        """
        INSERT INTO propagation_datasets (dataset_name, source_path, provenance_json, imported_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(dataset_name) DO UPDATE SET
            source_path = excluded.source_path,
            provenance_json = excluded.provenance_json,
            imported_at = excluded.imported_at
        """,
        (dataset_name, source_path, json.dumps(provenance, sort_keys=True), imported_at),
    )


def replace_case(connection, case: dict, nodes: list[dict], edges: list[dict]) -> None:
    connection.execute(
        """
        INSERT INTO propagation_cases (
            case_id, dataset_name, source_tweet_id, source_user_id, label, source_text, warnings_json, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset_name, source_tweet_id) DO UPDATE SET
            case_id = excluded.case_id,
            source_user_id = excluded.source_user_id,
            label = excluded.label,
            source_text = excluded.source_text,
            warnings_json = excluded.warnings_json,
            imported_at = excluded.imported_at
        """,
        (
            case["case_id"],
            case["dataset_name"],
            case["source_tweet_id"],
            case["source_user_id"],
            case["label"],
            case["source_text"],
            json.dumps(case["warnings"]),
            case["imported_at"],
        ),
    )
    connection.execute("DELETE FROM propagation_edges WHERE case_id = ?", (case["case_id"],))
    connection.execute("DELETE FROM propagation_nodes WHERE case_id = ?", (case["case_id"],))
    connection.executemany(
        """
        INSERT INTO propagation_nodes (case_id, tweet_id, user_id, post_time_delay_minutes, is_root)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (case["case_id"], node["tweet_id"], node["user_id"], node["post_time_delay_minutes"], int(node["is_root"]))
            for node in nodes
        ],
    )
    connection.executemany(
        """
        INSERT INTO propagation_edges (
            case_id, parent_tweet_id, child_tweet_id, parent_user_id, child_user_id,
            parent_delay_minutes, child_delay_minutes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                case["case_id"],
                edge["parent_tweet_id"],
                edge["child_tweet_id"],
                edge["parent_user_id"],
                edge["child_user_id"],
                edge["parent_delay_minutes"],
                edge["child_delay_minutes"],
            )
            for edge in edges
        ],
    )


def _load_nodes(connection, case_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT tweet_id, user_id, post_time_delay_minutes, is_root
        FROM propagation_nodes WHERE case_id = ? ORDER BY tweet_id
        """,
        (case_id,),
    ).fetchall()
    return [
        {
            "tweet_id": row["tweet_id"],
            "user_id": row["user_id"],
            "post_time_delay_minutes": row["post_time_delay_minutes"],
            "is_root": bool(row["is_root"]),
        }
        for row in rows
    ]


def _load_edges(connection, case_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT parent_tweet_id, child_tweet_id, parent_user_id, child_user_id,
               parent_delay_minutes, child_delay_minutes
        FROM propagation_edges WHERE case_id = ? ORDER BY parent_tweet_id, child_tweet_id
        """,
        (case_id,),
    ).fetchall()
    return [
        {
            "id": f"{row['parent_tweet_id']}->{row['child_tweet_id']}",
            "source": row["parent_tweet_id"],
            "target": row["child_tweet_id"],
            "parent_tweet_id": row["parent_tweet_id"],
            "child_tweet_id": row["child_tweet_id"],
            "parent_user_id": row["parent_user_id"],
            "child_user_id": row["child_user_id"],
            "parent_delay_minutes": row["parent_delay_minutes"],
            "child_delay_minutes": row["child_delay_minutes"],
            "relationship": "propagation_parent_to_child",
        }
        for row in rows
    ]


def _case_row(connection, case_id: str):
    return connection.execute("SELECT * FROM propagation_cases WHERE case_id = ?", (case_id,)).fetchone()


def list_cases() -> list[dict]:
    with session() as connection:
        rows = connection.execute(
            """
            SELECT cases.case_id, cases.dataset_name, cases.source_tweet_id, cases.source_user_id,
                   cases.label, cases.source_text,
                   (SELECT COUNT(*) FROM propagation_nodes nodes WHERE nodes.case_id = cases.case_id) AS node_count,
                   (SELECT COUNT(*) FROM propagation_edges edges WHERE edges.case_id = cases.case_id) AS edge_count
            FROM propagation_cases cases
            ORDER BY cases.dataset_name, cases.source_tweet_id
            """
        ).fetchall()
    return [
        {
            "case_id": row["case_id"],
            "dataset_name": row["dataset_name"],
            "source_tweet_id": row["source_tweet_id"],
            "source_user_id": row["source_user_id"],
            "label": row["label"],
            "has_source_text": bool(row["source_text"]),
            "node_count": row["node_count"],
            "edge_count": row["edge_count"],
        }
        for row in rows
    ]


def get_case(case_id: str) -> dict | None:
    with session() as connection:
        row = _case_row(connection, case_id)
        if row is None:
            return None
        dataset = connection.execute(
            "SELECT * FROM propagation_datasets WHERE dataset_name = ?",
            (row["dataset_name"],),
        ).fetchone()
        nodes = _load_nodes(connection, case_id)
        edges = _load_edges(connection, case_id)
    metrics = propagation_metrics(nodes, edges, row["source_tweet_id"])
    metrics.pop("node_depth")
    return {
        "case_id": row["case_id"],
        "dataset_name": row["dataset_name"],
        "source_tweet_id": row["source_tweet_id"],
        "source_user_id": row["source_user_id"],
        "label": row["label"],
        "source_text": row["source_text"],
        "propagated_post_text": "not_included_in_dataset",
        "warnings": json.loads(row["warnings_json"]),
        "imported_at": row["imported_at"],
        "provenance": _provenance(dataset) if dataset is not None else None,
        "metrics": metrics,
    }


def get_graph(case_id: str) -> dict | None:
    with session() as connection:
        row = _case_row(connection, case_id)
        if row is None:
            return None
        nodes = _load_nodes(connection, case_id)
        edges = _load_edges(connection, case_id)
    metrics = propagation_metrics(nodes, edges, row["source_tweet_id"])
    depths = metrics.pop("node_depth")
    graph_nodes = []
    for node in nodes:
        text = row["source_text"] if node["tweet_id"] == row["source_tweet_id"] else None
        graph_nodes.append(
            {
                **node,
                "id": node["tweet_id"],
                "depth": depths.get(node["tweet_id"]),
                "text": text,
                "text_status": "source_post" if text else "not_included_in_dataset",
            }
        )
    return {
        "case_id": case_id,
        "directed": True,
        "relationship": "propagation_parent_to_child",
        "nodes": graph_nodes,
        "edges": edges,
        "metrics": metrics,
    }
