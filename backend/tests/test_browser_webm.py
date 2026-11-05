"""Chrome MediaRecorder samples must be sampled, not rejected for a bad frame count."""

from pathlib import Path

from app.models.deepfake_detector import DeepfakeDetectorService
from app.models.video_io import _timing_fps, inspect_video

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class _NoFacePredictor:
    model_name = "stub"
    device = "cpu"

    def __init__(self):
        self.face_detector = self

    def detect_batch(self, _images, _scales):
        return [[]]


def test_media_recorder_frame_count_is_counted_when_the_container_value_is_unusable():
    for name in ("vp8.webm", "vp9.webm"):
        stats = inspect_video(FIXTURES / name)
        assert stats.opened is True
        assert stats.raw_frame_count <= 0
        assert stats.frame_count == 24
        assert stats.fps > 0


def test_unusable_frame_count_prefers_timestamp_fps_over_a_plausible_container_fps():
    assert _timing_fps(raw_fps=120.0, measured_fps=12.5, container_count_usable=False) == 12.5
    assert _timing_fps(raw_fps=30.0, measured_fps=29.0, container_count_usable=True) == 30.0


def test_media_recorder_video_is_sampled_without_a_score_when_no_face_is_present():
    service = DeepfakeDetectorService(predictor=_NoFacePredictor(), num_frames=5, min_valid_frames=3)
    result = service.analyze_video(FIXTURES / "vp9.webm")
    assert result.status == "no_face"
    assert result.prediction is None
    assert result.fake_score is None
    assert result.frames_sampled == 5
    assert result.frames_scored == 0
    assert result.error_code == "no_face"
