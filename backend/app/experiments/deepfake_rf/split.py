"""Group-aware splits. Videos that share a source_group_id stay together."""

from __future__ import annotations

import numpy as np

from app.experiments.deepfake_rf.manifest import is_regression_case


class SplitError(ValueError):
    pass


def assert_no_regression(rows: list[dict]) -> None:
    found = [row.get("video_id") for row in rows if is_regression_case(row)]
    if found:
        raise SplitError(
            "Regression cases cannot enter training, validation, or the comparative test: " + ", ".join(found)
        )


def _by_group(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["source_group_id"], []).append(row)
    return grouped


def _labels(rows: list[dict]) -> set[str]:
    return {row["label"] for row in rows}


def assign_grouped_split(rows: list[dict], *, seed: int, attempts: int = 50) -> dict[str, list[dict]]:
    """Place every source group entirely in train, validation, or test.

    Both classes must appear in train and in validation. Those two slices are
    the only slices allowed to influence the forest or the rejection thresholds.
    """
    assert_no_regression(rows)
    grouped = _by_group(rows)
    group_ids = list(grouped)
    if len(group_ids) < 3:
        raise SplitError("At least 3 source groups are required so a group is not shared across splits.")
    count = len(group_ids)
    if count >= 5:
        n_test = max(1, count // 5)
        n_val = max(2, count // 5)
        n_train = count - n_val - n_test
        if n_train < 2:
            n_val = 2
            n_test = 1
            n_train = count - 3
    else:
        n_test = 1
        n_val = 1
        n_train = count - 2
    if n_train < 1:
        raise SplitError("Not enough source groups to fill train, validation, and test.")
    for attempt in range(attempts):
        order = group_ids[:]
        rng = np.random.default_rng(seed + attempt)
        rng.shuffle(order)
        chosen = {
            "train": order[:n_train],
            "validation": order[n_train : n_train + n_val],
            "test": order[n_train + n_val :],
        }
        parts = {name: [row for group_id in ids for row in grouped[group_id]] for name, ids in chosen.items()}
        if _labels(parts["train"]) != {"real", "fake"} or _labels(parts["validation"]) != {"real", "fake"}:
            continue
        if not parts["test"]:
            continue
        parts["attempt"] = attempt
        return parts
    raise SplitError("Could not place both classes in train and validation without splitting a source group.")


def group_ids(rows: list[dict]) -> set[str]:
    return {row["source_group_id"] for row in rows}


def assert_group_disjoint(parts: dict[str, list[dict]]) -> None:
    names = ("train", "validation", "test")
    sets = [group_ids(parts[name]) for name in names]
    for index, left in enumerate(sets):
        for right in sets[index + 1 :]:
            shared = left & right
            if shared:
                raise SplitError("A source group appears in more than one split: " + ", ".join(sorted(shared)))
