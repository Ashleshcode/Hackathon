"""Shared DeepGuard inference service.

The installed ImagePredictor.predict_img and VideoPredictor.predict_video
return 0.5 for unreadable media, a missing face, a failed crop, and several
exceptions. That value is not used as a score.

This service keeps one ImagePredictor. Video frames are sampled with OpenCV
and scored with that same predictor. VideoPredictor is not constructed.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

from deepguard.data import get_test_transforms

from app.models.video_aggregation import POLICY_V1, POLICY_V2, aggregation_method_v2, aggregate_video_v2
from app.models.video_io import inspect_video

MODEL_NAME = "ms_eff_gcvit_b0"
CHECKPOINT_DATASET = "ff++"
SCORE_SEMANTICS = "raw_model_score_not_calibrated_probability"

# Operating points copied from VideoPredictor._frame_aggregate. They are not
# a calibration of the sigmoid output.
HIGH_SCORE = 0.8
LOW_SCORE = 0.2


@dataclass
class FrameFinding:
    frame_index: int
    timestamp_seconds: float
    status: str
    fake_score: float | None
    prediction: str | None
    error_code: str | None = None
    error_message: str | None = None
    face: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        body = asdict(self)
        face = body.pop("face") or {}
        body.update(face)
        return body


@dataclass
class DetectorResult:
    status: str
    media_type: str
    model_name: str
    checkpoint_dataset: str
    fake_score: float | None
    prediction: str | None
    device: str
    processing_time: float
    error_code: str | None = None
    error_message: str | None = None
    score_semantics: str = SCORE_SEMANTICS
    frames_sampled: int | None = None
    frames_scored: int | None = None
    aggregation_method: str | None = None
    aggregation_policy: str | None = None
    aggregation_evidence: dict[str, Any] | None = None
    frame_results: list[dict[str, Any]] | None = None
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def crop_blur_variance(crop: np.ndarray) -> float | None:
    """Laplacian variance of a face crop. Diagnostic only; it does not change the score."""
    if crop is None or getattr(crop, "size", 0) == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if getattr(crop, "ndim", 0) == 3 else crop
    if gray.size == 0:
        return None
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def select_device() -> str:
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def prediction_for_score(score: float, *, high_score: float = HIGH_SCORE, low_score: float = LOW_SCORE) -> str:
    if score >= high_score:
        return "fake"
    if score <= low_score:
        return "real"
    return "uncertain"


def aggregate_video_scores(
    scores: list[float],
    *,
    min_valid_frames: int,
    high_score: float = HIGH_SCORE,
    low_score: float = LOW_SCORE,
) -> tuple[str, str | None, float | None, str | None, str | None]:
    """Return status, prediction, aggregate score, error code, and error message.

    A video is fake only when at least two valid frames reach the high score
    and the median of the valid scores is also at least 0.5. One high frame
    is not enough.
    """
    if len(scores) < min_valid_frames:
        return (
            "indeterminate",
            None,
            None,
            "insufficient_valid_frames",
            f"{len(scores)} scored face frame(s); at least {min_valid_frames} are required.",
        )

    median = float(np.median(np.asarray(scores, dtype=np.float64)))
    high_frames = sum(score >= high_score for score in scores)
    low_frames = sum(score <= low_score for score in scores)

    if high_frames >= 2 and median >= 0.5:
        prediction = "fake"
    elif high_frames == 0 and low_frames == len(scores):
        prediction = "real"
    else:
        prediction = "uncertain"
    return ("scored", prediction, median, None, None)


class DeepfakeDetectorService:
    """One FaceForensics++ MS-EffGCViT-B0 predictor for images and video frames."""

    def __init__(
        self,
        predictor: Any | None = None,
        *,
        min_valid_frames: int = 3,
        num_frames: int = 20,
        high_score: float = HIGH_SCORE,
        low_score: float = LOW_SCORE,
    ) -> None:
        if min_valid_frames < 1:
            raise ValueError("min_valid_frames must be at least 1")
        if num_frames < 1 or num_frames > 20:
            raise ValueError("num_frames must be from 1 through 20")
        self.min_valid_frames = min_valid_frames
        self.num_frames = num_frames
        self.high_score = high_score
        self.low_score = low_score
        self._lock = threading.Lock()
        self._predictor = predictor if predictor is not None else self._build_predictor()
        self.model_name = getattr(self._predictor, "model_name", MODEL_NAME)
        self.checkpoint_dataset = CHECKPOINT_DATASET
        self.device = getattr(self._predictor, "device", select_device())

    @staticmethod
    def _build_predictor() -> Any:
        from inference.image_predictor import ImagePredictor

        return ImagePredictor(
            margin_ratio=0.2,
            conf_thres=0.5,
            min_face_ratio=0.01,
            model_name=MODEL_NAME,
            dataset=CHECKPOINT_DATASET,
        )

    @property
    def predictor(self) -> Any:
        return self._predictor

    def analyze_image(self, image_path: str | Path) -> DetectorResult:
        started = time.perf_counter()
        path = Path(image_path)
        if not path.is_file():
            return self._finish(
                "image",
                "invalid_media",
                None,
                None,
                started,
                "file_not_found",
                f"Image file does not exist: {path}",
            )

        bgr = cv2.imread(str(path))
        if bgr is None or bgr.size == 0:
            return self._finish(
                "image",
                "invalid_media",
                None,
                None,
                started,
                "unreadable_image",
                "OpenCV could not decode the image.",
            )

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        finding = self._score_rgb(rgb, frame_index=0, timestamp_seconds=0.0)
        return self._finish(
            "image",
            finding.status,
            finding.fake_score,
            finding.prediction,
            started,
            finding.error_code,
            finding.error_message,
        )

    def analyze_video(self, video_path: str | Path, *, aggregation_policy: str = POLICY_V2) -> DetectorResult:
        if aggregation_policy not in {POLICY_V1, POLICY_V2}:
            raise ValueError("aggregation_policy must be video_aggregation_v1 or video_aggregation_v2")
        started = time.perf_counter()
        path = Path(video_path)
        if not path.is_file():
            return self._finish(
                "video",
                "invalid_media",
                None,
                None,
                started,
                "file_not_found",
                f"Video file does not exist: {path}",
            )

        extracted, error_code, error_message = self._extract_frames(path)
        if error_code is not None:
            return self._finish("video", "invalid_media", None, None, started, error_code, error_message)

        findings = [
            self._score_rgb(rgb, frame_index=index, timestamp_seconds=timestamp)
            for index, timestamp, rgb in extracted
        ]
        scored = [item.fake_score for item in findings if item.status == "scored" and item.fake_score is not None]
        face_frames = [item for item in findings if item.status == "no_face"]
        errors = [item for item in findings if item.status == "inference_error"]

        if scored and aggregation_policy == POLICY_V1:
            status, prediction, aggregate, error_code, error_message = aggregate_video_scores(
                scored,
                min_valid_frames=self.min_valid_frames,
                high_score=self.high_score,
                low_score=self.low_score,
            )
            frame_results = [item.as_dict() for item in findings]
            policy = POLICY_V1
            evidence = {
                "policy": POLICY_V1,
                "median": aggregate,
                "scored_frame_count": len(scored),
                "high_frame_count": sum(score >= self.high_score for score in scored),
                "decision_explanation": (
                    "V1 marks fake when at least two scored frames are at least 0.8 and the median is at least 0.5. "
                    "Quality measurements do not change this rule."
                ),
            }
        elif scored:
            decision = aggregate_video_v2(
                [item.as_dict() for item in findings],
                min_valid_frames=self.min_valid_frames,
                high_score=self.high_score,
                low_score=self.low_score,
            )
            status = decision.status
            prediction = decision.prediction
            aggregate = decision.median if decision.status == "scored" else None
            error_code = decision.error_code
            error_message = decision.error_message
            frame_results = decision.frames
            policy = decision.policy
            evidence = decision.evidence
        elif face_frames and not errors:
            status, prediction, aggregate = "no_face", None, None
            error_code, error_message = "no_face", "No sampled frame contained a usable face."
            frame_results = [item.as_dict() for item in findings]
            policy = None
            evidence = None
        elif errors:
            status, prediction, aggregate = "inference_error", None, None
            error_code = errors[0].error_code or "inference_error"
            error_message = errors[0].error_message
            frame_results = [item.as_dict() for item in findings]
            policy = None
            evidence = None
        else:
            status, prediction, aggregate = "indeterminate", None, None
            error_code, error_message = "indeterminate", "No scored face frames were produced."
            frame_results = [item.as_dict() for item in findings]
            policy = None
            evidence = None

        warnings = [
            "fake_score is a raw sigmoid output, not a calibrated probability.",
            "Frames without a usable face are excluded from aggregation.",
            "A low-quality detection remains in the report and cannot by itself mark the video fake.",
        ]
        return self._finish(
            "video",
            status,
            aggregate,
            prediction,
            started,
            error_code,
            error_message,
            frames_sampled=len(findings),
            frames_scored=len(scored),
            aggregation_policy=policy,
            aggregation_evidence=evidence,
            aggregation_method=(
                "median of scored face frames; fake requires at least two frames >= 0.8 and a median >= 0.5"
                if policy == POLICY_V1
                else aggregation_method_v2(
                    high_score=self.high_score,
                    low_score=self.low_score,
                    min_valid_frames=self.min_valid_frames,
                    burst_gap_seconds=1.0,
                )
                if policy == POLICY_V2
                else None
            ),
            frame_results=frame_results,
            warnings=warnings,
        )

    def _extract_frames(
        self, path: Path
    ) -> tuple[list[tuple[int, float, np.ndarray]], str | None, str | None]:
        stats = inspect_video(path)
        if not stats.opened:
            return [], "unreadable_video", "OpenCV could not open the video."
        if stats.frame_count <= 0 or stats.fps <= 0:
            return [], "invalid_video_metadata", "The video has no positive frame count or frame rate."
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            return [], "unreadable_video", "OpenCV could not open the video."
        try:
            frame_count = stats.frame_count
            fps = stats.fps

            sample_count = min(self.num_frames, frame_count)
            indices = sorted(
                set(np.linspace(0, frame_count - 1, num=sample_count, endpoint=True, dtype=np.int32).tolist())
            )
            extracted: list[tuple[int, float, np.ndarray]] = []
            target = 0
            last_index = indices[-1]
            for frame_index in range(last_index + 1):
                if not capture.grab():
                    break
                if frame_index != indices[target]:
                    continue
                ok, frame = capture.retrieve()
                if ok and frame is not None and frame.size > 0:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    extracted.append((frame_index, frame_index / fps, rgb))
                target += 1
                if target >= len(indices):
                    break
        finally:
            capture.release()

        if not extracted:
            return [], "unreadable_video", "OpenCV did not return any sampled frames."
        return extracted, None, None

    def _score_rgb(self, rgb: np.ndarray, *, frame_index: int, timestamp_seconds: float) -> FrameFinding:
        try:
            with self._lock:
                boxes = self._predictor.face_detector.detect_batch([rgb], [1.0])
                box = boxes[0] if boxes else []
                if len(box) == 0:
                    return FrameFinding(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        status="no_face",
                        fake_score=None,
                        prediction=None,
                        error_code="no_face",
                        error_message="No face met the detector size and confidence checks.",
                    )

                crop = self._predictor._crop_face(rgb, box)
                if crop is None or getattr(crop, "size", 0) == 0:
                    return FrameFinding(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        status="inference_error",
                        fake_score=None,
                        prediction=None,
                        error_code="crop_failed",
                        error_message="The face crop was empty or invalid.",
                    )

                transforms = get_test_transforms(img_size=self._predictor.img_size, tta_hflip=0.0)
                tensor = transforms(image=crop)["image"].unsqueeze(0).to(self._predictor.device)
                with torch.inference_mode():
                    output = self._predictor.model(tensor)
                flat = torch.sigmoid(output).reshape(-1)
                if flat.numel() != 1 or not torch.isfinite(flat).all():
                    return FrameFinding(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        status="inference_error",
                        fake_score=None,
                        prediction=None,
                        error_code="invalid_model_output",
                        error_message="The model output was not a single finite score.",
                    )
                score = float(flat.item())
                face = self._face_measurement(rgb, box, crop)
        except Exception as exc:
            return FrameFinding(
                frame_index=frame_index,
                timestamp_seconds=timestamp_seconds,
                status="inference_error",
                fake_score=None,
                prediction=None,
                error_code="model_exception",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        return FrameFinding(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            status="scored",
            fake_score=score,
            prediction=prediction_for_score(score, high_score=self.high_score, low_score=self.low_score),
            face=face,
        )

    def _face_measurement(self, rgb: np.ndarray, box: list, crop: np.ndarray) -> dict[str, Any]:
        frame_h, frame_w = rgb.shape[:2]
        xmin, ymin, xmax, ymax = (float(value) for value in list(box)[:4])
        face_w = max(0.0, xmax - xmin)
        face_h = max(0.0, ymax - ymin)
        crop_h, crop_w = crop.shape[:2]
        return {
            "detector_confidence": self._detector_confidence(rgb),
            "bbox": [xmin, ymin, xmax, ymax],
            "face_width": face_w,
            "face_height": face_h,
            "face_area_ratio": (face_w * face_h) / (frame_w * frame_h) if frame_w and frame_h else None,
            "crop_width": int(crop_w),
            "crop_height": int(crop_h),
            "crop_blur": crop_blur_variance(crop),
        }

    def _detector_confidence(self, rgb: np.ndarray) -> float | None:
        detector = getattr(self._predictor, "face_detector", None)
        model = getattr(detector, "model", None)
        conf_thres = getattr(detector, "conf_thres", None)
        if model is None or conf_thres is None:
            return None
        try:
            results = model([rgb], conf=conf_thres, verbose=False)
            data = results[0].boxes.data.cpu().numpy()
        except Exception:
            return None
        faces = data[data[:, 5] == 0] if len(data) else data
        if len(faces) == 0:
            return None
        areas = (faces[:, 2] - faces[:, 0]) * (faces[:, 3] - faces[:, 1])
        return float(faces[int(np.argmax(areas)), 4])

    def _finish(
        self,
        media_type: str,
        status: str,
        fake_score: float | None,
        prediction: str | None,
        started: float,
        error_code: str | None,
        error_message: str | None,
        **extra: Any,
    ) -> DetectorResult:
        return DetectorResult(
            status=status,
            media_type=media_type,
            model_name=self.model_name,
            checkpoint_dataset=self.checkpoint_dataset,
            fake_score=fake_score,
            prediction=prediction,
            device=self.device,
            processing_time=time.perf_counter() - started,
            error_code=error_code,
            error_message=error_message,
            **extra,
        )


_shared_service: DeepfakeDetectorService | None = None
_shared_lock = threading.Lock()


def get_shared_detector() -> DeepfakeDetectorService:
    """Return the process-wide detector, creating it on first use."""
    global _shared_service
    with _shared_lock:
        if _shared_service is None:
            _shared_service = DeepfakeDetectorService()
        return _shared_service
