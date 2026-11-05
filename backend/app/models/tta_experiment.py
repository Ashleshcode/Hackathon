"""Test-time augmentation experiment. Production inference does not call this module.

The transforms are deterministic and mild: a horizontal flip, and brightness or
contrast moved by 8 percent. They are not averaged into a stored prediction.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

TRANSFORMS = (
    "identity",
    "horizontal_flip",
    "brightness_up",
    "brightness_down",
    "contrast_up",
    "contrast_down",
)
MILD_FACTOR = 1.08


def transform_rgb(rgb: np.ndarray, name: str) -> np.ndarray:
    """Return a new image. The input array is not modified."""
    image = np.array(rgb, copy=True)
    if name == "identity":
        return image
    if name == "horizontal_flip":
        return np.ascontiguousarray(image[:, ::-1])
    if name == "brightness_up":
        return _scale(image, MILD_FACTOR)
    if name == "brightness_down":
        return _scale(image, 1.0 / MILD_FACTOR)
    if name == "contrast_up":
        return _contrast(image, MILD_FACTOR)
    if name == "contrast_down":
        return _contrast(image, 1.0 / MILD_FACTOR)
    raise ValueError(f"Unknown augmentation {name!r}.")


def _scale(image: np.ndarray, factor: float) -> np.ndarray:
    return np.clip(image.astype(np.float32) * factor, 0, 255).astype(np.uint8)


def _contrast(image: np.ndarray, factor: float) -> np.ndarray:
    mean = image.astype(np.float32).mean(axis=(0, 1), keepdims=True)
    return np.clip((image.astype(np.float32) - mean) * factor + mean, 0, 255).astype(np.uint8)


def compare_transforms(rgb: np.ndarray, score_fn: Callable[[np.ndarray], float | None]) -> dict:
    """Score each transform independently. The identity score is the original prediction."""
    rows = []
    identity_score = None
    for name in TRANSFORMS:
        transformed = transform_rgb(rgb, name)
        score = score_fn(transformed)
        if name == "identity":
            identity_score = score
        delta = None
        if identity_score is not None and score is not None and name != "identity":
            delta = float(score) - float(identity_score)
        rows.append({"name": name, "score": score, "delta_from_identity": delta})
    deltas = [row["delta_from_identity"] for row in rows if row["delta_from_identity"] is not None]
    return {
        "averaged_into_production": False,
        "identity_score": identity_score,
        "scores": rows,
        "max_abs_delta_from_identity": max((abs(value) for value in deltas), default=None),
    }
