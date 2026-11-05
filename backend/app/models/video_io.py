"""Read video timing without trusting a broken container frame count.

Chrome MediaRecorder WebM files open in OpenCV and their frames decode, but
CAP_PROP_FRAME_COUNT is often a huge non-finite value. Treating that value as
the length rejects a playable recording before any frame is scored.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)

MAX_FRAMES = 100_000
_RECENT: dict[tuple[str, int, int], VideoStats] = {}


@dataclass(frozen=True)
class VideoStats:
    opened: bool
    frame_count: int
    fps: float
    raw_frame_count: float
    raw_fps: float


def _sane_count(value: float) -> int:
    if not math.isfinite(value) or value <= 0 or value > MAX_FRAMES:
        return 0
    return int(value)


def _sane_fps(value: float) -> float:
    if not math.isfinite(value) or value <= 0 or value > 240:
        return 0.0
    return float(value)


def _timing_fps(*, raw_fps: float, measured_fps: float, container_count_usable: bool) -> float:
    """Choose the fps used to turn a frame index into a timestamp.

    A Chrome WebM can report a plausible fps, such as 120, while its frame
    count is unusable and the decoded timestamps span a much longer recording.
    When the count cannot be trusted, the fps measured from those timestamps
    is the one that keeps burst gaps honest.
    """
    reported = _sane_fps(raw_fps)
    measured = _sane_fps(measured_fps)
    if not container_count_usable and measured > 0:
        return measured
    if reported > 0:
        return reported
    return measured


def _read_frame(capture: cv2.VideoCapture) -> bool | None:
    if not capture.grab():
        return None
    ok, frame = capture.retrieve()
    if ok and frame is not None and frame.size > 0:
        return True
    return False


def _count_frames(path: Path) -> tuple[int, float]:
    capture = cv2.VideoCapture(str(path))
    decoded = 0
    last_msec = 0.0
    try:
        if not capture.isOpened():
            return 0, 0.0
        while decoded < MAX_FRAMES:
            found = _read_frame(capture)
            if found is None:
                break
            if not found:
                continue
            decoded += 1
            msec = float(capture.get(cv2.CAP_PROP_POS_MSEC))
            if math.isfinite(msec) and msec > 0:
                last_msec = msec
    finally:
        capture.release()
    fps = 0.0
    if decoded > 1 and last_msec > 0:
        fps = _sane_fps((decoded - 1) / (last_msec / 1000.0))
    return decoded, fps


def inspect_video(path: Path) -> VideoStats:
    resolved = path.resolve()
    stat = resolved.stat()
    key = (str(resolved), stat.st_size, stat.st_mtime_ns)
    cached = _RECENT.get(key)
    if cached is not None:
        return cached
    stats = _inspect_video(resolved)
    _RECENT[key] = stats
    if len(_RECENT) > 8:
        _RECENT.pop(next(iter(_RECENT)))
    return stats


def _inspect_video(path: Path) -> VideoStats:
    capture = cv2.VideoCapture(str(path))
    raw_count = 0.0
    raw_fps = 0.0
    count = 0
    fps = 0.0
    try:
        if not capture.isOpened():
            logger.warning("OpenCV could not open video %s", path.name)
            return VideoStats(False, 0, 0.0, raw_count, raw_fps)
        raw_count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        raw_fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = _sane_count(raw_count)
        fps = _sane_fps(raw_fps)
        if _read_frame(capture) is True and count > 0 and fps > 0:
            return VideoStats(True, count, fps, raw_count, raw_fps)
    finally:
        capture.release()

    decoded, measured_fps = _count_frames(path)
    fps = _timing_fps(raw_fps=raw_fps, measured_fps=measured_fps, container_count_usable=count > 0)
    if decoded <= 0 or fps <= 0:
        logger.warning(
            "Video %s has no decodable timed frames. raw_frame_count=%s raw_fps=%s decoded=%s",
            path.name,
            raw_count,
            raw_fps,
            decoded,
        )
        return VideoStats(True, 0, 0.0, raw_count, raw_fps)
    if count <= 0:
        logger.warning(
            "Video %s reported frame count %s and fps %s; counted %s decodable frames at %s fps",
            path.name,
            raw_count,
            raw_fps,
            decoded,
            fps,
        )
    return VideoStats(True, decoded, fps, raw_count, raw_fps)
