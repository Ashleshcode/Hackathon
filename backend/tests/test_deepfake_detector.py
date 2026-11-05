import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch

from backend.app.models.deepfake_detector import (
    DeepfakeDetectorService,
    aggregate_video_scores,
    crop_blur_variance,
    get_shared_detector,
    prediction_for_score,
)
from backend.app.models.video_aggregation import POLICY_V1, POLICY_V2

SAMPLES = Path(r"D:\Hackathon\artifacts\deepguard-samples")
REAL_IMAGE = SAMPLES / "western_real_1.JPG"
FAKE_IMAGE = SAMPLES / "western_fake_1.JPG"


class ScriptedFaces:
    def __init__(self, box):
        self.box = box

    def detect_batch(self, frames, scales):
        return [self.box for _ in frames]


class ScriptedPredictor:
    def __init__(self, model, box=None, crop_result="image"):
        self.model = model
        self.face_detector = ScriptedFaces([1, 1, 20, 20] if box is None else box)
        self.img_size = [32, 32]
        self.device = "cpu"
        self.model_name = "ms_eff_gcvit_b0"
        self.margin_ratio = 0.0
        self.crop_result = crop_result

    def _crop_face(self, img, bbox):
        if self.crop_result == "none":
            return None
        return img


class TensorModel(torch.nn.Module):
    def __init__(self, value: float) -> None:
        super().__init__()
        self.value = value

    def forward(self, batch):
        return torch.full((batch.shape[0], 1), self.value)


@pytest.fixture(scope="module")
def detector():
    if not REAL_IMAGE.is_file() or not FAKE_IMAGE.is_file():
        pytest.skip("Official DeepGuard sample images are not available")
    return get_shared_detector()


def test_prediction_thresholds():
    assert prediction_for_score(0.8) == "fake"
    assert prediction_for_score(0.2) == "real"
    assert prediction_for_score(0.5) == "uncertain"


def test_one_high_frame_does_not_make_a_video_fake():
    status, prediction, score, error_code, _message = aggregate_video_scores(
        [0.99, 0.05, 0.04],
        min_valid_frames=3,
    )
    assert status == "scored"
    assert prediction == "uncertain"
    assert score == pytest.approx(0.05)
    assert error_code is None


def test_two_high_frames_can_mark_a_video_fake():
    status, prediction, score, _error_code, _message = aggregate_video_scores(
        [0.91, 0.95, 0.2],
        min_valid_frames=3,
    )
    assert status == "scored"
    assert prediction == "fake"
    assert score == pytest.approx(0.91)


def test_too_few_faces_are_indeterminate():
    status, prediction, score, error_code, _message = aggregate_video_scores(
        [0.99, 0.99],
        min_valid_frames=3,
    )
    assert status == "indeterminate"
    assert prediction is None
    assert score is None
    assert error_code == "insufficient_valid_frames"


def test_shared_detector_is_created_once(detector):
    again = get_shared_detector()
    assert again is detector
    assert again.predictor is detector.predictor
    assert again.device == "cuda:0"


def test_authentic_and_manipulated_samples_in_sequence(detector):
    authentic = detector.analyze_image(REAL_IMAGE)
    manipulated = detector.analyze_image(FAKE_IMAGE)

    assert authentic.status == "scored"
    assert authentic.prediction == "real"
    assert authentic.fake_score is not None
    assert authentic.fake_score < 0.2
    assert authentic.device == "cuda:0"
    assert authentic.model_name == "ms_eff_gcvit_b0"
    assert authentic.checkpoint_dataset == "ff++"
    assert authentic.processing_time > 0

    assert manipulated.status == "scored"
    assert manipulated.fake_score is not None
    assert manipulated.fake_score > 0.5
    assert manipulated.prediction in {"fake", "uncertain"}
    assert manipulated.prediction != "real"
    assert detector.predictor is get_shared_detector().predictor


def test_corrupted_image_is_invalid(detector, tmp_path):
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"this is not an image")
    result = detector.analyze_image(path)
    assert result.status == "invalid_media"
    assert result.fake_score is None
    assert result.prediction is None
    assert result.error_code == "unreadable_image"


def test_missing_image_is_invalid(detector, tmp_path):
    result = detector.analyze_image(tmp_path / "missing.jpg")
    assert result.status == "invalid_media"
    assert result.error_code == "file_not_found"
    assert result.fake_score is None


def test_no_face_image_is_not_a_half_score(detector, tmp_path):
    path = tmp_path / "blank.jpg"
    cv2.imwrite(str(path), np.full((240, 320, 3), 40, dtype=np.uint8))
    result = detector.analyze_image(path)
    assert result.status == "no_face"
    assert result.fake_score is None
    assert result.prediction is None
    assert result.error_code == "no_face"


def test_model_exception_is_not_a_half_score(tmp_path):
    class Exploding(torch.nn.Module):
        def forward(self, batch):
            raise RuntimeError("forced failure")

    service = DeepfakeDetectorService(predictor=ScriptedPredictor(Exploding()), min_valid_frames=1, num_frames=1)
    path = tmp_path / "face.jpg"
    cv2.imwrite(str(path), np.full((64, 64, 3), 180, dtype=np.uint8))
    result = service.analyze_image(path)
    assert result.status == "inference_error"
    assert result.error_code == "model_exception"
    assert result.fake_score is None


def test_failed_crop_is_not_a_half_score(tmp_path):
    predictor = ScriptedPredictor(TensorModel(0.0), crop_result="none")
    service = DeepfakeDetectorService(predictor=predictor, min_valid_frames=1, num_frames=1)
    path = tmp_path / "face.jpg"
    cv2.imwrite(str(path), np.full((64, 64, 3), 180, dtype=np.uint8))
    result = service.analyze_image(path)
    assert result.status == "inference_error"
    assert result.error_code == "crop_failed"
    assert result.fake_score is None


def test_exact_model_half_is_uncertain_not_indeterminate(tmp_path):
    service = DeepfakeDetectorService(
        predictor=ScriptedPredictor(TensorModel(0.0)),
        min_valid_frames=1,
        num_frames=1,
    )
    path = tmp_path / "face.jpg"
    cv2.imwrite(str(path), np.full((64, 64, 3), 180, dtype=np.uint8))
    result = service.analyze_image(path)
    assert result.status == "scored"
    assert result.prediction == "uncertain"
    assert result.fake_score == pytest.approx(0.5)


def test_selecting_v1_keeps_the_old_decision_on_the_same_scores(tmp_path):
    service = DeepfakeDetectorService(
        predictor=ScriptedPredictor(TensorModel(4.0)),
        min_valid_frames=3,
        num_frames=4,
    )
    path = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 8, (64, 64))
    assert writer.isOpened()
    image = np.full((64, 64, 3), 140, dtype=np.uint8)
    for _ in range(8):
        assert writer.write(image)
    writer.release()

    v1 = service.analyze_video(path, aggregation_policy=POLICY_V1)
    v2 = service.analyze_video(path, aggregation_policy=POLICY_V2)
    assert v1.aggregation_policy == POLICY_V1
    assert v1.prediction == "fake"
    assert v1.fake_score == pytest.approx(float(torch.sigmoid(torch.tensor(4.0))))
    assert [frame["fake_score"] for frame in v1.frame_results] == [frame["fake_score"] for frame in v2.frame_results]
    assert all(frame["crop_blur"] is not None for frame in v1.frame_results)
    assert v2.aggregation_policy == POLICY_V2
    assert v2.prediction == "uncertain"
    assert v2.aggregation_evidence["profile_pose_measured"] is False
    blur = crop_blur_variance(image)
    assert blur == pytest.approx(crop_blur_variance(image))
    assert blur >= 0


def test_sequential_calls_do_not_overlap_on_the_model(tmp_path):
    class TrackingModel(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.active = 0
            self.max_active = 0
            self.guard = threading.Lock()

        def forward(self, batch):
            with self.guard:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.05)
            with self.guard:
                self.active -= 1
            return torch.zeros(batch.shape[0], 1)

    model = TrackingModel()
    service = DeepfakeDetectorService(predictor=ScriptedPredictor(model), min_valid_frames=1, num_frames=1)
    path = tmp_path / "face.jpg"
    cv2.imwrite(str(path), np.full((64, 64, 3), 90, dtype=np.uint8))
    errors = []

    def run():
        try:
            result = service.analyze_image(path)
            if result.status != "scored":
                errors.append(result.status)
        except Exception as exc:  # pragma: no cover - reported through errors
            errors.append(str(exc))

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert model.max_active == 1
