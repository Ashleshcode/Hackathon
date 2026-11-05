"""Write a FaceForensics++ C23 manifest from a local dataset. Nothing is downloaded.

Example:
    .venv\\Scripts\\python.exe backend/scripts/build_ffpp_manifest.py ^
        --dataset-root D:\\data\\FaceForensics++ ^
        --output backend/experiments/deepfake_rf/manifests/faceforensics_c23.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.experiments.deepfake_rf.ffpp_manifest import (
    ManifestBuildError,
    build_rows,
    discover_faceforensics,
    load_official_splits,
    regression_rows,
    write_manifest,
)
from app.experiments.deepfake_rf.manifest import repo_root
from app.experiments.deepfake_rf.split_audit import SplitAuditError, audit_manifest


def main() -> int:
    arguments = sys.argv[1:]
    if "--dataset-root" not in arguments or "--output" not in arguments:
        print("Usage: build_ffpp_manifest.py --dataset-root DIRECTORY --output MANIFEST.csv [--force]")
        return 2
    dataset_root = Path(arguments[arguments.index("--dataset-root") + 1])
    output = Path(arguments[arguments.index("--output") + 1])
    overwrite = "--force" in arguments
    existing = repo_root() / "backend" / "experiments" / "deepfake_rf" / "manifests" / "manifest.csv"
    try:
        discovered = discover_faceforensics(dataset_root)
        rows, report = build_rows(discovered, load_official_splits(dataset_root))
        rows = [*regression_rows(existing), *rows]
        audit = audit_manifest(rows)
        write_manifest(output, rows, overwrite=overwrite)
    except (ManifestBuildError, SplitAuditError, OSError) as exc:
        print(exc)
        return 2
    print(f"real: {report['real']}")
    print(f"fake: {report['fake']}")
    print(f"source groups: {report['source_group_count']}")
    print(f"unmatched manipulated videos: {len(report['unmatched'])}")
    print(f"unknown manipulation methods: {', '.join(report['unknown_methods']) or 'none'}")
    print(f"official ids listed in more than one published split: {len(report['official_cross_split_ids'])}")
    print(f"split audit: {audit['split_assignment']}")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
