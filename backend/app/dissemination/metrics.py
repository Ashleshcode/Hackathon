"""Metrics that can be read from a stored parent-to-child tree."""

from __future__ import annotations

import math
from collections import defaultdict


def propagation_metrics(nodes: list[dict], edges: list[dict], root_tweet_id: str | None) -> dict:
    by_id = {node["tweet_id"]: node for node in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        children[edge["parent_tweet_id"]].append(edge["child_tweet_id"])

    depth: dict[str, int] = {}
    unreachable = sorted(by_id)
    if root_tweet_id in by_id:
        queue = [root_tweet_id]
        depth[root_tweet_id] = 0
        unreachable.remove(root_tweet_id)
        while queue:
            current = queue.pop(0)
            for child in children.get(current, []):
                if child not in by_id or child in depth:
                    continue
                depth[child] = depth[current] + 1
                queue.append(child)
                unreachable.remove(child)

    levels: dict[str, int] = {}
    for value in depth.values():
        levels[str(value)] = levels.get(str(value), 0) + 1
    parent_count = sum(1 for tweet_id in by_id if children.get(tweet_id))
    delays = [
        float(node["post_time_delay_minutes"])
        for node in nodes
        if node.get("post_time_delay_minutes") is not None and math.isfinite(float(node["post_time_delay_minutes"]))
    ]
    ordered = sorted(delays)
    median = None
    if ordered:
        middle = len(ordered) // 2
        if len(ordered) % 2:
            median = ordered[middle]
        else:
            median = (ordered[middle - 1] + ordered[middle]) / 2
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "maximum_depth": max(depth.values()) if depth else None,
        "branching_factor": (len(edges) / parent_count) if parent_count else None,
        "nodes_per_depth": levels,
        "unreachable_node_count": len(unreachable),
        "time_span_minutes": (ordered[-1] - ordered[0]) if len(ordered) >= 2 else None,
        "time_delay_distribution": {
            "count": len(ordered),
            "missing": len(nodes) - len(ordered),
            "minimum_minutes": ordered[0] if ordered else None,
            "median_minutes": median,
            "maximum_minutes": ordered[-1] if ordered else None,
            "values_minutes": ordered,
        },
        "node_depth": depth,
    }
