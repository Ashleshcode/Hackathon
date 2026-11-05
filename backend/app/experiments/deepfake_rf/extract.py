"""Run the existing detector once and write one feature row per video."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from app.experiments.deepfake_rf import FEATURE_SCHEMA_VERSION, MEASUREMENT_SOURCE, MODEL_VERSION
from app.experiments.deepfake_rf.features import FeatureError, features_from_frames
from app.experiments.deepfake_rf.io import write_failures, write_feature_csv, write_frames_jsonl, write_json
from app.experiments.deepfake_rf.manifest import is_synthetic_dataset, missing_videos, resolve_video_path
from app.experiments.deepfake_rf.visual import measure_visual


class ExtractionRefused(RuntimeError):
    pass


def api_port_open(host: str = "127.0.0.1", port: int = 8000) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def ensure_api_is_stopped(probe) -> None:
    if probe():
        raise ExtractionRefused(
            "The API server is accepting connections on port 8000. "
            "Stop it before feature extraction so a second DeepGuard process is not loaded onto the GPU."
        )


def _result_frames(result: Any) -> tuple[list[dict] | None, str | None]:
    if hasattr(result, "frame_results"):
        frames = result.frame_results
        code = result.error_code or result.status
    else:
        frames = result.get("frame_results")
        code = result.get("error_code") or result.get("status")
    return frames, code


def _public_frames(frames: list[dict]) -> list[dict]:
    kept = []
    for frame in frames:
        kept.append(
            {
                "timestamp_seconds": frame.get("timestamp_seconds"),
                "status": frame.get("status"),
                "face_detected": frame.get("face_detected", frame.get("status") == "scored"),
                "fake_score": frame.get("fake_score"),
                "detector_confidence": frame.get("detector_confidence"),
                "face_area_ratio": frame.get("face_area_ratio"),
                "crop_width": frame.get("crop_width"),
                "crop_height": frame.get("crop_height"),
            }
        )
    return kept


def extract_manifest(
    rows: list[dict],
    detector: Any,
    output_dir: str | Path,
    *,
    root: Path | None = None,
    measure: bool = True,
) -> dict:
    """Score every available video with the supplied detector.

    The caller creates that detector once. A missing file or a video with no
    scored face is written to the failure log and does not become a feature row.
    """
    if any(is_synthetic_dataset(row) for row in rows):
        raise ExtractionRefused("Synthetic manifest rows cannot be extracted.")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    num_frames = int(getattr(detector, "num_frames", 20))
    feature_rows: list[dict] = []
    frame_rows: list[dict] = []
    failures: list[dict] = []
    for row in missing_videos(rows, root=root):
        failures.append(
            {
                "video_id": row["video_id"],
                "file_path": row["file_path"],
                "error": "file_not_found",
            }
        )
    absent = {row["video_id"] for row in failures}
    present = [row for row in rows if row["video_id"] not in absent]
    for row in present:
        path = resolve_video_path(row["file_path"], root=root)
        try:
            result = detector.analyze_video(path)
            frames, code = _result_frames(result)
            if not frames:
                failures.append({"video_id": row["video_id"], "file_path": row["file_path"], "error": code or "no_frames"})
                continue
            visual = measure_visual(path, num_frames=num_frames) if measure else None
            measured = features_from_frames(frames, visual=visual)
        except FeatureError as exc:
            failures.append({"video_id": row["video_id"], "file_path": row["file_path"], "error": str(exc)})
            continue
        except Exception as exc:
            failures.append(
                {
                    "video_id": row["video_id"],
                    "file_path": row["file_path"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        feature_rows.append({"video_id": row["video_id"], **measured})
        frame_rows.append({"video_id": row["video_id"], "frames": _public_frames(frames)})

    write_feature_csv(destination / "features.csv", feature_rows)
    write_frames_jsonl(destination / "frames.jsonl", frame_rows)
    write_failures(destination / "failures.csv", failures)
    metadata = {
        "measurement_source": MEASUREMENT_SOURCE,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "synthetic": False,
        "detector": "DeepfakeDetectorService",
        "video_ids": [row["video_id"] for row in feature_rows],
        "failed_video_ids": [row["video_id"] for row in failures],
    }
    write_json(destination / "extraction.json", metadata)
    return metadata
