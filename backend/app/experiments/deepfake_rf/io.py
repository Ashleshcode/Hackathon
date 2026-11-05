"""Read and write extraction tables."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.experiments.deepfake_rf.schema import FEATURE_COLUMNS


def write_feature_csv(path: str | Path, rows: list[dict]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["video_id", *FEATURE_COLUMNS])
        writer.writeheader()
        for row in rows:
            body = {"video_id": row["video_id"]}
            for key in FEATURE_COLUMNS:
                value = row.get(key)
                body[key] = "" if value is None else value
            writer.writerow(body)


def read_feature_csv(path: str | Path) -> dict[str, dict]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        found: dict[str, dict] = {}
        for row in reader:
            features = {}
            for key in FEATURE_COLUMNS:
                text = (row.get(key) or "").strip()
                features[key] = None if text == "" else float(text)
            found[row["video_id"]] = features
    return found


def write_frames_jsonl(path: str | Path, rows: list[dict]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def read_frames_jsonl(path: str | Path) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    file_path = Path(path)
    if not file_path.is_file():
        return found
    with file_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            body = json.loads(line)
            found[body["video_id"]] = body["frames"]
    return found


def write_failures(path: str | Path, rows: list[dict]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["video_id", "file_path", "error"])
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, body: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
