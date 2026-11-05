"""Compare V1 and V2 labels for recordings whose frame scores are already known.

The input is a JSON list. Each item has an id, a ground_truth string, and frames
with timestamp_seconds, fake_score, and, when available, detector_confidence and
face_area_ratio. The script does not load DeepGuard and does not measure accuracy.
One labeled recording is not an accuracy result.

Example:
    .venv\\Scripts\\python.exe backend/scripts/evaluate_video_aggregation.py backend/scripts/examples/zoo_aggregation_case.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.deepfake_detector import aggregate_video_scores  # noqa: E402
from app.models.video_aggregation import aggregate_video_v2  # noqa: E402


def _prepare(frames: list[dict]) -> list[dict]:
    prepared = []
    for frame in frames:
        score = float(frame["fake_score"])
        prepared.append(
            {
                "timestamp_seconds": float(frame["timestamp_seconds"]),
                "status": "scored",
                "fake_score": score,
                "prediction": "fake" if score >= 0.8 else "real" if score <= 0.2 else "uncertain",
                "detector_confidence": frame.get("detector_confidence"),
                "face_area_ratio": frame.get("face_area_ratio"),
            }
        )
    return prepared


def evaluate_case(case: dict) -> dict:
    frames = _prepare(case["frames"])
    scores = [frame["fake_score"] for frame in frames]
    _status, v1_prediction, _median, _code, _message = aggregate_video_scores(scores, min_valid_frames=3)
    v2 = aggregate_video_v2(frames, min_valid_frames=3)
    warnings = sorted({warning for frame in v2.frames for warning in frame.get("quality_warnings") or []})
    return {
        "id": case.get("id"),
        "ground_truth": case.get("ground_truth"),
        "v1_prediction": v1_prediction,
        "v2_prediction": v2.prediction,
        "median": v2.evidence["median"],
        "high_frame_count": v2.evidence["high_frame_count"],
        "high_burst_count": v2.evidence["high_burst_count"],
        "eligible_burst_count": v2.evidence["eligible_burst_count"],
        "quality_warnings": warnings,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: evaluate_video_aggregation.py cases.json")
    cases = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps([evaluate_case(case) for case in cases], indent=2))


if __name__ == "__main__":
    main()
