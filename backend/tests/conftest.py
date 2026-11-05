"""Shared fixtures. All generated media lives in pytest's temporary folders."""

from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import pytest


def frame_brightness(frame_index: int) -> int:
    """Give each frame a known brightness, so tests can identify it."""
    return min(frame_index * 8, 255)


@pytest.fixture
def make_video(tmp_path: Path) -> Callable[..., Path]:
    """Return a function that writes a small real video with OpenCV."""

    def _make_video(
        total_frames: int,
        fps: float = 30.0,
        name: str = "sample.mp4",
        codec: str = "mp4v",
    ) -> Path:
        path = tmp_path / name
        writer = cv2.VideoWriter(
            str(path), cv2.VideoWriter_fourcc(*codec), fps, (64, 48)
        )
        if not writer.isOpened():
            pytest.skip(f"OpenCV cannot write {name} with codec {codec} here")
        try:
            for index in range(total_frames):
                frame = np.full((48, 64, 3), frame_brightness(index), dtype=np.uint8)
                writer.write(frame)
        finally:
            writer.release()
        return path

    return _make_video


@pytest.fixture
def image_file(tmp_path: Path) -> Path:
    path = tmp_path / "sample.png"
    success, encoded = cv2.imencode(".png", np.zeros((48, 64, 3), dtype=np.uint8))
    assert success
    path.write_bytes(encoded.tobytes())
    return path


@pytest.fixture
def corrupt_file(tmp_path: Path) -> Path:
    path = tmp_path / "corrupt.mp4"
    path.write_bytes(b"this is not a real media file" * 100)
    return path
