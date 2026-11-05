"""Create media-analysis jobs, process them, and record the outcome.

Job statuses follow ``docs/API_CONTRACTS.md``: ``queued``, ``running``,
``completed``, ``failed``, and ``unsupported``.

* ``completed``: the detector ran. A video with no faces is still completed,
  with an ``unsupported`` aggregate prediction and a null score.
* ``failed``: the media or detector could not be processed. ``result`` is null
  and ``error`` explains why. No score is ever made up.
* ``unsupported``: the stored media is a type this pipeline does not analyse.
"""

import logging
import math
import numbers
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from app.media.aggregation import aggregate_frame_results
from app.media.interfaces import (
    ALLOWED_PREDICTIONS,
    SCORE_SEMANTICS,
    DetectionResult,
    FrameDetector,
    JobRepository,
    MediaFetchError,
    MediaStore,
)
from app.media.video_processor import VideoProcessingError, extract_video_frames

logger = logging.getLogger(__name__)

SUPPORTED_MIME_TYPES = {
    "image": {"image/jpeg", "image/png", "image/webp", "image/bmp"},
    "video": {"video/mp4", "video/quicktime", "video/x-msvideo"},
}
TEST_ONLY_MOCK_WARNING = (
    "TEST-ONLY MOCK DETECTOR: this output is not a genuine model prediction."
)


class MediaNotFoundError(Exception):
    """The requested ``media_id`` is not in storage."""


class MediaStoreUnavailableError(Exception):
    """Member 1's storage layer has not been connected yet."""


class MockDetectorRejectedError(ValueError):
    """A test mock was passed where a production detector is required."""


class _JobFailure(Exception):
    """Processing failed for a reason that is safe to show in ``error``."""


class _UnsupportedMedia(Exception):
    """The media is a type this pipeline does not analyse."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MediaJob:
    """One job. Frozen, so a reader never sees a half-updated record."""

    job_id: str
    media_id: str
    post_id: str | None
    monitor_id: str | None
    media_type: str
    status: str
    created_at: str
    result: dict[str, Any] | None = None
    error: str | None = None
    finished_at: str | None = None
    # Internal records that are not part of the job response.
    provenance_label: str | None = None
    model: dict[str, str] | None = None

    def to_response(self) -> dict[str, Any]:
        """Return the contract's job object.

        ``finished_at`` and ``error`` appear only once they apply, matching the
        contract's queued, completed, and failed examples.
        """
        response: dict[str, Any] = {
            "job_id": self.job_id,
            "media_id": self.media_id,
            "post_id": self.post_id,
            "monitor_id": self.monitor_id,
            "media_type": self.media_type,
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
        }
        if self.finished_at is not None:
            response["finished_at"] = self.finished_at
        if self.error is not None:
            response["error"] = self.error
        return response


class InMemoryJobRepository:
    """Default job storage. Jobs are lost when the backend restarts."""

    def __init__(self) -> None:
        self._jobs: dict[str, MediaJob] = {}
        self._lock = threading.Lock()

    def save(self, job: MediaJob) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> MediaJob | None:
        with self._lock:
            return self._jobs.get(job_id)


def load_image(image_path: Path) -> np.ndarray:
    """Decode an image file, raising ``_JobFailure`` if it is unreadable."""
    try:
        # np.fromfile + imdecode also handles non-ASCII Windows paths.
        data = np.fromfile(str(image_path), dtype=np.uint8)
    except OSError as exc:
        raise _JobFailure(f"Unable to read image file: {exc.strerror}") from exc

    image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    if image is None:
        raise _JobFailure("Image file is empty, corrupt, or not a supported format")
    return image


def validate_detection(detection: DetectionResult) -> DetectionResult:
    """Enforce the contract's rules on detector output before it is stored.

    * A missing face is never ``real`` or ``fake``, and has a null score.
    * ``real`` and ``fake`` need a finite score.
    * Output outside the contract fails the job rather than being guessed at.
    """
    if detection.prediction not in ALLOWED_PREDICTIONS:
        raise _JobFailure(
            f"Detector returned an invalid prediction: {detection.prediction!r}"
        )

    score = detection.fake_score
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, numbers.Real):
            raise _JobFailure(f"Detector returned a non-numeric score: {score!r}")
        score = float(score)
        if not math.isfinite(score):
            raise _JobFailure(f"Detector returned a non-finite score: {score}")

    face_count = detection.face_count
    if isinstance(face_count, bool) or not isinstance(face_count, numbers.Integral):
        raise _JobFailure(f"Detector returned an invalid face_count: {face_count!r}")
    # NumPy integers cannot be converted to JSON, so store a plain int.
    face_count = int(face_count)

    if face_count <= 0:
        warnings = tuple(detection.warnings)
        prediction = detection.prediction
        if prediction in ("real", "fake"):
            warnings += (
                f"Detector returned '{prediction}' without a face; "
                "treated as unsupported.",
            )
            prediction = "unsupported"
        return replace(
            detection,
            face_count=0,
            prediction=prediction,
            fake_score=None,
            warnings=warnings,
        )

    if detection.prediction in ("real", "fake") and score is None:
        raise _JobFailure(
            f"Detector returned '{detection.prediction}' without a score"
        )

    return replace(detection, face_count=face_count, fake_score=score)


class MediaJobService:
    """Creates and processes media jobs.

    ``media_store`` or ``detector`` may be ``None`` until Member 1's code
    exists. Jobs then report that dependency as missing, instead of pretending
    that analysis happened.
    """

    def __init__(
        self,
        job_repository: JobRepository,
        media_store: MediaStore | None = None,
        detector: FrameDetector | None = None,
        allow_test_only_detector: bool = False,
    ) -> None:
        if getattr(detector, "is_test_only_mock", False) and not allow_test_only_detector:
            raise MockDetectorRejectedError(
                "A test-only mock detector cannot be used outside the test suite"
            )
        self._jobs = job_repository
        self._media_store = media_store
        self._detector = detector
        # One detector is shared by the process, so analyse one job at a time.
        # Waiting jobs stay "queued" until they get this lock.
        self._processing_lock = threading.Lock()

    def create_job(self, media_id: str) -> MediaJob:
        """Create a queued job for media already stored with a post."""
        if self._media_store is None:
            raise MediaStoreUnavailableError(
                "Media storage is not connected to media jobs yet"
            )

        media = self._media_store.get_media(media_id)
        if media is None:
            raise MediaNotFoundError(f"media_id not found: {media_id}")

        return self._new_job(
            media_id=media.media_id,
            post_id=media.post_id,
            monitor_id=media.monitor_id,
            media_type=media.media_type,
        )

    def create_dev_upload_job(self, media_type: str, provenance_label: str) -> MediaJob:
        """Create a job for a developer upload. It belongs to no post."""
        return self._new_job(
            media_id=f"med_dev_{uuid.uuid4().hex}",
            post_id=None,
            monitor_id=None,
            media_type=media_type,
            provenance_label=provenance_label,
        )

    def get_job(self, job_id: str) -> MediaJob | None:
        return self._jobs.get(job_id)

    def process_job(self, job_id: str, local_path: Path | None = None) -> None:
        """Run a queued job. All failures are recorded on the job, not raised.

        ``local_path`` is used only by the developer upload route. Product jobs
        always resolve their file through the media store.
        """
        with self._processing_lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                logger.warning("Job %s was not processed: not queued", job_id)
                return

            job = replace(job, status="running")
            self._jobs.save(job)

            try:
                result = self._analyse(job, local_path)
                model = self._model_record()
            except _UnsupportedMedia as exc:
                self._finish(job, "unsupported", error=str(exc))
            except (_JobFailure, VideoProcessingError, MediaFetchError) as exc:
                self._finish(job, "failed", error=str(exc))
            except FileNotFoundError:
                self._finish(job, "failed", error="Media file was not found")
            except Exception as exc:
                logger.exception("Job %s failed unexpectedly", job_id)
                self._finish(
                    job,
                    "failed",
                    error=f"Unexpected processing error ({type(exc).__name__})",
                )
            else:
                self._finish(job, "completed", result=result, model=model)

    def _new_job(self, **fields: Any) -> MediaJob:
        job = MediaJob(
            job_id=f"job_{uuid.uuid4().hex}",
            status="queued",
            created_at=_utc_now(),
            **fields,
        )
        self._jobs.save(job)
        return job

    def _finish(
        self,
        job: MediaJob,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        model: dict[str, str] | None = None,
    ) -> None:
        self._jobs.save(
            replace(
                job,
                status=status,
                result=result,
                error=error,
                finished_at=_utc_now(),
                model=model,
            )
        )

    def _model_record(self) -> dict[str, str]:
        info = self._detector.model_info
        return {
            "name": info.name,
            "checkpoint_dataset": info.checkpoint_dataset,
            "version": info.version,
        }

    def _analyse(self, job: MediaJob, local_path: Path | None) -> dict[str, Any]:
        if job.media_type not in SUPPORTED_MIME_TYPES:
            raise _UnsupportedMedia(f"Unsupported media_type: {job.media_type}")

        path = local_path if local_path is not None else self._resolve_file(job)

        if self._detector is None:
            raise _JobFailure(
                "No production detector is connected, so no analysis was run"
            )

        if job.media_type == "image":
            result = self._analyse_image(path)
        else:
            result = self._analyse_video(path)

        if getattr(self._detector, "is_test_only_mock", False):
            result["warnings"].append(TEST_ONLY_MOCK_WARNING)
        if job.provenance_label is not None:
            result["warnings"].append(
                f"Developer upload labelled {job.provenance_label}. "
                "This is not a platform record."
            )
        return result

    def _resolve_file(self, job: MediaJob) -> Path:
        if self._media_store is None:
            raise _JobFailure("Media storage is not connected to media jobs yet")

        media = self._media_store.get_media(job.media_id)
        if media is None:
            raise _JobFailure(f"media_id is no longer stored: {job.media_id}")

        mime_type = media.mime_type
        if mime_type and mime_type.lower() not in SUPPORTED_MIME_TYPES[job.media_type]:
            raise _UnsupportedMedia(
                f"Unsupported {job.media_type} mime_type: {mime_type}"
            )

        return self._media_store.get_local_path(media)

    def _detect(self, image: np.ndarray) -> DetectionResult:
        try:
            detection = self._detector.analyze_image(image)
        except Exception as exc:
            logger.exception("Detector raised an exception")
            raise _JobFailure(f"Detector failed: {exc}") from exc
        return validate_detection(detection)

    def _analyse_image(self, path: Path) -> dict[str, Any]:
        detection = self._detect(load_image(path))
        warnings = list(detection.warnings)
        if detection.face_count == 0:
            warnings.append("No usable face was found in the image.")

        return {
            "model": self._model_record(),
            "face_count": detection.face_count,
            "prediction": detection.prediction,
            "fake_score": detection.fake_score,
            "score_semantics": SCORE_SEMANTICS,
            "warnings": warnings,
        }

    def _analyse_video(self, path: Path) -> dict[str, Any]:
        extraction = extract_video_frames(path)
        frame_results: list[dict[str, Any]] = []
        warnings: list[str] = []

        for frame in extraction.frames:
            detection = self._detect(frame.image)
            frame_results.append(
                {
                    "timestamp_seconds": frame.timestamp_seconds,
                    "face_detected": detection.face_count > 0,
                    "prediction": detection.prediction,
                    "fake_score": detection.fake_score,
                }
            )
            # A warning repeated by every frame is only reported once.
            warnings.extend(w for w in detection.warnings if w not in warnings)

        if extraction.failed_frame_indices:
            warnings.append(
                f"{len(extraction.failed_frame_indices)} sampled frame(s) could not "
                f"be decoded and were skipped: {extraction.failed_frame_indices}"
            )

        aggregate = aggregate_frame_results(frame_results)
        return {
            "frames_sampled": len(frame_results),
            "frames_with_faces": aggregate.frames_with_faces,
            "frame_results": frame_results,
            "aggregate_prediction": aggregate.aggregate_prediction,
            "aggregate_fake_score": aggregate.aggregate_fake_score,
            "aggregation_method": aggregate.aggregation_method,
            "score_semantics": SCORE_SEMANTICS,
            "warnings": warnings + aggregate.warnings,
        }
