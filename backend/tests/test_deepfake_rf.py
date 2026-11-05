"""Pipeline tests for the Random Forest experiment. Fixture numbers are not DeepGuard measurements."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.utils.class_weight import compute_class_weight

from app.experiments.deepfake_rf.baseline import v1_prediction
from app.experiments.deepfake_rf.extract import ExtractionRefused, ensure_api_is_stopped, extract_manifest
from app.experiments.deepfake_rf.features import FeatureError, features_from_frames
from app.experiments.deepfake_rf.io import read_feature_csv
from app.experiments.deepfake_rf.manifest import ManifestError, is_regression_case, load_manifest, validate_manifest
from app.experiments.deepfake_rf.metrics import LIMITATION
from app.experiments.deepfake_rf.schema import FEATURE_COLUMNS
from app.experiments.deepfake_rf.split import assert_group_disjoint, assign_grouped_split, group_ids
from app.experiments.deepfake_rf.train import (
    TrainingError,
    assert_extraction_metadata,
    load_model,
    train_and_evaluate,
)
from app.experiments.deepfake_rf.uncertainty import apply_rejection, select_thresholds
from app.experiments.deepfake_rf.visual import measure_visual

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST = Path(__file__).resolve().parents[1] / "experiments" / "deepfake_rf" / "manifests" / "manifest.csv"


def _frame(timestamp, score, **extra):
    body = {"timestamp_seconds": timestamp, "status": "scored" if score is not None else "no_face", "fake_score": score}
    body.update(extra)
    return body


def test_feature_extraction_uses_scores_time_and_face_measurements():
    frames = [
        _frame(0.0, 0.0, detector_confidence=0.8, face_area_ratio=0.02, crop_width=10, crop_height=20),
        _frame(1.0, 0.0, detector_confidence=0.4, face_area_ratio=0.04, crop_width=30, crop_height=40),
        _frame(2.0, 1.0, detector_confidence=0.9, face_area_ratio=0.05, crop_width=30, crop_height=40),
        _frame(3.0, 1.0, detector_confidence=0.7, face_area_ratio=0.08, crop_width=10, crop_height=20),
        _frame(1.5, None),
    ]
    measured = features_from_frames(frames, visual={"frame_width": 640, "frame_height": 360, "mean_frame_blur": 12.5})
    assert measured["score_mean"] == pytest.approx(0.5)
    assert measured["score_median"] == pytest.approx(0.5)
    assert measured["score_min"] == pytest.approx(0.0)
    assert measured["score_max"] == pytest.approx(1.0)
    assert measured["score_std"] == pytest.approx(0.5)
    assert measured["score_iqr"] == pytest.approx(1.0)
    assert measured["fraction_score_ge_0_8"] == pytest.approx(0.5)
    assert measured["fraction_score_le_0_2"] == pytest.approx(0.5)
    assert measured["fraction_score_uncertain"] == pytest.approx(0.0)
    assert measured["high_burst_count"] == pytest.approx(1.0)
    assert measured["max_consecutive_high_frames"] == pytest.approx(2.0)
    assert measured["mean_high_burst_duration_seconds"] == pytest.approx(1.0)
    assert measured["score_mean_abs_step"] == pytest.approx(1.0 / 3.0)
    assert measured["score_first_third_mean"] == pytest.approx(0.0)
    assert measured["score_middle_third_mean"] == pytest.approx(0.0)
    assert measured["score_last_third_mean"] == pytest.approx(1.0)
    assert measured["mean_detector_confidence"] == pytest.approx(0.7)
    assert measured["min_face_area_ratio"] == pytest.approx(0.02)
    assert measured["median_face_area_ratio"] == pytest.approx(0.045)
    assert measured["mean_crop_width"] == pytest.approx(20.0)
    assert measured["mean_crop_height"] == pytest.approx(30.0)
    assert measured["usable_face_fraction"] == pytest.approx(0.8)
    assert measured["mean_frame_blur"] == pytest.approx(12.5)
    assert "label" not in FEATURE_COLUMNS


def test_missing_face_measurements_stay_missing():
    measured = features_from_frames([_frame(0.0, 0.4), _frame(1.0, 0.6)])
    assert measured["score_mean"] == pytest.approx(0.5)
    assert measured["mean_detector_confidence"] is None
    assert measured["min_face_area_ratio"] is None
    assert measured["mean_crop_width"] is None
    assert measured["mean_frame_blur"] is None
    assert measured["score_mean_abs_step"] == pytest.approx(0.2)


def test_no_scored_frame_is_an_error():
    with pytest.raises(FeatureError):
        features_from_frames([_frame(0.0, None)])


def test_visual_measurement_reads_a_real_fixture():
    measured = measure_visual(FIXTURES / "vp9.webm", num_frames=5)
    assert measured["frame_width"] > 0
    assert measured["frame_height"] > 0
    assert measured["mean_frame_blur"] >= 0
    assert measured["video_fps"] > 0


def test_manifest_rejects_bad_labels_duplicates_and_synthetic_rows():
    with pytest.raises(ManifestError):
        validate_manifest(
            [
                {
                    "video_id": "a",
                    "file_path": "a.mp4",
                    "label": "authentic",
                    "dataset_name": "dfdc",
                    "source_group_id": "g",
                    "capture_condition": "c23",
                    "notes": "",
                }
            ]
        )
    with pytest.raises(ManifestError):
        validate_manifest(
            [
                {
                    "video_id": "a",
                    "file_path": "a.mp4",
                    "label": "real",
                    "dataset_name": "dfdc",
                    "source_group_id": "g",
                    "capture_condition": "",
                    "notes": "",
                },
                {
                    "video_id": "a",
                    "file_path": "b.mp4",
                    "label": "fake",
                    "dataset_name": "dfdc",
                    "source_group_id": "g",
                    "capture_condition": "",
                    "notes": "",
                },
            ]
        )
    with pytest.raises(ManifestError):
        validate_manifest(
            [
                {
                    "video_id": "a",
                    "file_path": "a.mp4",
                    "label": "real",
                    "dataset_name": "synthetic_demo_data",
                    "source_group_id": "g",
                    "capture_condition": "",
                    "notes": "",
                }
            ]
        )


def test_committed_zoo_manifest_is_a_regression_case_only():
    rows = load_manifest(MANIFEST)
    assert len(rows) == 1
    assert rows[0]["video_id"] == "zoo_jawed_ma_5634abfcde7d"
    assert rows[0]["label"] == "real"
    assert is_regression_case(rows[0])
    assert "1c7bdef9bc4e506a614a3f78cdce7d1b29146200030ee33c2012837df605516e" in rows[0]["notes"]


def test_source_groups_do_not_leak_across_splits():
    rows = []
    for index in range(3):
        rows.append(_video(f"real-{index}", "real", f"real-{index}", "ff++"))
        rows.append(_video(f"fake-{index}", "fake", f"fake-{index}", "ff++"))
    rows.append(_video("mixed-real", "real", "mixed", "ff++"))
    rows.append(_video("mixed-fake", "fake", "mixed", "ff++"))
    for seed in range(5):
        parts = assign_grouped_split(rows, seed=seed)
        assert_group_disjoint(parts)
        homes = {}
        for name in ("train", "validation", "test"):
            for row in parts[name]:
                homes.setdefault(row["source_group_id"], set()).add(name)
        assert all(len(place) == 1 for place in homes.values())
        assert group_ids(parts["train"]).isdisjoint(group_ids(parts["test"]))


def test_rejection_thresholds_come_from_validation_coverage():
    assert apply_rejection(0.1, low=0.3, high=0.7) == "real"
    assert apply_rejection(0.9, low=0.3, high=0.7) == "fake"
    assert apply_rejection(0.5, low=0.3, high=0.7) == "uncertain"
    chosen = select_thresholds([0.1, 0.2, 0.8, 0.9], ["real", "real", "fake", "fake"])
    assert chosen["low"] == 0.25
    assert chosen["high"] == 0.55


def test_extraction_logs_a_missing_file_and_reuses_one_detector(tmp_path):
    present = tmp_path / "clip.webm"
    present.write_bytes(b"not a video")

    class Detector:
        num_frames = 4

        def __init__(self):
            self.calls = 0

        def analyze_video(self, _path):
            self.calls += 1
            return type(
                "Result",
                (),
                {
                    "frame_results": [_frame(0.0, 0.2), _frame(0.5, 0.4), _frame(1.0, 0.6)],
                    "error_code": None,
                    "status": "scored",
                },
            )()

    detector = Detector()
    rows = [
        _video("present", "real", "g", "dfdc", file_path=str(present)),
        _video("absent", "fake", "h", "dfdc", file_path=str(tmp_path / "missing.webm")),
    ]
    extract_manifest(rows, detector, tmp_path / "out", measure=False)
    assert detector.calls == 1
    features = read_feature_csv(tmp_path / "out" / "features.csv")
    assert set(features) == {"present"}
    assert features["present"]["mean_frame_blur"] is None
    failures = (tmp_path / "out" / "failures.csv").read_text(encoding="utf-8")
    assert "absent" in failures
    assert "file_not_found" in failures
    metadata = json.loads((tmp_path / "out" / "extraction.json").read_text(encoding="utf-8"))
    assert metadata["synthetic"] is False
    assert metadata["measurement_source"] == "deepguard_frame_results"


def test_api_guard_refuses_a_running_server():
    with pytest.raises(ExtractionRefused):
        ensure_api_is_stopped(lambda: True)


def test_synthetic_metadata_cannot_train():
    with pytest.raises(TrainingError):
        assert_extraction_metadata({"synthetic": True, "measurement_source": "deepguard_frame_results", "feature_schema_version": "deepfake_rf_features_v1"})


def test_training_compares_v1_and_forest_without_using_the_regression_case(tmp_path):
    rows = []
    features = {}
    frames = {}
    for dataset, prefix in (("faceforensics++", "ff"), ("dfdc", "df")):
        for index in range(3):
            for label, score in (("real", 0.05), ("fake", 0.95)):
                video_id = f"{prefix}-{label}-{index}"
                group = f"{prefix}-{label}-{index}"
                rows.append(_video(video_id, label, group, dataset))
                features[video_id] = _signal(score)
                frames[video_id] = [_frame(float(offset), score) for offset in range(4)]
    rows.append(
        _video(
            "zoo-case",
            "real",
            "zoo_jawed_2005",
            "real_world_regression",
            notes="usage=regression_only",
        )
    )
    features["zoo-case"] = _signal(0.05)
    frames["zoo-case"] = [_frame(float(offset), 0.05) for offset in range(4)]
    report = train_and_evaluate(
        rows,
        features,
        frames,
        tmp_path / "run",
        seed=7,
        grid=({"n_estimators": 20, "max_depth": 4, "min_samples_leaf": 1},),
    )
    assert report["limitation"] == LIMITATION
    assert "zoo-case" not in report["split"]["comparable_test_videos"]
    assert report["regression_cases"][0]["video_id"] == "zoo-case"
    assert report["regression_cases"][0]["prediction"] in {"real", "fake", "uncertain"}
    forest = report["held_out"]["random_forest"]
    baseline = report["held_out"]["v1_baseline"]
    assert forest["rows"] == baseline["rows"]
    assert forest["rows"] > 0
    assert forest["non_abstained"]["accuracy"] == pytest.approx(1.0)
    assert baseline["non_abstained"]["accuracy"] == pytest.approx(1.0)
    assert forest["ranking"]["score_semantics"] == "uncalibrated_class_vote_fraction"
    assert report["calibration"]["applied"] is False
    assert any(item["status"] == "scored" for item in report["cross_dataset"])
    config = json.loads((tmp_path / "run" / "training_config.json").read_text(encoding="utf-8"))
    train_labels = []
    for row in rows:
        if row["source_group_id"] in report["split"]["train_groups"]:
            train_labels.append(1 if row["label"] == "fake" else 0)
    expected = compute_class_weight(class_weight="balanced", classes=np.array([0, 1]), y=np.asarray(train_labels))
    assert config["class_weight"]["mode"] == "balanced"
    assert config["class_weight"]["real"] == pytest.approx(expected[0])
    assert config["class_weight"]["fake"] == pytest.approx(expected[1])
    rare_class_weights = compute_class_weight(
        class_weight="balanced",
        classes=np.array([0, 1]),
        y=np.array([0, 1, 1, 1, 1, 1, 1, 1]),
    )
    assert rare_class_weights[0] > rare_class_weights[1]
    loaded = load_model(tmp_path / "run" / "model.joblib")
    assert loaded["model_version"] == "deepfake_rf_v2"
    assert (tmp_path / "run" / "evaluation_report.md").is_file()
    assert "not a measured real-world accuracy" in (tmp_path / "run" / "evaluation_report.md").read_text(encoding="utf-8")


def test_v1_baseline_labels_follow_the_existing_rule():
    assert v1_prediction([_frame(float(index), 0.05) for index in range(4)]) == "real"
    assert v1_prediction([_frame(float(index), 0.95) for index in range(4)]) == "fake"
    assert v1_prediction([_frame(0.0, 0.9), _frame(0.4, 0.1), _frame(0.8, 0.1)]) == "uncertain"


def test_regression_only_manifest_does_not_fit(tmp_path):
    rows = load_manifest(MANIFEST)
    with pytest.raises(TrainingError):
        train_and_evaluate(rows, {}, {}, tmp_path / "empty")


def _video(video_id, label, group, dataset, *, file_path="clip.mp4", notes=""):
    return {
        "video_id": video_id,
        "file_path": file_path,
        "label": label,
        "dataset_name": dataset,
        "source_group_id": group,
        "capture_condition": "local",
        "notes": notes,
    }


def _signal(score):
    return {
        "score_mean": score,
        "score_max": score,
        "fraction_score_ge_0_8": 1.0 if score >= 0.8 else 0.0,
    }
