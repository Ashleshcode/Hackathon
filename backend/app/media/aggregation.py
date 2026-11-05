"""Combine frame-level detector results into one video-level result.

The rule (``AGGREGATION_METHOD``):

1. A frame is *usable* if it has a face, a ``real`` or ``fake`` prediction, and
   a raw score. Frames without a usable face never contribute a score.
2. With fewer than ``MIN_USABLE_FRAMES`` usable frames there is not enough
   evidence: the prediction is ``uncertain`` (``unsupported`` when no frame has
   a face) and the aggregate score is ``None``.
3. Otherwise a label needs at least 2/3 of all frames *with a face*. Uncertain
   face frames stay in that denominator, so they weaken both labels. One fake
   frame can therefore never make the whole video fake.
4. Conflicting frames that reach neither 2/3 threshold give ``uncertain``.
5. The aggregate score is the median raw score of the usable frames. It is
   still a raw model score, not a calibrated probability.
"""

import statistics
from dataclasses import dataclass
from typing import Any

AGGREGATION_METHOD = "two_thirds_of_face_frames_median_raw_score_v1"
MIN_USABLE_FRAMES = 3
LABEL_SHARE_THRESHOLD = 2 / 3


@dataclass(frozen=True)
class VideoAggregate:
    frames_with_faces: int
    aggregate_prediction: str
    aggregate_fake_score: float | None
    aggregation_method: str
    warnings: list[str]


def aggregate_frame_results(frame_results: list[dict[str, Any]]) -> VideoAggregate:
    """Apply the rule in the module docstring to a video's frame results."""
    frames_sampled = len(frame_results)
    face_frames = [frame for frame in frame_results if frame["face_detected"]]
    usable_frames = [
        frame
        for frame in face_frames
        if frame["prediction"] in ("real", "fake")
        and frame["fake_score"] is not None
    ]
    fake_count = sum(frame["prediction"] == "fake" for frame in usable_frames)
    real_count = len(usable_frames) - fake_count

    # The contract has no separate field for this, so the counts travel with
    # the method name: "Record the aggregation method and the number of usable
    # frames."
    method = (
        f"{AGGREGATION_METHOD}: usable_frames={len(usable_frames)}, "
        f"frames_with_faces={len(face_frames)}, frames_sampled={frames_sampled}, "
        f"fake_frames={fake_count}, real_frames={real_count}, "
        f"min_usable_frames={MIN_USABLE_FRAMES}, label_share_threshold=2/3"
    )
    warnings: list[str] = []

    if not face_frames:
        warnings.append(
            f"No usable face was found in any of the {frames_sampled} sampled "
            "frames, so the video cannot be assessed."
        )
        return VideoAggregate(0, "unsupported", None, method, warnings)

    if len(usable_frames) < MIN_USABLE_FRAMES:
        warnings.append(
            f"Only {len(usable_frames)} usable frame(s) were found, and at least "
            f"{MIN_USABLE_FRAMES} are required for a video-level result."
        )
        return VideoAggregate(len(face_frames), "uncertain", None, method, warnings)

    if fake_count / len(face_frames) >= LABEL_SHARE_THRESHOLD:
        prediction = "fake"
    elif real_count / len(face_frames) >= LABEL_SHARE_THRESHOLD:
        prediction = "real"
    else:
        prediction = "uncertain"
        warnings.append(
            f"Frame results do not agree ({fake_count} fake, {real_count} real, "
            f"{len(face_frames) - len(usable_frames)} other, of "
            f"{len(face_frames)} frames with a face), so no video-level label "
            "was assigned."
        )

    if len(usable_frames) * 2 < frames_sampled:
        warnings.append(
            f"Only {len(usable_frames)} of {frames_sampled} sampled frames were "
            "usable, so this result covers a limited part of the video."
        )

    score = statistics.median(frame["fake_score"] for frame in usable_frames)
    return VideoAggregate(len(face_frames), prediction, score, method, warnings)
