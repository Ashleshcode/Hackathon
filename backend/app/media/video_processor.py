"""Read a video file with OpenCV and extract its sampled frames."""

import math
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from app.media.frame_sampling import MAX_SAMPLED_FRAMES, sample_frame_indices


class VideoProcessingError(ValueError):
    """The video is empty, corrupt, unreadable, or has invalid metadata."""


@dataclass
class VideoFrame:
    frame_index: int
    timestamp_seconds: float
    image: object


@dataclass
class VideoExtraction:
    """Frames that were decoded, plus the sampled frames that could not be."""

    frames: list[VideoFrame]
    failed_frame_indices: list[int] = field(default_factory=list)


def extract_video_frames(
    video_path: str | Path,
    max_samples: int = MAX_SAMPLED_FRAMES,
) -> VideoExtraction:
    """Decode up to ``max_samples`` evenly spaced frames from a video.

    Frames that cannot be decoded are reported in ``failed_frame_indices``, so
    the caller can warn about them. If no frame decodes, this raises
    ``VideoProcessingError`` instead of returning an empty success.
    """
    path = Path(video_path)

    if not path.is_file():
        raise FileNotFoundError(f"Video not found: {path.name}")

    if path.stat().st_size == 0:
        raise VideoProcessingError("Video file is empty")

    cap = cv2.VideoCapture(str(path))

    try:
        if not cap.isOpened():
            raise VideoProcessingError("Unable to open video file")

        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = cap.get(cv2.CAP_PROP_FPS)

        if not math.isfinite(frame_count) or frame_count < 1:
            raise VideoProcessingError(
                f"Invalid video metadata: frame count is {frame_count}"
            )

        if not math.isfinite(fps) or fps <= 0:
            raise VideoProcessingError(f"Invalid video metadata: FPS is {fps}")

        samples = sample_frame_indices(int(frame_count), fps, max_samples)

        frames: list[VideoFrame] = []
        failed_frame_indices: list[int] = []

        for sample in samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, sample.frame_index)
            success, image = cap.read()

            if not success or image is None:
                failed_frame_indices.append(sample.frame_index)
                continue

            frames.append(
                VideoFrame(
                    frame_index=sample.frame_index,
                    timestamp_seconds=sample.timestamp_seconds,
                    image=image,
                )
            )

        if not frames:
            raise VideoProcessingError(
                f"None of the {len(samples)} sampled frames could be decoded"
            )

        return VideoExtraction(frames, failed_frame_indices)

    finally:
        cap.release()


def process_video(
    video_path: str,
    max_samples: int = MAX_SAMPLED_FRAMES,
) -> list[VideoFrame]:
    """Return only the decoded frames from ``extract_video_frames``."""
    return extract_video_frames(video_path, max_samples).frames
