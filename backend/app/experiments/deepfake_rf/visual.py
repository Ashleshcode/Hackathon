"""Cheap visual measurements on the same sample indices the detector uses.

The walk repeats the detector's grab/retrieve loop so the blur average refers
to those frames. It does not load a model.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from app.models.video_io import _sane_fps, inspect_video


def sample_indices(frame_count: int, num_frames: int) -> list[int]:
    """Match DeepfakeDetectorService._extract_frames."""
    sample_count = min(num_frames, frame_count)
    if sample_count < 1:
        return []
    return sorted(set(np.linspace(0, frame_count - 1, num=sample_count, endpoint=True, dtype=np.int32).tolist()))


def measure_visual(path: str | Path, *, num_frames: int = 20) -> dict[str, float | None]:
    empty: dict[str, float | None] = {
        "mean_frame_blur": None,
        "frame_width": None,
        "frame_height": None,
        "file_bytes_per_second": None,
        "video_fps": None,
        "raw_container_fps": None,
        "container_fps_usable": None,
    }
    file_path = Path(path)
    stats = inspect_video(file_path)
    if stats.opened and stats.frame_count > 0 and stats.fps > 0:
        empty["video_fps"] = float(stats.fps)
        duration = stats.frame_count / stats.fps
        if duration > 0 and file_path.is_file():
            empty["file_bytes_per_second"] = float(file_path.stat().st_size / duration)
    if math.isfinite(stats.raw_fps):
        empty["raw_container_fps"] = float(stats.raw_fps)
        sane = _sane_fps(stats.raw_fps)
        empty["container_fps_usable"] = 1.0 if sane == stats.raw_fps and sane > 0 else 0.0
    if not stats.opened or stats.frame_count <= 0:
        return empty

    indices = sample_indices(stats.frame_count, num_frames)
    if not indices:
        return empty
    capture = cv2.VideoCapture(str(file_path))
    if not capture.isOpened():
        return empty
    blur_values: list[float] = []
    width = None
    height = None
    try:
        target = 0
        last_index = indices[-1]
        for frame_index in range(last_index + 1):
            if not capture.grab():
                break
            if frame_index != indices[target]:
                continue
            ok, frame = capture.retrieve()
            target += 1
            if not ok or frame is None or frame.size == 0:
                if target >= len(indices):
                    break
                continue
            if width is None:
                height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur_values.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
            if target >= len(indices):
                break
    finally:
        capture.release()
    if width is not None and height is not None:
        empty["frame_width"] = float(width)
        empty["frame_height"] = float(height)
    if blur_values:
        empty["mean_frame_blur"] = float(np.mean(np.asarray(blur_values, dtype=np.float64)))
    return empty
