"""Validate uploaded bytes, score them with the shared detector, and store the job."""

from __future__ import annotations

import inspect
import logging
import uuid
from dataclasses import dataclass

import cv2

logger = logging.getLogger(__name__)

from app.database.connection import utc_now
from app.database.repository import get_report, persist_analysis
from app.media.storage import delete_stored, sha256_hex, write_bytes
from app.models.deepfake_detector import DetectorResult
from app.models.video_io import inspect_video

IMAGE_MAX_BYTES = 20 * 1024 * 1024
VIDEO_MAX_BYTES = 100 * 1024 * 1024

COMPLETED_DETECTOR_STATUSES = {"scored", "no_face", "indeterminate"}


class AnalysisRejected(Exception):
    def __init__(self, status_code: int, code: str, message: str, report: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.report = report


@dataclass(frozen=True)
class _Kind:
    media_type: str
    suffix: str


def sniff_media(data: bytes) -> _Kind | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return _Kind("image", ".png")
    if data.startswith(b"\xff\xd8\xff"):
        return _Kind("image", ".jpg")
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return _Kind("image", ".gif")
    if data.startswith(b"BM"):
        return _Kind("image", ".bmp")
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return _Kind("image", ".webp")
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return _Kind("video", ".mp4")
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return _Kind("video", ".webm")
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"AVI ":
        return _Kind("video", ".avi")
    return None


def _safe_error_message(code: str | None, message: str | None) -> str | None:
    if code == "model_exception":
        return "The detector could not score this file."
    if not message:
        return None
    normalized = message.replace("\\", "/")
    if "/" in normalized or "Traceback" in message:
        return "The file could not be analyzed."
    return message


_FRAME_DETAILS = (
    "detector_confidence",
    "bbox",
    "face_width",
    "face_height",
    "face_area_ratio",
    "crop_width",
    "crop_height",
    "crop_blur",
    "quality_eligible",
    "aggregation_eligible",
    "quality_warnings",
    "quality_flags",
    "exclusion_reasons",
    "burst_id",
)


def _public_frame(frame: dict) -> dict:
    body = {
        "timestamp_seconds": frame["timestamp_seconds"],
        "face_detected": frame["status"] == "scored",
        "status": frame["status"],
        "prediction": frame["prediction"],
        "fake_score": frame["fake_score"],
    }
    for key in _FRAME_DETAILS:
        if key in frame and frame[key] is not None:
            body[key] = frame[key]
    return body


def public_detector_result(result: DetectorResult) -> dict:
    body = {
        "status": result.status,
        "media_type": result.media_type,
        "prediction": result.prediction,
        "fake_score": result.fake_score,
        "score_semantics": result.score_semantics,
        "model": {"name": result.model_name, "checkpoint_dataset": result.checkpoint_dataset},
        "error_code": result.error_code,
        "error_message": _safe_error_message(result.error_code, result.error_message),
        "warnings": list(result.warnings),
    }
    if result.aggregation_policy:
        body["aggregation_policy"] = result.aggregation_policy
    if result.aggregation_evidence:
        body["aggregation_evidence"] = result.aggregation_evidence
    if result.frame_results is not None:
        body["frames_sampled"] = result.frames_sampled
        body["frames_scored"] = result.frames_scored
        body["frames_with_faces"] = result.frames_scored
        body["aggregation_method"] = result.aggregation_method
        body["aggregate_prediction"] = result.prediction
        body["aggregate_fake_score"] = result.fake_score
        body["frame_results"] = [_public_frame(frame) for frame in result.frame_results]
    return body


def _decode(kind: _Kind, path) -> None:
    if kind.media_type == "image":
        image = cv2.imread(str(path))
        if image is None or image.size == 0:
            raise AnalysisRejected(422, "unreadable_image", "The image could not be decoded.")
        return
    stats = inspect_video(path)
    if not stats.opened or stats.frame_count <= 0 or stats.fps <= 0:
        logger.warning(
            "Rejected undecodable video %s opened=%s frames=%s fps=%s raw_frame_count=%s raw_fps=%s",
            path.name,
            stats.opened,
            stats.frame_count,
            stats.fps,
            stats.raw_frame_count,
            stats.raw_fps,
        )
        raise AnalysisRejected(422, "unreadable_video", "The video could not be decoded, so it was not scored.")


def _report(
    *,
    report_id: str,
    status: str,
    status_reason: str | None,
    media_type: str,
    asset_id: str,
    byte_size: int,
    digest: str,
    created_at: str,
    completed_at: str | None,
    result: dict | None,
) -> dict:
    return {
        "report_id": report_id,
        "job_id": report_id,
        "status": status,
        "status_reason": status_reason,
        "media_type": media_type,
        "media_asset_id": asset_id,
        "byte_size": byte_size,
        "sha256": digest,
        "created_at": created_at,
        "completed_at": completed_at,
        "result": result,
    }


def _store_failed(
    *,
    report_id: str,
    asset_id: str,
    media_type: str,
    storage_name: str | None,
    data: bytes,
    code: str,
    message: str,
    keep_file: bool,
) -> dict:
    created_at = utc_now()
    result = {
        "status": "invalid_media",
        "media_type": media_type,
        "prediction": None,
        "fake_score": None,
        "score_semantics": "raw_model_score_not_calibrated_probability",
        "error_code": code,
        "error_message": message,
        "warnings": [],
    }
    try:
        persist_analysis(
            asset_id=asset_id,
            media_type=media_type,
            storage_name=storage_name if keep_file else None,
            byte_size=len(data),
            sha256=sha256_hex(data),
            job_id=report_id,
            status="failed",
            status_reason=code,
            result=result,
            created_at=created_at,
            completed_at=None,
        )
    except Exception:
        delete_stored(storage_name)
        raise
    if not keep_file:
        delete_stored(storage_name)
    return _report(
        report_id=report_id,
        status="failed",
        status_reason=code,
        media_type=media_type,
        asset_id=asset_id,
        byte_size=len(data),
        digest=sha256_hex(data),
        created_at=created_at,
        completed_at=None,
        result=result,
    )


def _run_video(detector, path, aggregation_policy: str | None):
    method = detector.analyze_video
    policy = aggregation_policy or "video_aggregation_v2"
    try:
        accepted = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return method(path)
    if "aggregation_policy" in accepted or any(
        item.kind is inspect.Parameter.VAR_KEYWORD for item in accepted.values()
    ):
        return method(path, aggregation_policy=policy)
    return method(path)


def analyze_bytes(data: bytes, *, expected: str, detector, aggregation_policy: str | None = None) -> dict:
    if detector is None:
        raise AnalysisRejected(503, "detector_not_initialized", "The detector is not initialized.")
    limit = IMAGE_MAX_BYTES if expected == "image" else VIDEO_MAX_BYTES
    if len(data) > limit:
        raise AnalysisRejected(413, "file_too_large", "The file is larger than the limit.")
    if not data:
        raise AnalysisRejected(422, "empty_file", "The file is empty.")

    kind = sniff_media(data)
    if kind is None or kind.media_type != expected:
        raise AnalysisRejected(415, "unsupported_media_type", "The file type is not supported for this route.")

    report_id = f"rpt_{uuid.uuid4().hex[:12]}"
    asset_id = f"ma_{uuid.uuid4().hex[:12]}"
    storage_name = f"{asset_id}{kind.suffix}"
    digest = sha256_hex(data)
    path = write_bytes(storage_name, data)
    try:
        _decode(kind, path)
    except AnalysisRejected as rejected:
        report = _store_failed(
            report_id=report_id,
            asset_id=asset_id,
            media_type=kind.media_type,
            storage_name=storage_name,
            data=data,
            code=rejected.code,
            message=rejected.message,
            keep_file=False,
        )
        raise AnalysisRejected(rejected.status_code, rejected.code, rejected.message, report) from None

    try:
        if expected == "image":
            detected = detector.analyze_image(path)
        else:
            detected = _run_video(detector, path, aggregation_policy)
    except Exception:
        detected = DetectorResult(
            status="inference_error",
            media_type=expected,
            model_name=getattr(detector, "model_name", "ms_eff_gcvit_b0"),
            checkpoint_dataset=getattr(detector, "checkpoint_dataset", "ff++"),
            fake_score=None,
            prediction=None,
            device=getattr(detector, "device", "cpu"),
            processing_time=0.0,
            error_code="model_exception",
            error_message="The detector could not score this file.",
        )

    public = public_detector_result(detected)
    job_status = "completed" if detected.status in COMPLETED_DETECTOR_STATUSES else "failed"
    created_at = utc_now()
    completed_at = created_at if job_status == "completed" else None
    try:
        persist_analysis(
            asset_id=asset_id,
            media_type=kind.media_type,
            storage_name=storage_name,
            byte_size=len(data),
            sha256=digest,
            job_id=report_id,
            status=job_status,
            status_reason=detected.error_code,
            result=public,
            created_at=created_at,
            completed_at=completed_at,
        )
    except Exception:
        delete_stored(storage_name)
        raise
    return _report(
        report_id=report_id,
        status=job_status,
        status_reason=detected.error_code,
        media_type=kind.media_type,
        asset_id=asset_id,
        byte_size=len(data),
        digest=digest,
        created_at=created_at,
        completed_at=completed_at,
        result=public,
    )


def load_report(report_id: str) -> dict | None:
    return get_report(report_id)
