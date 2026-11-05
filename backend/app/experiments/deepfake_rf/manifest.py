"""Manifest rows for locally supplied videos. This module does not download data."""

from __future__ import annotations

import csv
from pathlib import Path

MANIFEST_COLUMNS = (
    "video_id",
    "file_path",
    "label",
    "dataset_name",
    "source_group_id",
    "capture_condition",
    "notes",
)
LABELS = {"real", "fake"}
REGRESSION_DATASET = "real_world_regression"
REGRESSION_TOKEN = "usage=regression_only"


class ManifestError(ValueError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def is_regression_case(row: dict) -> bool:
    usage = (row.get("usage") or "").strip().lower()
    notes = (row.get("notes") or "").lower()
    dataset = (row.get("dataset_name") or "").strip()
    return usage == "regression_only" or REGRESSION_TOKEN in notes or dataset == REGRESSION_DATASET


def is_synthetic_dataset(row: dict) -> bool:
    name = (row.get("dataset_name") or "").strip().lower()
    return name == "synthetic_demo_data" or name.startswith("synthetic")


def resolve_video_path(file_path: str, *, root: Path | None = None) -> Path:
    path = Path(file_path)
    if path.is_absolute():
        return path
    return (root or repo_root()) / path


def load_manifest(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ManifestError("The manifest has no header.")
        fields = [name.strip() for name in reader.fieldnames]
        missing = [name for name in MANIFEST_COLUMNS if name not in fields]
        if missing:
            raise ManifestError(f"The manifest is missing columns: {', '.join(missing)}")
        columns = list(MANIFEST_COLUMNS)
        if "usage" in fields:
            columns.append("usage")
        rows = []
        for raw in reader:
            if raw is None:
                continue
            if all(not (value or "").strip() for value in raw.values()):
                continue
            rows.append({name: (raw.get(name) or "").strip() for name in columns})
    validate_manifest(rows)
    return rows


def validate_manifest(rows: list[dict]) -> None:
    if not rows:
        raise ManifestError("The manifest has no videos.")
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        video_id = (row.get("video_id") or "").strip()
        if not video_id:
            raise ManifestError(f"Row {index} has an empty video_id.")
        if video_id in seen:
            raise ManifestError(f"Duplicate video_id {video_id}.")
        seen.add(video_id)
        label = (row.get("label") or "").strip()
        if label not in LABELS:
            raise ManifestError(f"Row {index} has label {label!r}. Expected real or fake.")
        if not (row.get("file_path") or "").strip():
            raise ManifestError(f"Row {index} has an empty file_path.")
        if not (row.get("dataset_name") or "").strip():
            raise ManifestError(f"Row {index} has an empty dataset_name.")
        if not (row.get("source_group_id") or "").strip():
            raise ManifestError(f"Row {index} has an empty source_group_id.")
        if "capture_condition" not in row or "notes" not in row:
            raise ManifestError(f"Row {index} is missing capture_condition or notes.")
        if is_synthetic_dataset(row):
            raise ManifestError(
                f"Row {index} uses dataset {row.get('dataset_name')!r}. Synthetic rows cannot be extracted or trained."
            )


def missing_videos(rows: list[dict], *, root: Path | None = None) -> list[dict]:
    missing = []
    for row in rows:
        path = resolve_video_path(row["file_path"], root=root)
        if not path.is_file():
            missing.append(row)
    return missing
