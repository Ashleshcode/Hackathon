"""Frame sampling and OpenCV extraction, using real generated video files."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.media import video_processor
from app.media.frame_sampling import MAX_SAMPLED_FRAMES, sample_frame_indices
from app.media.video_processor import (
    VideoProcessingError,
    extract_video_frames,
    process_video,
)
from conftest import frame_brightness


class FakeCapture:
    """Stands in for cv2.VideoCapture to simulate metadata and read failures."""

    instances: list["FakeCapture"] = []

    def __init__(
        self,
        frame_count: float = 10,
        fps: float = 10,
        opened: bool = True,
        bad_frames: set[int] | None = None,
    ) -> None:
        self.frame_count = frame_count
        self.fps = fps
        self.opened = opened
        self.bad_frames = bad_frames or set()
        self.position = 0
        self.released = False
        FakeCapture.instances.append(self)

    def isOpened(self) -> bool:
        return self.opened

    def get(self, prop: int) -> float:
        return self.frame_count if prop == cv2.CAP_PROP_FRAME_COUNT else self.fps

    def set(self, prop: int, value: int) -> bool:
        self.position = value
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.position in self.bad_frames:
            return False, None
        return True, np.zeros((4, 4, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True


@pytest.fixture
def fake_capture(monkeypatch, tmp_path):
    """Patch OpenCV's reader and return a file path that passes the file checks."""
    FakeCapture.instances = []
    path = tmp_path / "fake.mp4"
    path.write_bytes(b"placeholder")

    def install(**settings) -> Path:
        monkeypatch.setattr(
            video_processor.cv2, "VideoCapture", lambda _: FakeCapture(**settings)
        )
        return path

    return install


# ---------- sampling ----------


def test_sampling_matches_previous_behaviour():
    samples = sample_frame_indices(300, 30)
    assert len(samples) == 20
    assert samples[0].timestamp_seconds == 0.0
    assert samples[-1].timestamp_seconds == pytest.approx(9.966666666666667)


@pytest.mark.parametrize("total_frames", [1, 2, 3, 19, 20, 21, 22, 39, 40, 41, 1000, 99991])
def test_sampling_never_duplicates_or_exceeds_cap(total_frames):
    indices = [s.frame_index for s in sample_frame_indices(total_frames, 25)]
    assert len(indices) == len(set(indices)) == min(total_frames, MAX_SAMPLED_FRAMES)
    assert indices == sorted(indices)
    assert indices[0] == 0
    assert indices[-1] == (total_frames - 1 if total_frames > 1 else 0)


@pytest.mark.parametrize("total_frames", [0, -5])
def test_sampling_no_frames(total_frames):
    assert sample_frame_indices(total_frames, 30) == []


@pytest.mark.parametrize("fps", [0, -1, float("nan"), float("inf")])
def test_sampling_rejects_invalid_fps(fps):
    with pytest.raises(ValueError, match="FPS"):
        sample_frame_indices(10, fps)


@pytest.mark.parametrize("max_samples", [0, -1, MAX_SAMPLED_FRAMES + 1])
def test_sampling_rejects_invalid_max_samples(max_samples):
    with pytest.raises(ValueError, match="max_samples"):
        sample_frame_indices(10, 30, max_samples)


# ---------- extraction from real files ----------


def test_video_with_fewer_than_20_frames_uses_every_frame(make_video):
    frames = process_video(str(make_video(7)))
    assert [f.frame_index for f in frames] == list(range(7))


def test_video_with_more_than_20_frames_is_capped(make_video):
    frames = process_video(str(make_video(100)))
    assert len(frames) == 20
    assert len({f.frame_index for f in frames}) == 20
    assert frames[0].frame_index == 0
    assert frames[-1].frame_index == 99


def test_timestamps_are_index_divided_by_fps(make_video):
    frames = process_video(str(make_video(50, fps=25.0)))
    assert frames[0].timestamp_seconds == 0.0
    assert frames[-1].timestamp_seconds == pytest.approx(49 / 25)
    for frame in frames:
        assert frame.timestamp_seconds == pytest.approx(frame.frame_index / 25)


def test_extracted_image_is_the_requested_frame(make_video):
    for frame in process_video(str(make_video(30))):
        assert frame.image.shape == (48, 64, 3)
        assert frame.image.mean() == pytest.approx(
            frame_brightness(frame.frame_index), abs=6
        )


@pytest.mark.parametrize(
    ("name", "codec"),
    [("clip.mp4", "mp4v"), ("clip.mov", "mp4v"), ("clip.avi", "MJPG")],
)
def test_common_video_formats(make_video, name, codec):
    assert len(process_video(str(make_video(25, name=name, codec=codec)))) == 20


# ---------- invalid files ----------


def test_missing_file_does_not_expose_the_directory(tmp_path):
    with pytest.raises(FileNotFoundError) as error:
        process_video(str(tmp_path / "missing.mp4"))
    assert str(tmp_path) not in str(error.value)


def test_zero_byte_file(tmp_path):
    path = tmp_path / "empty.mp4"
    path.write_bytes(b"")
    with pytest.raises(VideoProcessingError, match="empty"):
        process_video(str(path))


def test_video_container_with_no_frames(make_video):
    with pytest.raises(VideoProcessingError):
        process_video(str(make_video(0)))


def test_corrupt_file(corrupt_file):
    with pytest.raises(VideoProcessingError):
        process_video(str(corrupt_file))


# ---------- simulated OpenCV behaviour ----------


@pytest.mark.parametrize("fps", [0, -1, float("nan"), float("inf")])
def test_invalid_fps_metadata_fails_and_releases(fake_capture, fps):
    with pytest.raises(VideoProcessingError, match="FPS"):
        process_video(str(fake_capture(fps=fps)))
    assert FakeCapture.instances[-1].released


@pytest.mark.parametrize("frame_count", [0, -1, float("nan")])
def test_invalid_frame_count_metadata_fails_and_releases(fake_capture, frame_count):
    with pytest.raises(VideoProcessingError, match="frame count"):
        process_video(str(fake_capture(frame_count=frame_count)))
    assert FakeCapture.instances[-1].released


def test_unopenable_video_fails_and_releases(fake_capture):
    with pytest.raises(VideoProcessingError, match="open"):
        process_video(str(fake_capture(opened=False)))
    assert FakeCapture.instances[-1].released


def test_successful_read_releases(fake_capture):
    process_video(str(fake_capture()))
    assert FakeCapture.instances[-1].released


def test_undecodable_frames_are_reported_not_hidden(fake_capture):
    extraction = extract_video_frames(fake_capture(bad_frames={3, 7}))
    assert extraction.failed_frame_indices == [3, 7]
    assert [f.frame_index for f in extraction.frames] == [0, 1, 2, 4, 5, 6, 8, 9]


def test_no_decodable_frames_is_an_error(fake_capture):
    with pytest.raises(VideoProcessingError, match="decoded"):
        extract_video_frames(fake_capture(bad_frames=set(range(10))))
    assert FakeCapture.instances[-1].released
