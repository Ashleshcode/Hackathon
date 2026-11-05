"""Prove a manifest's source groups and sequence ids do not cross splits."""

from __future__ import annotations

import re

from app.experiments.deepfake_rf.manifest import is_regression_case
from app.experiments.deepfake_rf.split import SplitError, assert_group_disjoint, assign_grouped_split, group_ids

_SEQUENCE = re.compile(r"\b(?:sequence|target|source)=([0-9]+)")
_COMPONENT = re.compile(r"\bcomponent=([0-9,]+)")


class SplitAuditError(ValueError):
    pass


def sequence_ids(row: dict) -> set[str]:
    notes = row.get("notes") or ""
    found = set(_SEQUENCE.findall(notes))
    component = _COMPONENT.search(notes)
    if component:
        found.update(part for part in component.group(1).split(",") if part)
    return found


def overlapping_groups(parts: dict[str, list[dict]]) -> list[str]:
    names = [name for name in ("train", "validation", "test") if name in parts]
    seen: dict[str, str] = {}
    overlap: list[str] = []
    for name in names:
        for group in group_ids(parts[name]):
            if group in seen and seen[group] != name:
                overlap.append(group)
            seen[group] = name
    return sorted(set(overlap))


def overlapping_sequence_ids(rows: list[dict]) -> list[str]:
    owner: dict[str, str] = {}
    shared: list[str] = []
    for row in rows:
        group = row.get("source_group_id") or ""
        for sequence in sequence_ids(row):
            previous = owner.get(sequence)
            if previous is not None and previous != group:
                shared.append(sequence)
            owner[sequence] = group
    return sorted(set(shared))


def audit_manifest(rows: list[dict], *, seed: int = 42) -> dict:
    """Check identity grouping, then a train/validation/test assignment when enough groups exist."""
    regression = [row for row in rows if is_regression_case(row)]
    trainable = [row for row in rows if not is_regression_case(row)]
    shared = overlapping_sequence_ids(trainable)
    if shared:
        raise SplitAuditError("Sequence ids belong to more than one source group: " + ", ".join(shared))
    group_count = len({row.get("source_group_id") for row in trainable})
    if group_count < 3:
        return {
            "train_groups": [],
            "validation_groups": [],
            "test_groups": [],
            "regression_video_ids": sorted(row["video_id"] for row in regression),
            "sequence_ids_by_split": {},
            "split_assignment": "not_enough_groups",
        }
    try:
        parts = assign_grouped_split(trainable, seed=seed)
        assert_group_disjoint(parts)
    except SplitError as exc:
        raise SplitAuditError(str(exc)) from exc
    leaked = overlapping_groups(parts)
    if leaked:
        raise SplitAuditError("Source groups cross the held-out split: " + ", ".join(leaked))
    split_ids: dict[str, set[str]] = {name: set() for name in ("train", "validation", "test")}
    for name in split_ids:
        for row in parts[name]:
            split_ids[name].update(sequence_ids(row))
    for left_name, left_ids in split_ids.items():
        for right_name, right_ids in split_ids.items():
            if left_name >= right_name:
                continue
            conflict = left_ids & right_ids
            if conflict:
                raise SplitAuditError(
                    f"Sequence ids {', '.join(sorted(conflict))} appear in both {left_name} and {right_name}."
                )
    regression_ids = {row["video_id"] for row in regression}
    split_videos = {row["video_id"] for name in split_ids for row in parts[name]}
    if regression_ids & split_videos:
        raise SplitAuditError("A regression-only video entered a train, validation, or test split.")
    return {
        "train_groups": sorted(group_ids(parts["train"])),
        "validation_groups": sorted(group_ids(parts["validation"])),
        "test_groups": sorted(group_ids(parts["test"])),
        "regression_video_ids": sorted(regression_ids),
        "sequence_ids_by_split": {name: sorted(values) for name, values in split_ids.items()},
        "split_assignment": "grouped",
    }
