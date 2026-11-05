"""Choose which video frames to analyse and work out their timestamps."""

import math
from dataclasses import dataclass

# API contract: "Sample at most 20 frames."
MAX_SAMPLED_FRAMES = 20


@dataclass
class SampledFrame:
    frame_index: int
    timestamp_seconds: float


def sample_frame_indices(
    total_frames: int,
    fps: float,
    max_samples: int = MAX_SAMPLED_FRAMES,
) -> list[SampledFrame]:
    """Return evenly spaced, unique frames, including the first and last frame.

    Timestamps are ``frame_index / fps``, so they assume a constant frame rate.
    A video with no frames returns an empty list.
    """
    if total_frames <= 0:
        return []

    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be a finite number greater than zero")

    if max_samples <= 0:
        raise ValueError("max_samples must be greater than zero")

    if max_samples > MAX_SAMPLED_FRAMES:
        raise ValueError(f"max_samples must not exceed {MAX_SAMPLED_FRAMES}")

    sample_count = min(total_frames, max_samples)

    if sample_count == 1:
        indices = [0]
    else:
        indices = [
            round(i * (total_frames - 1) / (sample_count - 1))
            for i in range(sample_count)
        ]

    return [
        SampledFrame(frame_index=index, timestamp_seconds=index / fps)
        for index in sorted(set(indices))
    ]
