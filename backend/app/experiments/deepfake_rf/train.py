"""Train the experimental forest and compare it with the V1 rule on the same videos."""

from __future__ import annotations

import hashlib
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils.class_weight import compute_class_weight

from app.experiments.deepfake_rf import FEATURE_SCHEMA_VERSION, MEASUREMENT_SOURCE, MODEL_VERSION
from app.experiments.deepfake_rf.baseline import v1_prediction
from app.experiments.deepfake_rf.io import write_json
from app.experiments.deepfake_rf.manifest import is_regression_case, is_synthetic_dataset
from app.experiments.deepfake_rf.metrics import (
    LIMITATION,
    authentic_false_positives,
    decision_report,
)
from app.experiments.deepfake_rf.schema import FEATURE_COLUMNS, FEATURE_DESCRIPTIONS
from app.experiments.deepfake_rf.split import SplitError, assert_group_disjoint, assign_grouped_split, group_ids
from app.experiments.deepfake_rf.uncertainty import apply_rejection, select_thresholds

RANDOM_SEED = 42
DEFAULT_GRID = (
    {"n_estimators": 100, "max_depth": 4, "min_samples_leaf": 1},
    {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 3},
    {"n_estimators": 200, "max_depth": None, "min_samples_leaf": 1},
)


class TrainingError(ValueError):
    pass


def assert_extraction_metadata(metadata: dict) -> None:
    if metadata.get("synthetic") is True or metadata.get("measurement_source") != MEASUREMENT_SOURCE:
        raise TrainingError("Synthetic features cannot be used for training.")
    if metadata.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise TrainingError("The feature file uses an unknown schema.")


def _matrix(rows: list[dict], columns: list[str]) -> np.ndarray:
    values = np.full((len(rows), len(columns)), np.nan, dtype=np.float64)
    for row_index, row in enumerate(rows):
        for column_index, key in enumerate(columns):
            value = row["features"].get(key)
            if value is not None:
                values[row_index, column_index] = float(value)
    return values


def _labels(rows: list[dict]) -> np.ndarray:
    return np.asarray([1 if row["label"] == "fake" else 0 for row in rows], dtype=np.int64)


def _kept_columns(rows: list[dict]) -> list[str]:
    kept = [key for key in FEATURE_COLUMNS if any(row["features"].get(key) is not None for row in rows)]
    if not kept:
        raise TrainingError("Every feature is missing on the training videos.")
    return kept


def _fit(rows: list[dict], columns: list[str], params: dict, seed: int) -> RandomForestClassifier:
    model = RandomForestClassifier(random_state=seed, class_weight="balanced", n_jobs=1, **params)
    model.fit(_matrix(rows, columns), _labels(rows))
    return model


def _votes(model: RandomForestClassifier, rows: list[dict], columns: list[str]) -> list[float]:
    if not rows:
        return []
    probabilities = model.predict_proba(_matrix(rows, columns))
    classes = list(model.classes_)
    if 1 not in classes:
        return [0.0 for _row in rows]
    column = classes.index(1)
    return [float(value) for value in probabilities[:, column]]


def _hard_balanced_accuracy(model: RandomForestClassifier, rows: list[dict], columns: list[str]) -> float | None:
    if not rows:
        return None
    predicted = model.predict(_matrix(rows, columns))
    actual = _labels(rows)
    recalls = []
    for label in (0, 1):
        mask = actual == label
        if not np.any(mask):
            return None
        recalls.append(float(np.mean(predicted[mask] == label)))
    return 0.5 * (recalls[0] + recalls[1])


def _select_model(train_rows, validation_rows, columns, grid, seed) -> tuple[dict, list[dict]]:
    results = []
    best = None
    for params in grid:
        model = _fit(train_rows, columns, params, seed)
        score = _hard_balanced_accuracy(model, validation_rows, columns)
        trial = {"params": params, "validation_hard_balanced_accuracy": score}
        results.append(trial)
        if score is None:
            continue
        if best is None or score > best["validation_hard_balanced_accuracy"]:
            best = trial
    if best is None:
        raise TrainingError("No hyperparameter setting produced a validation score.")
    return best["params"], results


def _case(row: dict, prediction: str, vote: float | None, frames: list[dict] | None) -> dict:
    return {
        "video_id": row["video_id"],
        "label": row["label"],
        "dataset_name": row["dataset_name"],
        "source_group_id": row["source_group_id"],
        "prediction": prediction,
        "vote_fraction": vote,
        "vote_fraction_semantics": "uncalibrated_class_vote_fraction",
        "v1_prediction": v1_prediction(frames) if frames is not None else None,
        "score_median": row["features"].get("score_median"),
        "score_max": row["features"].get("score_max"),
    }


def _predict_cases(model, rows, columns, thresholds, frames_by_id) -> list[dict]:
    votes = _votes(model, rows, columns)
    cases = []
    for row, vote in zip(rows, votes):
        prediction = apply_rejection(vote, low=thresholds["low"], high=thresholds["high"])
        cases.append(_case(row, prediction, vote, frames_by_id.get(row["video_id"])))
    return cases


def _method_report(cases: list[dict], *, prediction_key: str, with_ranking: bool) -> dict:
    labels = [case["label"] for case in cases]
    predictions = [case[prediction_key] for case in cases]
    votes = [case["vote_fraction"] for case in cases] if with_ranking else None
    return decision_report(labels, predictions, vote_fractions=votes)


def _cross_dataset(trainable, grid, seed, frames_by_id) -> list[dict]:
    names = sorted({row["dataset_name"] for row in trainable})
    if len(names) < 2:
        return [{"status": "not_supported", "reason": "The manifest has one trainable dataset, so a cross-dataset split is not available."}]
    reports = []
    for held in names:
        test_rows = [row for row in trainable if row["dataset_name"] == held]
        train_pool = [row for row in trainable if row["dataset_name"] != held]
        overlap = group_ids(test_rows) & group_ids(train_pool)
        if overlap:
            test_rows = [row for row in test_rows if row["source_group_id"] not in overlap]
        if {row["label"] for row in test_rows} != {"real", "fake"}:
            reports.append(
                {
                    "held_out_dataset": held,
                    "status": "not_supported",
                    "reason": "The held-out dataset does not contain both classes after removing shared source groups.",
                }
            )
            continue
        try:
            parts = assign_grouped_split(train_pool, seed=seed)
            assert_group_disjoint(parts)
        except SplitError as exc:
            reports.append({"held_out_dataset": held, "status": "not_supported", "reason": str(exc)})
            continue
        cross_columns = _kept_columns(parts["train"])
        params, _trials = _select_model(parts["train"], parts["validation"], cross_columns, grid, seed)
        model = _fit(parts["train"], cross_columns, params, seed)
        validation_votes = _votes(model, parts["validation"], cross_columns)
        try:
            thresholds = select_thresholds(
                validation_votes,
                [row["label"] for row in parts["validation"]],
            )
        except ValueError as exc:
            reports.append({"held_out_dataset": held, "status": "not_supported", "reason": str(exc)})
            continue
        cases = _predict_cases(model, test_rows, cross_columns, thresholds, frames_by_id)
        comparable = [case for case in cases if case["v1_prediction"] is not None]
        reports.append(
            {
                "held_out_dataset": held,
                "status": "scored",
                "limitation": LIMITATION,
                "test_videos": len(comparable),
                "random_forest": _method_report(comparable, prediction_key="prediction", with_ranking=True),
                "v1_baseline": _method_report(comparable, prediction_key="v1_prediction", with_ranking=False),
            }
        )
    return reports


def render_report(report: dict) -> str:
    def line(metrics: dict) -> str:
        accepted = metrics["non_abstained"]
        text = (
            f"- rows {metrics['rows']}, coverage {metrics['coverage']}, "
            f"uncertain rate {metrics['uncertain_prediction_rate']}\n"
            f"  accuracy {accepted['accuracy']}, balanced accuracy {accepted['balanced_accuracy']}, "
            f"precision {accepted['precision']}, recall {accepted['recall']}, F1 {accepted['f1']}, "
            f"false-positive rate {accepted['false_positive_rate']}, "
            f"false-negative rate {accepted['false_negative_rate']}\n"
            f"  confusion matrix {metrics['confusion_matrix']}"
        )
        ranking = metrics.get("ranking")
        if ranking:
            text += (
                f"\n  vote-fraction ROC-AUC {ranking['roc_auc']}, PR-AUC {ranking['pr_auc']} "
                f"({ranking['score_semantics']})"
            )
        return text

    parts = [
        "# Random Forest experiment",
        "",
        report["limitation"],
        "",
        "Production video aggregation was not changed. The V1 numbers below come from `aggregate_video_scores`.",
        "",
        "## Held-out comparison",
        "",
        "Random Forest:",
        line(report["held_out"]["random_forest"]),
        "",
        "V1 baseline:",
        line(report["held_out"]["v1_baseline"]),
        "",
        "## Authentic videos predicted fake by the forest",
        "",
    ]
    errors = report["authentic_predicted_fake_by_random_forest"]
    if not errors:
        parts.append("None on this held-out split.")
    else:
        for case in errors:
            parts.append(
                f"- {case['video_id']} ({case['dataset_name']}), vote fraction {case['vote_fraction']}, "
                f"V1 prediction {case['v1_prediction']}"
            )
    parts.extend(["", "## Authentic videos predicted fake by V1", ""])
    v1_errors = report["authentic_predicted_fake_by_v1"]
    if not v1_errors:
        parts.append("None on this held-out split.")
    else:
        for case in v1_errors:
            parts.append(f"- {case['video_id']} ({case['dataset_name']})")
    parts.extend(["", "## Regression cases", ""])
    if not report["regression_cases"]:
        parts.append("None supplied.")
    else:
        parts.append("These cases are not included in the held-out metrics or the threshold choice.")
        for case in report["regression_cases"]:
            parts.append(
                f"- {case['video_id']}: label {case['label']}, forest {case.get('prediction')}, "
                f"V1 {case.get('v1_prediction')}"
            )
    parts.extend(["", "## Cross-dataset", ""])
    for item in report["cross_dataset"]:
        if item["status"] != "scored":
            parts.append(f"- {item.get('held_out_dataset', 'all')}: {item['reason']}")
        else:
            parts.append(
                f"- held out {item['held_out_dataset']}: forest selective accuracy "
                f"{item['random_forest']['non_abstained']['accuracy']}"
            )
    parts.append("")
    return "\n".join(parts)


def train_and_evaluate(
    manifest_rows: list[dict],
    features_by_id: dict[str, dict],
    frames_by_id: dict[str, list[dict]],
    output_dir: str | Path,
    *,
    manifest_path: str | Path | None = None,
    seed: int = RANDOM_SEED,
    grid: tuple[dict, ...] = DEFAULT_GRID,
) -> dict:
    if any(is_synthetic_dataset(row) for row in manifest_rows):
        raise TrainingError("Synthetic manifest rows cannot be trained.")
    trainable = []
    regression = []
    for row in manifest_rows:
        if is_regression_case(row):
            regression.append(row)
        else:
            trainable.append(row)
    missing = [row["video_id"] for row in trainable if row["video_id"] not in features_by_id]
    if missing:
        raise TrainingError("Trainable videos have no extracted features: " + ", ".join(missing))
    joined = []
    for row in trainable:
        item = dict(row)
        item["features"] = features_by_id[row["video_id"]]
        joined.append(item)
    try:
        parts = assign_grouped_split(joined, seed=seed)
        assert_group_disjoint(parts)
    except SplitError as exc:
        raise TrainingError(str(exc)) from exc
    columns = _kept_columns(parts["train"])
    params, trials = _select_model(parts["train"], parts["validation"], columns, grid, seed)
    model = _fit(parts["train"], columns, params, seed)
    validation_votes = _votes(model, parts["validation"], columns)
    thresholds = select_thresholds(validation_votes, [row["label"] for row in parts["validation"]])
    test_cases = _predict_cases(model, parts["test"], columns, thresholds, frames_by_id)
    comparable = [case for case in test_cases if case["v1_prediction"] is not None]
    excluded = [case["video_id"] for case in test_cases if case["v1_prediction"] is None]
    regression_rows = []
    for row in regression:
        if row["video_id"] not in features_by_id:
            regression_rows.append(
                {
                    "video_id": row["video_id"],
                    "label": row["label"],
                    "prediction": None,
                    "reason": "features_not_extracted",
                }
            )
            continue
        item = dict(row)
        item["features"] = features_by_id[row["video_id"]]
        regression_rows.extend(_predict_cases(model, [item], columns, thresholds, frames_by_id))

    weights = compute_class_weight(class_weight="balanced", classes=np.array([0, 1]), y=_labels(parts["train"]))
    manifest_reference = {
        "rows": len(manifest_rows),
        "trainable_rows": len(trainable),
        "regression_rows": len(regression),
    }
    if manifest_path is not None:
        payload = Path(manifest_path).read_bytes()
        manifest_reference["path"] = str(manifest_path)
        manifest_reference["sha256"] = hashlib.sha256(payload).hexdigest()
    report = {
        "model_version": MODEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "limitation": LIMITATION,
        "calibration": {
            "applied": False,
            "reason": "Rejection uses the uncalibrated class-vote fraction. No probability calibrator was fit.",
        },
        "score_semantics": "uncalibrated_class_vote_fraction",
        "split": {
            "seed": seed,
            "attempt": parts["attempt"],
            "train_videos": len(parts["train"]),
            "validation_videos": len(parts["validation"]),
            "test_videos": len(parts["test"]),
            "train_groups": sorted(group_ids(parts["train"])),
            "validation_groups": sorted(group_ids(parts["validation"])),
            "test_groups": sorted(group_ids(parts["test"])),
            "comparable_test_videos": [case["video_id"] for case in comparable],
            "excluded_from_comparison": excluded,
        },
        "held_out": {
            "random_forest": _method_report(comparable, prediction_key="prediction", with_ranking=True),
            "v1_baseline": _method_report(comparable, prediction_key="v1_prediction", with_ranking=False),
        },
        "authentic_predicted_fake_by_random_forest": authentic_false_positives(comparable),
        "authentic_predicted_fake_by_v1": [
            case for case in comparable if case["label"] == "real" and case["v1_prediction"] == "fake"
        ],
        "regression_cases": regression_rows,
        "cross_dataset": _cross_dataset(joined, grid, seed, frames_by_id),
    }
    config = {
        "model_version": MODEL_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "seed": seed,
        "class_weight": {"mode": "balanced", "real": float(weights[0]), "fake": float(weights[1])},
        "missing_values": "left_missing_for_the_forest",
        "feature_columns": columns,
        "dropped_columns": [key for key in FEATURE_COLUMNS if key not in columns],
        "hyperparameter_grid": trials,
        "selected_hyperparameters": params,
        "rejection_thresholds": {"low": thresholds["low"], "high": thresholds["high"]},
        "rejection_trials": thresholds["trials"],
        "calibration_applied": False,
    }
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "feature_columns": columns,
            "model_version": MODEL_VERSION,
            "label_to_int": {"real": 0, "fake": 1},
            "score_semantics": "uncalibrated_class_vote_fraction",
            "thresholds": {"low": thresholds["low"], "high": thresholds["high"]},
        },
        destination / "model.joblib",
    )
    write_json(
        destination / "feature_schema.json",
        {
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "columns": columns,
            "descriptions": {key: FEATURE_DESCRIPTIONS[key] for key in columns},
        },
    )
    write_json(destination / "training_config.json", config)
    write_json(destination / "manifest_reference.json", manifest_reference)
    write_json(destination / "evaluation_report.json", report)
    (destination / "evaluation_report.md").write_text(render_report(report), encoding="utf-8")
    (destination / "model_version.txt").write_text(MODEL_VERSION + "\n", encoding="utf-8")
    return report


def load_model(path: str | Path) -> dict:
    payload = joblib.load(path)
    if payload.get("model_version") != MODEL_VERSION:
        raise TrainingError("The saved model version does not match this experiment.")
    return payload
