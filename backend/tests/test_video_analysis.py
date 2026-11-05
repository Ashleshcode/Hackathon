from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.app.models.deepfake_detector import DeepfakeDetectorService, get_shared_detector
from backend.app.models.tta_experiment import compare_transforms
from backend.app.models.video_aggregation import compare_v1_and_v2

SAMPLES = Path(r"D:\Hackathon\artifacts\deepguard-samples")
REAL_IMAGE = SAMPLES / "western_real_1.JPG"
REAL_VIDEO = SAMPLES / "western_real.mp4"
FAKE_VIDEO = SAMPLES / "western_fake.mp4"


@pytest.fixture(scope="module")
def detector():
    if not REAL_VIDEO.is_file() or not FAKE_VIDEO.is_file() or not REAL_IMAGE.is_file():
        pytest.skip("Official DeepGuard samples are not available")
    return get_shared_detector()


def _write_video(path: Path, frames: list[np.ndarray], fps: float = 10.0) -> None:
    height, width = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        pytest.fail("OpenCV could not create a test video")
    for frame in frames:
        writer.write(frame)
    writer.release()


def test_official_videos_keep_frame_timestamps(detector):
    authentic = detector.analyze_video(REAL_VIDEO)
    manipulated = detector.analyze_video(FAKE_VIDEO)

    assert authentic.status == "scored"
    assert authentic.prediction == "uncertain"
    assert authentic.fake_score is not None
    assert authentic.fake_score < 0.2
    assert authentic.frame_results is not None
    assert max(item["fake_score"] for item in authentic.frame_results) > 0.2
    assert all(item["fake_score"] < 0.8 for item in authentic.frame_results)
    assert authentic.frames_sampled == 20
    assert authentic.frames_scored == 20
    timestamps = [item["timestamp_seconds"] for item in authentic.frame_results]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 20
    assert all(item["status"] == "scored" for item in authentic.frame_results)

    assert manipulated.status == "scored"
    assert manipulated.prediction == "fake"
    assert manipulated.fake_score is not None
    assert manipulated.fake_score > 0.8
    assert manipulated.frames_scored == 20
    high_frames = [item for item in manipulated.frame_results if item["fake_score"] >= 0.8]
    assert len(high_frames) >= 2

    scores_before = [item["fake_score"] for item in authentic.frame_results]
    real_comparison = compare_v1_and_v2(authentic.frame_results)
    fake_comparison = compare_v1_and_v2(manipulated.frame_results)
    assert [item["fake_score"] for item in authentic.frame_results] == scores_before
    assert real_comparison["v1"]["prediction"] == "uncertain"
    assert real_comparison["v2"]["prediction"] == "uncertain"
    assert fake_comparison["v1"]["prediction"] == "fake"
    assert fake_comparison["v2"]["prediction"] == "fake"


def test_corrupted_video_is_invalid(detector, tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"this is not a video")
    result = detector.analyze_video(path)
    assert result.status == "invalid_media"
    assert result.fake_score is None
    assert result.prediction is None
    assert result.error_code == "unreadable_video"


def test_video_with_no_faces(detector, tmp_path):
    path = tmp_path / "blank.mp4"
    blank = np.full((180, 240, 3), 15, dtype=np.uint8)
    _write_video(path, [blank.copy() for _ in range(12)])
    result = detector.analyze_video(path)
    assert result.status == "no_face"
    assert result.fake_score is None
    assert result.prediction is None
    assert result.frames_sampled == 12
    assert result.frames_scored == 0
    assert result.frame_results is not None
    assert all(item["status"] == "no_face" for item in result.frame_results)


def test_mixed_frames_exclude_blank_frames_from_the_score(detector, tmp_path):
    path = tmp_path / "mixed.mp4"
    face = cv2.imread(str(REAL_IMAGE))
    assert face is not None
    blank = np.zeros_like(face)
    frames = []
    for index in range(8):
        frames.append(face if index % 2 == 0 else blank)
    _write_video(path, frames, fps=8.0)

    service = DeepfakeDetectorService(predictor=detector.predictor, min_valid_frames=3, num_frames=8)
    result = service.analyze_video(path)
    assert result.frame_results is not None
    scored = [item for item in result.frame_results if item["status"] == "scored"]
    missed = [item for item in result.frame_results if item["status"] == "no_face"]
    assert len(scored) >= 3
    assert len(missed) >= 1
    assert result.status == "scored"
    assert result.prediction == "real"
    assert result.fake_score is not None
    assert result.fake_score < 0.2
    assert result.frames_scored == len(scored)
    assert all(item["timestamp_seconds"] >= 0 for item in result.frame_results)


def test_mild_transforms_stay_outside_the_production_score(detector):
    bgr = cv2.imread(str(REAL_IMAGE))
    assert bgr is not None
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    def score(image):
        return detector._score_rgb(image, frame_index=0, timestamp_seconds=0.0).fake_score

    comparison = compare_transforms(rgb, score)
    production = detector.analyze_image(REAL_IMAGE)
    identity = comparison["identity_score"]
    assert comparison["averaged_into_production"] is False
    assert identity == pytest.approx(production.fake_score)
    assert production.prediction == "real"
    assert all(row["score"] is not None for row in comparison["scores"])
    again = compare_transforms(rgb, score)
    assert [row["score"] for row in again["scores"]] == [row["score"] for row in comparison["scores"]]
