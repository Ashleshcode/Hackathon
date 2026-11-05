"""The production V1 rule, used only as a comparison baseline."""

from __future__ import annotations

from app.models.deepfake_detector import aggregate_video_scores


def v1_prediction(frame_results: list[dict], *, min_valid_frames: int = 3) -> str:
    """Return the stored V1 rule's label. Indeterminate stays uncertain."""
    scores = []
    for frame in frame_results:
        score = frame.get("fake_score")
        if frame.get("status") not in (None, "scored") or score is None:
            continue
        if frame.get("status") is None and frame.get("face_detected") is not True:
            continue
        scores.append(float(score))
    status, prediction, _median, _code, _message = aggregate_video_scores(scores, min_valid_frames=min_valid_frames)
    if status != "scored" or prediction is None:
        return "uncertain"
    return prediction
