"""Extract DeepGuard features for the Random Forest experiment.

Stop the FastAPI server first. This process loads the existing detector once.

Example:
    .venv\\Scripts\\python.exe backend/scripts/rf_extract_features.py ^
        --manifest backend/experiments/deepfake_rf/manifests/manifest.csv ^
        --output-dir backend/experiments/deepfake_rf/runs/extract
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.experiments.deepfake_rf.extract import ExtractionRefused, api_port_open, ensure_api_is_stopped, extract_manifest
from app.experiments.deepfake_rf.manifest import ManifestError, load_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract one DeepGuard feature vector per manifest video.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--allow-concurrent-gpu", action="store_true")
    args = parser.parse_args()
    try:
        rows = load_manifest(args.manifest)
        if not args.allow_concurrent_gpu:
            ensure_api_is_stopped(api_port_open)
        from app.models.deepfake_detector import DeepfakeDetectorService

        detector = DeepfakeDetectorService()
        metadata = extract_manifest(rows, detector, args.output_dir)
    except (ManifestError, ExtractionRefused, OSError) as exc:
        print(exc)
        return 2
    print(
        f"Extracted {len(metadata['video_ids'])} videos. "
        f"Failed {len(metadata['failed_video_ids'])}. Output: {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
