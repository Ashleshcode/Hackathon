"""One feature vector per video, taken from an existing detector result."""

from __future__ import annotations

from typing import Any

import numpy as np

from app.experiments.deepfake_rf.schema import FEATURE_COLUMNS
from app.models.deepfake_detector import HIGH_SCORE, LOW_SCORE
from app.models.video_aggregation import BURST_GAP_SECONDS, assign_high_score_bursts


class FeatureError(ValueError):
    """The detector result does not contain enough scored frames to measure."""


def _scored(frame: dict) -> bool:
    score = frame.get("fake_score")
    if score is None:
        return False
    try:
        value = float(score)
    except (TypeError, ValueError):
        return False
    if not np.isfinite(value):
        return False
    status = frame.get("status")
    if status == "scored":
        return True
    return status is None and frame.get("face_detected") is True


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _timeline_means(scores: list[float], times: list[float]) -> tuple[float | None, float | None, float | None]:
    start = min(times)
    span = max(times) - start
    if span <= 0:
        return None, None, None
    buckets: list[list[float]] = [[], [], []]
    for score, timestamp in zip(scores, times):
        position = (timestamp - start) / span
        if position < (1.0 / 3.0):
            buckets[0].append(score)
        elif position < (2.0 / 3.0):
            buckets[1].append(score)
        else:
            buckets[2].append(score)
    return _mean(buckets[0]), _mean(buckets[1]), _mean(buckets[2])


def _burst_durations(frames: list[dict]) -> list[float]:
    copies = []
    for frame in frames:
        body = dict(frame)
        if _scored(frame):
            body["status"] = "scored"
        copies.append(body)
    assign_high_score_bursts(copies, high_score=HIGH_SCORE, gap_seconds=BURST_GAP_SECONDS)
    grouped: dict[int, list[float]] = {}
    for frame in copies:
        if frame.get("burst_id") is None:
            continue
        grouped.setdefault(int(frame["burst_id"]), []).append(float(frame.get("timestamp_seconds") or 0.0))
    return [max(times) - min(times) for times in grouped.values()]


def _max_consecutive_high(frames: list[dict]) -> int:
    ordered = sorted(frames, key=lambda frame: float(frame.get("timestamp_seconds") or 0.0))
    longest = 0
    current = 0
    for frame in ordered:
        score = frame.get("fake_score")
        high = _scored(frame) and float(score) >= HIGH_SCORE
        if high:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _optional_floats(frames: list[dict], key: str) -> list[float]:
    values: list[float] = []
    for frame in frames:
        if not _scored(frame):
            continue
        raw = frame.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            values.append(value)
    return values


def features_from_frames(
    frame_results: list[dict],
    *,
    visual: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    """Measure one video. Raises FeatureError when no frame has a raw score."""
    if not frame_results:
        raise FeatureError("The detector returned no frames.")
    scored_frames = [frame for frame in frame_results if _scored(frame)]
    if not scored_frames:
        raise FeatureError("No sampled frame has a raw score.")

    ordered = sorted(scored_frames, key=lambda frame: float(frame.get("timestamp_seconds") or 0.0))
    scores = [float(frame["fake_score"]) for frame in ordered]
    times = [float(frame.get("timestamp_seconds") or 0.0) for frame in ordered]
    array = np.asarray(scores, dtype=np.float64)
    steps = [abs(scores[index] - scores[index - 1]) for index in range(1, len(scores))]
    durations = _burst_durations(ordered)
    first, middle, last = _timeline_means(scores, times)
    confidences = _optional_floats(frame_results, "detector_confidence")
    areas = _optional_floats(frame_results, "face_area_ratio")
    crop_widths = _optional_floats(frame_results, "crop_width")
    crop_heights = _optional_floats(frame_results, "crop_height")
    visual = visual or {}

    measured: dict[str, float | None] = {
        "score_mean": float(np.mean(array)),
        "score_median": float(np.median(array)),
        "score_min": float(np.min(array)),
        "score_max": float(np.max(array)),
        "score_std": float(np.std(array)),
        "score_iqr": float(np.percentile(array, 75) - np.percentile(array, 25)),
        "fraction_score_ge_0_8": float(np.mean(array >= HIGH_SCORE)),
        "fraction_score_le_0_2": float(np.mean(array <= LOW_SCORE)),
        "fraction_score_uncertain": float(np.mean((array > LOW_SCORE) & (array < HIGH_SCORE))),
        "high_burst_count": float(len(durations)),
        "max_consecutive_high_frames": float(_max_consecutive_high(frame_results)),
        "mean_high_burst_duration_seconds": _mean(durations),
        "score_mean_abs_step": _mean(steps),
        "score_first_third_mean": first,
        "score_middle_third_mean": middle,
        "score_last_third_mean": last,
        "mean_detector_confidence": _mean(confidences),
        "min_face_area_ratio": float(np.min(areas)) if areas else None,
        "median_face_area_ratio": float(np.median(np.asarray(areas, dtype=np.float64))) if areas else None,
        "mean_crop_width": _mean(crop_widths),
        "mean_crop_height": _mean(crop_heights),
        "usable_face_fraction": float(len(scored_frames) / len(frame_results)),
        "sampled_frame_count": float(len(frame_results)),
        "scored_frame_count": float(len(scored_frames)),
    }
    for key in FEATURE_COLUMNS:
        if key in measured:
            continue
        value = visual.get(key)
        if value is None:
            measured[key] = None
            continue
        number = float(value)
        measured[key] = number if np.isfinite(number) else None
    return {key: measured[key] for key in FEATURE_COLUMNS}
