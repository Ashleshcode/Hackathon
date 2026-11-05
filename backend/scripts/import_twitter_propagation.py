"""Import a local Twitter15 or Twitter16 directory. Nothing is downloaded.

Example:
    .venv\\Scripts\\python.exe backend/scripts/import_twitter_propagation.py --dataset-root D:\\data\\Twitter15_16_dataset
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dissemination.import_dataset import PropagationImportError, import_propagation_directory


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--dataset-root":
        print("Usage: import_twitter_propagation.py --dataset-root DIRECTORY")
        return 2
    try:
        report = import_propagation_directory(Path(sys.argv[2]))
    except PropagationImportError as exc:
        print(exc)
        return 2
    for dataset in report["datasets"]:
        print(
            f"{dataset['dataset_name']}: imported {dataset['imported_case_count']} cases, "
            f"{dataset['malformed_file_count']} malformed files"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
