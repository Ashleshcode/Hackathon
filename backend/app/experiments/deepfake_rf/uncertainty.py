"""Rejection thresholds on an uncalibrated class-vote fraction.

The fraction is the share of trees that voted fake. It is not a probability.
"""

from __future__ import annotations

import numpy as np


def apply_rejection(vote_fraction: float, *, low: float, high: float) -> str:
    if low >= high:
        raise ValueError("The low rejection threshold must be below the high threshold.")
    if not np.isfinite(vote_fraction):
        return "uncertain"
    if vote_fraction >= high:
        return "fake"
    if vote_fraction <= low:
        return "real"
    return "uncertain"


def _selective_balanced_accuracy(labels: list[str], predictions: list[str]) -> tuple[float | None, float]:
    accepted = [(label, prediction) for label, prediction in zip(labels, predictions) if prediction != "uncertain"]
    coverage = len(accepted) / len(labels) if labels else 0.0
    if not accepted:
        return None, coverage
    recalls = []
    for label in ("real", "fake"):
        total = sum(item[0] == label for item in accepted)
        if total == 0:
            return None, coverage
        correct = sum(item[0] == label and item[1] == label for item in accepted)
        recalls.append(correct / total)
    return 0.5 * (recalls[0] + recalls[1]), coverage


def select_thresholds(
    vote_fractions: list[float],
    labels: list[str],
    *,
    lows: tuple[float, ...] = (0.25, 0.35, 0.45),
    highs: tuple[float, ...] = (0.55, 0.70, 0.85),
) -> dict:
    """Choose thresholds from validation votes only.

    The winning pair has the highest balanced accuracy among accepted
    predictions. Coverage breaks a tie. An earlier pair wins a remaining tie.
    """
    if len(vote_fractions) != len(labels) or not labels:
        raise ValueError("Validation votes and labels must be the same non-empty length.")
    if set(labels) != {"real", "fake"}:
        raise ValueError("Validation labels must include both real and fake.")
    best = None
    trials = []
    for low in lows:
        for high in highs:
            if low >= high:
                continue
            predictions = [apply_rejection(vote, low=low, high=high) for vote in vote_fractions]
            balanced, coverage = _selective_balanced_accuracy(labels, predictions)
            uncertain = sum(prediction == "uncertain" for prediction in predictions) / len(predictions)
            trial = {
                "low": low,
                "high": high,
                "validation_selective_balanced_accuracy": balanced,
                "validation_coverage": coverage,
                "validation_uncertain_rate": uncertain,
            }
            trials.append(trial)
            if balanced is None:
                continue
            if best is None or balanced > best["validation_selective_balanced_accuracy"] or (
                balanced == best["validation_selective_balanced_accuracy"] and coverage > best["validation_coverage"]
            ):
                best = trial
    if best is None:
        raise ValueError("Every validation threshold left the selective balanced accuracy undefined.")
    return {"low": best["low"], "high": best["high"], "selected": best, "trials": trials}
