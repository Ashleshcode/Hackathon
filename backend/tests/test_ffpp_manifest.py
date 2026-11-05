"""Filename fixtures for the FaceForensics++ manifest builder. These files are empty and are not training data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.experiments.deepfake_rf.extract import extract_manifest
from app.experiments.deepfake_rf.ffpp_manifest import (
    ManifestBuildError,
    ManifestExistsError,
    build_faceforensics_manifest,
    build_rows,
    discover_faceforensics,
    load_official_splits,
)
from app.experiments.deepfake_rf.manifest import is_regression_case, load_manifest, missing_videos
from app.experiments.deepfake_rf.split_audit import (
    SplitAuditError,
    audit_manifest,
    overlapping_groups,
    overlapping_sequence_ids,
)

ZOO = Path(__file__).resolve().parents[1] / "experiments" / "deepfake_rf" / "manifests" / "manifest.csv"
METHODS = ("Deepfakes", "Face2Face", "FaceSwap", "NeuralTextures")


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def _tree(root: Path) -> None:
    for identity in ("000", "001", "002", "010", "011", "020", "021"):
        _touch(root / "original_sequences" / "youtube" / "c23" / "videos" / f"{identity}.mp4")
    _touch(root / "original_sequences" / "youtube" / "c40" / "videos" / "000.mp4")
    _touch(root / "original_sequences" / "actors" / "c23" / "videos" / "000.mp4")
    pairs = {
        "Deepfakes": ("000_001.mp4", "001_000.mp4"),
        "Face2Face": ("001_002.mp4",),
        "FaceSwap": ("010_011.mp4",),
        "NeuralTextures": ("020_021.mp4",),
    }
    for method, names in pairs.items():
        for name in names:
            _touch(root / "manipulated_sequences" / method / "c23" / "videos" / name)
    _touch(root / "manipulated_sequences" / "Deepfakes" / "c40" / "videos" / "000_001.mp4")
    _touch(root / "manipulated_sequences" / "Face2Face" / "c23" / "videos" / "001_999.mp4")
    _touch(root / "manipulated_sequences" / "FaceShifter" / "c23" / "videos" / "000_001.mp4")
    _touch(root / "manipulated_sequences" / "DeepFakeDetection" / "c23" / "videos" / "000_001.mp4")
    splits = root / "splits"
    splits.mkdir()
    (splits / "train.json").write_text(json.dumps([["000", "001"], ["010", "011"]]), encoding="utf-8")
    (splits / "val.json").write_text(json.dumps([["020", "021"]]), encoding="utf-8")
    (splits / "test.json").write_text(json.dumps([["001", "010"]]), encoding="utf-8")


def test_builder_covers_methods_and_keeps_connected_identities_together(tmp_path):
    root = tmp_path / "ffpp"
    _tree(root)
    output = tmp_path / "faceforensics_c23.csv"
    report = build_faceforensics_manifest(root, output, existing_manifest=ZOO)
    assert report["real"] == 7
    assert report["fake"] == 5
    assert report["by_method"] == {method: 1 if method != "Deepfakes" else 2 for method in METHODS}
    assert {item["video_id"] for item in report["unmatched"]} == {"ffpp_c23_Face2Face_001_999"}
    assert report["unknown_methods"] == ["DeepFakeDetection", "FaceShifter"]
    assert "original_sequences/youtube/c40" in report["skipped_other_compression"]
    assert "manipulated_sequences/Deepfakes/c40" in report["skipped_other_compression"]
    assert "original_sequences/actors" in report["skipped_other_compression"]
    assert "001" in report["official_cross_split_ids"]
    assert "010" in report["official_cross_split_ids"]

    rows = load_manifest(output)
    zoo = rows[0]
    assert zoo["video_id"] == "zoo_jawed_ma_5634abfcde7d"
    assert zoo["file_path"] == "backend/data/media/ma_5634abfcde7d.webm"
    assert zoo["label"] == "real"
    assert zoo["dataset_name"] == "real_world_regression"
    assert zoo["source_group_id"] == "zoo_jawed_2005"
    assert zoo["usage"] == "regression_only"
    assert "sha256=1c7bdef9bc4e506a614a3f78cdce7d1b29146200030ee33c2012837df605516e" in zoo["notes"]
    assert is_regression_case(zoo)

    trainable = [row for row in rows if not is_regression_case(row)]
    assert {row["capture_condition"] for row in trainable if row["label"] == "fake"} == {f"c23/{method}" for method in METHODS}
    assert all(row["dataset_name"] == "faceforensics++" for row in trainable)
    assert all(row["usage"] == "trainable" for row in trainable)
    assert all(Path(row["file_path"]).is_file() for row in trainable)
    chain = "ffpp_c23_000_001_002"
    assert {row["source_group_id"] for row in trainable if "000" in row["video_id"] or "002" in row["video_id"]} == {chain}
    swapped = [row for row in trainable if row["video_id"] in {"ffpp_c23_Deepfakes_000_001", "ffpp_c23_Deepfakes_001_000"}]
    assert len(swapped) == 2
    assert {row["source_group_id"] for row in swapped} == {chain}
    assert "001_999" not in output.read_text(encoding="utf-8")
    assert "FaceShifter" not in output.read_text(encoding="utf-8")
    assert "c40" not in output.read_text(encoding="utf-8")

    audit = audit_manifest(rows)
    assert audit["split_assignment"] == "grouped"
    assert "zoo_jawed_ma_5634abfcde7d" in audit["regression_video_ids"]
    placed = set(audit["train_groups"]) | set(audit["validation_groups"]) | set(audit["test_groups"])
    assert chain in placed
    assert "zoo_jawed_2005" not in placed
    sequence_homes = {}
    for name, identities in audit["sequence_ids_by_split"].items():
        for identity in identities:
            sequence_homes.setdefault(identity, set()).add(name)
    assert all(len(homes) == 1 for homes in sequence_homes.values())
    assert missing_videos(trainable) == []


def test_missing_original_is_excluded_without_guessing_a_group(tmp_path):
    root = tmp_path / "ffpp"
    _touch(root / "original_sequences" / "youtube" / "c23" / "videos" / "000.mp4")
    _touch(root / "manipulated_sequences" / "Deepfakes" / "c23" / "videos" / "000_004.mp4")
    for method in METHODS[1:]:
        (root / "manipulated_sequences" / method / "c23" / "videos").mkdir(parents=True)
    discovered = discover_faceforensics(root)
    rows, report = build_rows(discovered, {})
    assert report["real"] == 1
    assert report["fake"] == 0
    assert report["unmatched"][0]["missing"] == ["source"]
    assert rows[0]["source_group_id"] == "ffpp_c23_000"


def test_unknown_method_duplicate_and_ambiguous_names_do_not_guess(tmp_path):
    root = tmp_path / "unknown"
    _touch(root / "original_sequences" / "youtube" / "c23" / "videos" / "000.mp4")
    _touch(root / "manipulated_sequences" / "FaceShifter" / "c23" / "videos" / "000_001.mp4")
    for method in METHODS:
        (root / "manipulated_sequences" / method / "c23" / "videos").mkdir(parents=True)
    discovered = discover_faceforensics(root)
    assert discovered["unknown_methods"] == ["FaceShifter"]
    assert discovered["manipulations"] == []

    duplicate = tmp_path / "duplicate"
    _touch(duplicate / "original_sequences" / "youtube" / "c23" / "videos" / "000.mp4")
    _touch(duplicate / "original_sequences" / "youtube" / "c23" / "videos" / "00.mp4")
    (duplicate / "manipulated_sequences").mkdir()
    with pytest.raises(ManifestBuildError, match="Duplicate original sequence 000"):
        discover_faceforensics(duplicate)

    repeated = tmp_path / "repeated"
    _touch(repeated / "original_sequences" / "youtube" / "c23" / "videos" / "000.mp4")
    _touch(repeated / "original_sequences" / "youtube" / "c23" / "videos" / "001.mp4")
    _touch(repeated / "manipulated_sequences" / "Deepfakes" / "c23" / "videos" / "000_001.mp4")
    _touch(repeated / "manipulated_sequences" / "Deepfakes" / "c23" / "videos" / "0_1.mp4")
    with pytest.raises(ManifestBuildError, match="Duplicate manipulated video"):
        discover_faceforensics(repeated)

    output = tmp_path / "should-not-exist.csv"
    for name in ("weird.mp4", "000_001_002.mp4", "000_000.mp4"):
        broken = tmp_path / name
        _touch(broken / "original_sequences" / "youtube" / "c23" / "videos" / "000.mp4")
        _touch(broken / "manipulated_sequences" / "Deepfakes" / "c23" / "videos" / name)
        with pytest.raises(ManifestBuildError, match="Ambiguous"):
            build_faceforensics_manifest(broken, output)
        assert not output.exists()


def test_a_pair_listed_in_two_official_splits_is_rejected(tmp_path):
    root = tmp_path / "splits"
    _touch(root / "original_sequences" / "youtube" / "c23" / "videos" / "000.mp4")
    (root / "manipulated_sequences").mkdir()
    splits = root / "splits"
    splits.mkdir()
    (splits / "train.json").write_text(json.dumps([["000", "001"]]), encoding="utf-8")
    (splits / "test.json").write_text(json.dumps([["0", "1"]]), encoding="utf-8")
    with pytest.raises(ManifestBuildError, match="ambiguous"):
        load_official_splits(root)


def test_hand_built_overlap_is_rejected_before_a_split_is_assigned():
    leaked = [
        {"video_id": "a", "label": "real", "source_group_id": "left", "notes": "sequence=000", "dataset_name": "faceforensics++"},
        {"video_id": "b", "label": "fake", "source_group_id": "right", "notes": "target=000; source=001", "dataset_name": "faceforensics++"},
    ]
    assert overlapping_sequence_ids(leaked) == ["000"]
    with pytest.raises(SplitAuditError, match="more than one source group"):
        audit_manifest(leaked)
    parts = {
        "train": [{"source_group_id": "shared"}],
        "validation": [{"source_group_id": "other"}],
        "test": [{"source_group_id": "shared"}],
    }
    assert overlapping_groups(parts) == ["shared"]


class _StubDetector:
    num_frames = 2

    def analyze_video(self, path):
        return {
            "frame_results": [
                {"timestamp_seconds": 0.0, "status": "scored", "fake_score": 0.1},
                {"timestamp_seconds": 1.0, "status": "scored", "fake_score": 0.2},
            ]
        }


def test_generated_manifest_is_accepted_by_the_existing_extractor(tmp_path):
    root = tmp_path / "ffpp"
    _tree(root)
    output = tmp_path / "manifest.csv"
    build_faceforensics_manifest(root, output, existing_manifest=ZOO)
    rows = load_manifest(output)
    trainable = [row for row in rows if row["dataset_name"] == "faceforensics++"]
    assert missing_videos(trainable) == []
    metadata = extract_manifest(trainable[:1], _StubDetector(), tmp_path / "extract", measure=False)
    assert metadata["synthetic"] is False
    assert metadata["measurement_source"] == "deepguard_frame_results"
    assert metadata["failed_video_ids"] == []
    assert metadata["video_ids"] == [trainable[0]["video_id"]]
    with pytest.raises(ManifestExistsError, match="already exists"):
        build_faceforensics_manifest(root, output, existing_manifest=ZOO)
