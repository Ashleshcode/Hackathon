"""Train and evaluate the experimental Random Forest.

The feature directory must come from rf_extract_features.py.
A manifest that only contains the zoo regression case stops before fitting.

Example:
    .venv\\Scripts\\python.exe backend/scripts/rf_train_evaluate.py ^
        --manifest backend/experiments/deepfake_rf/manifests/manifest.csv ^
        --extraction-dir backend/experiments/deepfake_rf/runs/extract ^
        --output-dir backend/experiments/deepfake_rf/runs/deepfake_rf_v2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.experiments.deepfake_rf.io import read_feature_csv, read_frames_jsonl
from app.experiments.deepfake_rf.manifest import ManifestError, load_manifest
from app.experiments.deepfake_rf.train import TrainingError, assert_extraction_metadata, train_and_evaluate


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the experimental forest and compare it with the V1 rule.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--extraction-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    extraction = Path(args.extraction_dir)
    try:
        metadata = json.loads((extraction / "extraction.json").read_text(encoding="utf-8"))
        assert_extraction_metadata(metadata)
        report = train_and_evaluate(
            load_manifest(args.manifest),
            read_feature_csv(extraction / "features.csv"),
            read_frames_jsonl(extraction / "frames.jsonl"),
            args.output_dir,
            manifest_path=args.manifest,
        )
    except (ManifestError, TrainingError, OSError, json.JSONDecodeError) as exc:
        print(exc)
        return 2
    held = report["held_out"]["random_forest"]["non_abstained"]
    print(
        f"Wrote {args.output_dir}. Held-out forest selective accuracy {held['accuracy']}. "
        "This is not a measured real-world accuracy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
