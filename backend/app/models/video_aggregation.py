"""Versioned video decisions. Frame scores are inputs; this module does not run the model.

V1 is the policy already stored on older reports: fake when at least two scores
are at or above 0.8 and the median is at least 0.5. Retrieval returns that
stored result unchanged.

V2 is used for new analyses. A video is fake only when the median itself is at
least 0.8, the high scores form at least two bursts separated by more than
``burst_gap_seconds``, enough scored frames are quality-eligible, and a fake
label does not rest only on low-quality detections. Real still requires every
scored frame to be at or below 0.2. Every other case is uncertain.

A high-scoring frame joins the previous burst when its timestamp is within
``burst_gap_seconds`` of that burst's previous high frame. The 8-second tab
capture samples about 0.41 seconds apart, so the default gap of 1.0 seconds
keeps those neighbors in one burst and splits the zoo recording's later group
at about 2.5 seconds.

A fake label needs two pieces of temporal evidence. Two separate
quality-eligible bursts supply that. One burst also supplies it when its first
and last high scores are more than ``sustained_burst_seconds`` apart, because
the high scores are then a sustained run rather than one brief cluster. The
zoo clusters last less than a second, so neither one is sustained.

Quality uses the detector's own acceptance floors, raised by documented
factors. With the installed defaults, a face is eligible for fake evidence
when detector confidence is at least 0.65 (0.5 + 0.15) and the face covers at
least 0.02 of the frame (0.01 × 2). A detection that only just clears the
detector cannot support a fake verdict. Ineligible frames stay in the report
with a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

POLICY_V1 = "video_aggregation_v1"
POLICY_V2 = "video_aggregation_v2"
BURST_GAP_SECONDS = 1.0
SUSTAINED_BURST_SECONDS = 2.0
QUALITY_CONFIDENCE_MARGIN = 0.15
QUALITY_AREA_MULTIPLE = 2.0
DETECTOR_CONFIDENCE_FLOOR = 0.5
DETECTOR_MIN_FACE_RATIO = 0.01


@dataclass
class AggregationDecision:
    policy: str
    status: str
    prediction: str | None
    median: float | None
    error_code: str | None = None
    error_message: str | None = None
    evidence: dict = field(default_factory=dict)
    frames: list[dict] = field(default_factory=list)


def quality_thresholds(
    *,
    confidence_floor: float = DETECTOR_CONFIDENCE_FLOOR,
    confidence_margin: float = QUALITY_CONFIDENCE_MARGIN,
    min_face_ratio: float = DETECTOR_MIN_FACE_RATIO,
    area_multiple: float = QUALITY_AREA_MULTIPLE,
) -> tuple[float, float]:
    return confidence_floor + confidence_margin, min_face_ratio * area_multiple


def assess_frame_quality(
    frame: dict,
    *,
    min_confidence: float,
    min_area_ratio: float,
) -> tuple[bool, list[str]]:
    """Return whether a scored face may support a fake verdict, and why not."""
    if frame.get("status") != "scored" or frame.get("fake_score") is None:
        return False, []
    warnings: list[str] = []
    confidence = frame.get("detector_confidence")
    area_ratio = frame.get("face_area_ratio")
    if confidence is None or area_ratio is None:
        return False, ["quality_not_measured"]
    if float(confidence) < min_confidence:
        warnings.append("low_detector_confidence")
    if float(area_ratio) < min_area_ratio:
        warnings.append("face_area_near_minimum")
    return not warnings, warnings


def assign_high_score_bursts(
    frames: list[dict],
    *,
    high_score: float,
    gap_seconds: float,
) -> int:
    """Write burst_id onto high-scoring frames. Return the number of bursts."""
    ordered = sorted(
        (
            frame
            for frame in frames
            if frame.get("status") == "scored" and frame.get("fake_score") is not None and float(frame["fake_score"]) >= high_score
        ),
        key=lambda frame: float(frame.get("timestamp_seconds") or 0.0),
    )
    burst_id = -1
    previous = None
    for frame in ordered:
        timestamp = float(frame.get("timestamp_seconds") or 0.0)
        if previous is None or timestamp - previous > gap_seconds:
            burst_id += 1
        frame["burst_id"] = burst_id
        previous = timestamp
    return burst_id + 1


def _burst_evidence(frames: list[dict], *, sustained_seconds: float) -> tuple[int, int, int]:
    grouped: dict[int, list[dict]] = {}
    for frame in frames:
        if frame.get("burst_id") is None or not frame.get("quality_eligible"):
            continue
        grouped.setdefault(int(frame["burst_id"]), []).append(frame)
    eligible = 0
    sustained = 0
    evidence = 0
    for group in grouped.values():
        eligible += 1
        timestamps = [float(frame["timestamp_seconds"]) for frame in group]
        if max(timestamps) - min(timestamps) > sustained_seconds:
            sustained += 1
            evidence += 2
        else:
            evidence += 1
    return eligible, sustained, evidence


def aggregate_video_v2(
    frames: list[dict],
    *,
    min_valid_frames: int,
    high_score: float = 0.8,
    low_score: float = 0.2,
    burst_gap_seconds: float = BURST_GAP_SECONDS,
    sustained_burst_seconds: float = SUSTAINED_BURST_SECONDS,
    min_confidence: float | None = None,
    min_area_ratio: float | None = None,
) -> AggregationDecision:
    """Decide a video label from existing frame scores. Does not rescore frames."""
    if min_confidence is None or min_area_ratio is None:
        default_confidence, default_area = quality_thresholds()
        min_confidence = default_confidence if min_confidence is None else min_confidence
        min_area_ratio = default_area if min_area_ratio is None else min_area_ratio

    annotated = [dict(frame) for frame in frames]
    for frame in annotated:
        eligible, warnings = assess_frame_quality(frame, min_confidence=min_confidence, min_area_ratio=min_area_ratio)
        if frame.get("status") == "scored" and frame.get("fake_score") is not None:
            frame["quality_eligible"] = eligible
            frame["quality_warnings"] = warnings
        else:
            frame["quality_eligible"] = False
            frame["quality_warnings"] = []
            frame["burst_id"] = None

    burst_count = assign_high_score_bursts(annotated, high_score=high_score, gap_seconds=burst_gap_seconds)
    for frame in annotated:
        frame.setdefault("burst_id", None)

    scored = [frame for frame in annotated if frame.get("status") == "scored" and frame.get("fake_score") is not None]
    scores = [float(frame["fake_score"]) for frame in scored]
    median = float(np.median(np.asarray(scores, dtype=np.float64))) if scores else None
    high_frames = [frame for frame in scored if float(frame["fake_score"]) >= high_score]
    eligible_frames = [frame for frame in scored if frame.get("quality_eligible")]
    eligible_bursts, sustained_bursts, evidence_count = _burst_evidence(
        annotated,
        sustained_seconds=sustained_burst_seconds,
    )
    low_only = bool(high_frames) and all(not frame.get("quality_eligible") for frame in high_frames)

    evidence = {
        "policy": POLICY_V2,
        "median": median,
        "high_frame_count": len(high_frames),
        "high_burst_count": burst_count,
        "eligible_burst_count": eligible_bursts,
        "sustained_burst_count": sustained_bursts,
        "temporal_evidence_count": evidence_count,
        "sustained_burst_seconds": sustained_burst_seconds,
        "scored_frame_count": len(scored),
        "quality_eligible_frame_count": len(eligible_frames),
        "min_valid_frames": min_valid_frames,
        "high_score": high_score,
        "low_score": low_score,
        "median_fake_minimum": high_score,
        "burst_gap_seconds": burst_gap_seconds,
        "quality_min_confidence": min_confidence,
        "quality_min_area_ratio": min_area_ratio,
        "low_quality_only_high_scores": low_only,
        "rejected_reasons": [],
    }

    if len(scored) < min_valid_frames:
        evidence["rejected_reasons"] = ["insufficient_valid_frames"]
        return AggregationDecision(
            policy=POLICY_V2,
            status="indeterminate",
            prediction="uncertain",
            median=None,
            error_code="insufficient_valid_frames",
            error_message=f"{len(scored)} scored face frame(s); at least {min_valid_frames} are required.",
            evidence=evidence,
            frames=annotated,
        )

    reasons: list[str] = []
    fake = True
    if median is None or median < high_score:
        fake = False
        reasons.append("median_below_fake_minimum")
    if evidence_count < 2:
        fake = False
        reasons.append("fewer_than_two_temporal_evidence")
    if len(eligible_frames) < min_valid_frames:
        fake = False
        reasons.append("insufficient_quality_eligible_frames")
    if low_only:
        fake = False
        reasons.append("high_scores_are_low_quality_only")

    if fake:
        prediction = "fake"
    elif scores and all(score <= low_score for score in scores):
        prediction = "real"
    else:
        prediction = "uncertain"
    evidence["rejected_reasons"] = reasons
    return AggregationDecision(
        policy=POLICY_V2,
        status="scored",
        prediction=prediction,
        median=median,
        evidence=evidence,
        frames=annotated,
    )


def aggregation_method_v2(
    *,
    high_score: float,
    low_score: float,
    min_valid_frames: int,
    burst_gap_seconds: float,
) -> str:
    return (
        "video_aggregation_v2 median of scored face frames; "
        f"fake requires a median >= {high_score}, either two high-score bursts "
        f"separated by more than {burst_gap_seconds} seconds or one burst lasting "
        f"more than {SUSTAINED_BURST_SECONDS} seconds, at least {min_valid_frames} "
        "quality-eligible scored frames, and high-score evidence that is not only "
        f"low-quality detections; real requires every scored frame <= {low_score}; "
        "otherwise uncertain. Low-quality frames remain in the report."
    )
