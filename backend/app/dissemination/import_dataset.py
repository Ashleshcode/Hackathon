"""Offline import of a locally supplied Twitter15 or Twitter16 directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.database.connection import session, utc_now
from app.dissemination.parse import (
    DATASET_REFERENCE,
    TreeEdge,
    canonical_dataset_name,
    case_id_for,
    is_root_sentinel,
    read_label_file,
    read_source_posts,
    read_tree_file,
)
from app.dissemination.repository import replace_case, upsert_dataset


class PropagationImportError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetDirectory:
    name: str
    path: Path


def discover_datasets(root: Path) -> list[DatasetDirectory]:
    root = Path(root)
    candidates: list[Path] = []
    if (root / "tree").is_dir() and (root / "label.txt").is_file():
        candidates.append(root)
    else:
        if not root.is_dir():
            raise PropagationImportError(f"Dataset directory does not exist: {root}")
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "tree").is_dir() and (child / "label.txt").is_file():
                candidates.append(child)
    found: list[DatasetDirectory] = []
    for path in candidates:
        name = canonical_dataset_name(path.name)
        if name is None:
            raise PropagationImportError(
                f"{path} is not named twitter15 or twitter16. The importer does not download or guess a dataset."
            )
        found.append(DatasetDirectory(name, path))
    if not found:
        raise PropagationImportError(
            "No twitter15 or twitter16 directory with label.txt and a tree folder was found. "
            "Place the dataset locally. It is not downloaded."
        )
    return found


def _nodes_and_edges(source_tweet_id: str, edges: list[TreeEdge]) -> tuple[list[dict], list[dict], str | None, list[str]]:
    nodes: dict[str, dict] = {}
    stored_edges: list[dict] = []
    warnings: list[str] = []
    root_user_id = None

    def add_node(user_id: str, tweet_id: str, delay: float | None, is_root: bool) -> None:
        current = nodes.get(tweet_id)
        if current is None:
            nodes[tweet_id] = {
                "tweet_id": tweet_id,
                "user_id": user_id,
                "post_time_delay_minutes": delay,
                "is_root": is_root,
            }
            return
        if current["user_id"] != user_id:
            warnings.append(f"tweet {tweet_id} appears with user ids {current['user_id']} and {user_id}")
        if is_root:
            current["is_root"] = True

    for edge in edges:
        if is_root_sentinel(edge.parent):
            add_node(edge.child.user_id, edge.child.tweet_id, edge.child.delay_minutes, edge.child.tweet_id == source_tweet_id)
            if edge.child.tweet_id == source_tweet_id:
                root_user_id = edge.child.user_id
            continue
        add_node(edge.parent.user_id, edge.parent.tweet_id, edge.parent.delay_minutes, edge.parent.tweet_id == source_tweet_id)
        add_node(edge.child.user_id, edge.child.tweet_id, edge.child.delay_minutes, edge.child.tweet_id == source_tweet_id)
        if edge.parent.tweet_id == source_tweet_id:
            root_user_id = edge.parent.user_id
        stored_edges.append(
            {
                "parent_tweet_id": edge.parent.tweet_id,
                "child_tweet_id": edge.child.tweet_id,
                "parent_user_id": edge.parent.user_id,
                "child_user_id": edge.child.user_id,
                "parent_delay_minutes": edge.parent.delay_minutes,
                "child_delay_minutes": edge.child.delay_minutes,
            }
        )
    if source_tweet_id in nodes:
        nodes[source_tweet_id]["is_root"] = True
        root_user_id = nodes[source_tweet_id]["user_id"]
    elif nodes:
        warnings.append(f"source tweet {source_tweet_id} is not a node in its tree file")
    return list(nodes.values()), stored_edges, root_user_id, warnings


def _import_dataset(connection, dataset: DatasetDirectory, imported_at: str) -> dict:
    labels, label_warnings = read_label_file(dataset.path / "label.txt")
    posts, post_warnings = read_source_posts(dataset.path / "source_tweets.txt")
    tree_dir = dataset.path / "tree"
    tree_files = sorted(path for path in tree_dir.iterdir() if path.is_file())
    imported: list[str] = []
    malformed: list[dict] = []
    missing_labels: list[str] = []
    for path in tree_files:
        parsed = read_tree_file(path)
        nodes, edges, root_user, structure_warnings = _nodes_and_edges(parsed.source_tweet_id, parsed.edges)
        warnings = [*parsed.warnings, *structure_warnings]
        if not nodes:
            malformed.append({"source_tweet_id": parsed.source_tweet_id, "warnings": warnings or ["tree file has no nodes"]})
            continue
        label = labels.get(parsed.source_tweet_id)
        if label is None:
            missing_labels.append(parsed.source_tweet_id)
            warnings.append("label.txt has no label for this source tweet")
        replace_case(
            connection,
            {
                "case_id": case_id_for(dataset.name, parsed.source_tweet_id),
                "dataset_name": dataset.name,
                "source_tweet_id": parsed.source_tweet_id,
                "source_user_id": root_user,
                "label": label,
                "source_text": posts.get(parsed.source_tweet_id),
                "warnings": warnings,
                "imported_at": imported_at,
            },
            nodes,
            edges,
        )
        imported.append(parsed.source_tweet_id)
    missing_trees = sorted(set(labels) - set(imported) - {item["source_tweet_id"] for item in malformed})
    missing_post_trees = sorted(set(posts) - set(imported) - {item["source_tweet_id"] for item in malformed})
    provenance = {
        "reference": DATASET_REFERENCE,
        "description": (
            "Historical parent-to-child propagation trees. "
            "Only source-post text is present. Propagated post text was not supplied and was not reconstructed."
        ),
        "source_path": str(dataset.path),
        "tree_file_count": len(tree_files),
        "label_count": len(labels),
        "source_post_count": len(posts),
        "imported_case_count": len(imported),
        "malformed_files": malformed,
        "missing_tree_ids": missing_trees,
        "source_posts_without_trees": missing_post_trees,
        "missing_label_ids": missing_labels,
        "file_warnings": [*label_warnings, *post_warnings],
    }
    upsert_dataset(connection, dataset.name, str(dataset.path), provenance, imported_at)
    return {"dataset_name": dataset.name, "imported_case_count": len(imported), "malformed_file_count": len(malformed)}


def import_propagation_directory(root: Path) -> dict:
    datasets = discover_datasets(root)
    imported_at = utc_now()
    summaries = []
    with session() as connection:
        for dataset in datasets:
            summaries.append(_import_dataset(connection, dataset, imported_at))
    return {"datasets": summaries}
