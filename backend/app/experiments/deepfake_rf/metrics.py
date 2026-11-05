"""Comparison metrics. Vote fractions stay labelled as vote fractions."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

LIMITATION = (
    "This comparison describes only the held-out videos in the supplied manifest. "
    "It is not a measured real-world accuracy."
)


def _safe_divide(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def binary_metrics(labels: list[str], predictions: list[str]) -> dict:
    """Score accepted real/fake predictions. The positive class is fake."""
    pairs = [(label, prediction) for label, prediction in zip(labels, predictions) if prediction in {"real", "fake"}]
    true_positive = sum(label == "fake" and prediction == "fake" for label, prediction in pairs)
    false_positive = sum(label == "real" and prediction == "fake" for label, prediction in pairs)
    true_negative = sum(label == "real" and prediction == "real" for label, prediction in pairs)
    false_negative = sum(label == "fake" and prediction == "real" for label, prediction in pairs)
    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)
    specificity = _safe_divide(true_negative, true_negative + false_positive)
    f1 = None
    if precision is not None and recall is not None and precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    balanced = None if recall is None or specificity is None else 0.5 * (recall + specificity)
    return {
        "support": len(pairs),
        "accuracy": _safe_divide(true_positive + true_negative, len(pairs)),
        "balanced_accuracy": balanced,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_positive_rate": _safe_divide(false_positive, false_positive + true_negative),
        "false_negative_rate": _safe_divide(false_negative, false_negative + true_positive),
    }


def confusion_matrix(labels: list[str], predictions: list[str]) -> dict[str, dict[str, int]]:
    matrix = {label: {"real": 0, "fake": 0, "uncertain": 0} for label in ("real", "fake")}
    for label, prediction in zip(labels, predictions):
        if label not in matrix or prediction not in matrix[label]:
            continue
        matrix[label][prediction] += 1
    return matrix


def ranking_metrics(labels: list[str], vote_fractions: list[float]) -> dict:
    """Rank by the fake-class vote fraction. This is not a calibrated probability."""
    usable = [
        (label, vote)
        for label, vote in zip(labels, vote_fractions)
        if label in {"real", "fake"} and vote is not None and np.isfinite(vote)
    ]
    body = {
        "score_semantics": "uncalibrated_class_vote_fraction",
        "roc_auc": None,
        "pr_auc": None,
    }
    if len({label for label, _vote in usable}) < 2:
        return body
    y_true = [1 if label == "fake" else 0 for label, _vote in usable]
    scores = [vote for _label, vote in usable]
    body["roc_auc"] = float(roc_auc_score(y_true, scores))
    body["pr_auc"] = float(average_precision_score(y_true, scores))
    return body


def decision_report(labels: list[str], predictions: list[str], *, vote_fractions: list[float] | None = None) -> dict:
    uncertain = sum(prediction == "uncertain" for prediction in predictions)
    total = len(labels)
    report = {
        "rows": total,
        "uncertain_prediction_rate": (uncertain / total) if total else None,
        "coverage": ((total - uncertain) / total) if total else None,
        "accuracy_counting_uncertain_as_incorrect": _safe_divide(
            sum(label == prediction for label, prediction in zip(labels, predictions)),
            total,
        ),
        "confusion_matrix": confusion_matrix(labels, predictions),
        "non_abstained": binary_metrics(labels, predictions),
    }
    if vote_fractions is not None:
        report["ranking"] = ranking_metrics(labels, vote_fractions)
    return report


def authentic_false_positives(cases: list[dict]) -> list[dict]:
    return [
        case
        for case in cases
        if case.get("label") == "real" and case.get("prediction") == "fake"
    ]
