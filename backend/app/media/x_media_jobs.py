"""Analysis jobs for X media already stored by the official connector.

The shared detector scores a local file when one has been linked. This module
does not download variant URLs, and it does not replace the detector's
thresholds or video aggregation.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlparse

from app.database.connection import get_media_directory, utc_now
from app.database.repository import find_x_media, get_x_media_job, save_x_media_job

VIDEO_TYPES = {"video", "animated_gif"}
IMAGE_TYPES = {"photo", "image"}


class MediaJobError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def permitted_variant(media_type: str | None, variants) -> bool:
    """A video is permitted only when the stored payload contains an MP4 variant."""
    if media_type not in VIDEO_TYPES or not isinstance(variants, list):
        return False
    for item in variants:
        if not isinstance(item, dict):
            continue
        content_type = str(item.get("content_type") or "").lower()
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        path = urlparse(url).path.lower()
        if content_type == "video/mp4" or path.endswith(".mp4"):
            return True
    return False


def _youtube(value: str | None) -> bool:
    if not value:
        return False
    host = urlparse(value).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == "youtu.be" or host.endswith("youtube.com") or host.endswith("youtube-nocookie.com")


def _local_file(storage_name: str | None) -> Path | None:
    if not storage_name or storage_name != Path(storage_name).name:
        return None
    directory = get_media_directory()
    path = directory / storage_name
    if path.is_file() and path.parent == directory:
        return path
    return None


def _contract_result(detected) -> dict | None:
    if detected.status not in {"scored", "no_face", "indeterminate"}:
        return None
    prediction = detected.prediction
    score = detected.fake_score
    if detected.status == "no_face":
        prediction = "unsupported"
        score = None
    elif detected.status == "indeterminate":
        prediction = "uncertain"
        score = None
    body = {
        "model": {
            "name": detected.model_name,
            "checkpoint_dataset": detected.checkpoint_dataset,
            "version": None,
        },
        "prediction": prediction,
        "fake_score": score,
        "score_semantics": detected.score_semantics,
        "detector_status": detected.status,
        "warnings": list(detected.warnings),
    }
    if detected.frame_results is not None:
        body["frames_sampled"] = detected.frames_sampled
        body["frames_with_faces"] = detected.frames_scored
        body["aggregate_prediction"] = prediction
        body["aggregate_fake_score"] = score
        body["aggregation_method"] = detected.aggregation_method
        if getattr(detected, "aggregation_policy", None):
            body["aggregation_policy"] = detected.aggregation_policy
        if getattr(detected, "aggregation_evidence", None):
            body["aggregation_evidence"] = detected.aggregation_evidence
        body["frame_results"] = [
            {
                "timestamp_seconds": frame["timestamp_seconds"],
                "face_detected": frame["status"] == "scored",
                "prediction": frame["prediction"],
                "fake_score": frame["fake_score"],
                **{
                    key: frame[key]
                    for key in (
                        "detector_confidence",
                        "bbox",
                        "face_width",
                        "face_height",
                        "face_area_ratio",
                        "crop_width",
                        "crop_height",
                        "quality_eligible",
                        "quality_warnings",
                        "burst_id",
                    )
                    if key in frame and frame[key] is not None
                },
            }
            for frame in detected.frame_results
        ]
    return body


def _response(
    *,
    job_id: str,
    post_id: str,
    media_key: str,
    media_type: str | None,
    variant_access: str,
    status: str,
    status_reason: str | None,
    result: dict | None,
    created_at: str,
) -> dict:
    return {
        "job_id": job_id,
        "post_id": post_id,
        "media_key": media_key,
        "platform": "x",
        "media_type": media_type,
        "variant_access": variant_access,
        "status": status,
        "status_reason": status_reason,
        "result": result,
        "created_at": created_at,
    }


def create_x_media_job(post_id: str, media_key: str, detector) -> dict:
    if "://" in post_id or "://" in media_key:
        raise MediaJobError(422, "url_not_accepted", "post_id and media_key must be platform ids, not URLs.")
    media = find_x_media(post_id, media_key)
    if media is None:
        raise MediaJobError(404, "media_not_found", "No stored X media matches that post_id and media_key.")
    if _youtube(media["url"]) or _youtube(media["preview_image_url"]):
        raise MediaJobError(
            422,
            "youtube_audiovisual_analysis_not_permitted",
            "YouTube audiovisual content is not analysed.",
        )

    media_type = media["media_type"]
    video = media_type in VIDEO_TYPES
    image = media_type in IMAGE_TYPES
    has_variant = permitted_variant(media_type, media["variants"])
    has_image_url = image and isinstance(media["url"], str) and media["url"].startswith(("http://", "https://"))
    variant_access = "present" if has_variant or has_image_url else "absent"
    created_at = utc_now()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    status = "unavailable"
    status_reason = "x_api_did_not_provide_a_permitted_variant"
    result = None
    completed_at = None

    if variant_access == "present":
        local_path = _local_file(media["storage_name"])
        if media["storage_name"] and local_path is None:
            status = "failed"
            status_reason = "media_file_missing"
        elif local_path is None:
            status = "unavailable"
            status_reason = "permitted_media_not_retrieved"
        elif detector is None:
            status = "failed"
            status_reason = "detector_not_initialized"
        else:
            try:
                if video:
                    detected = detector.analyze_video(local_path)
                else:
                    detected = detector.analyze_image(local_path)
            except Exception:
                detected = None
            if detected is None:
                status = "failed"
                status_reason = "detector_failed"
            else:
                result = _contract_result(detected)
                if result is None:
                    status = "failed"
                    status_reason = detected.error_code or "analysis_failed"
                else:
                    status = "completed"
                    status_reason = None
                    completed_at = created_at
    elif media_type not in VIDEO_TYPES | IMAGE_TYPES:
        status = "unsupported"
        status_reason = "unsupported_media_type"

    response = _response(
        job_id=job_id,
        post_id=post_id,
        media_key=media_key,
        media_type=media_type,
        variant_access=variant_access,
        status=status,
        status_reason=status_reason,
        result=result,
        created_at=created_at,
    )
    return save_x_media_job(
        {
            "job_id": job_id,
            "campaign_id": media["campaign_id"],
            "post_id": post_id,
            "status": status,
            "status_reason": status_reason,
            "created_at": created_at,
            "completed_at": completed_at,
            "response": response,
        }
    )


def load_x_media_job(job_id: str) -> dict | None:
    return get_x_media_job(job_id)
