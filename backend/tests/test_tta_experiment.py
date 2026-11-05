"""Augmentation fixtures. These tests do not load DeepGuard."""

import numpy as np

from app.models.tta_experiment import TRANSFORMS, compare_transforms, transform_rgb


def test_transforms_are_reproducible_and_are_not_averaged():
    image = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)

    def score(rgb):
        return float(rgb[0, 0, 0])

    first = compare_transforms(image, score)
    second = compare_transforms(image, score)
    assert [row["name"] for row in first["scores"]] == list(TRANSFORMS)
    assert first["scores"] == second["scores"]
    assert first["averaged_into_production"] is False
    assert first["identity_score"] == score(image)
    flipped = transform_rgb(image, "horizontal_flip")
    assert np.array_equal(flipped, transform_rgb(image, "horizontal_flip"))
    assert not np.array_equal(flipped, image)
    assert np.array_equal(image, transform_rgb(image, "identity"))
    brighter = transform_rgb(image, "brightness_up")
    assert brighter.dtype == np.uint8
    assert float(brighter.mean()) > float(image.mean())
