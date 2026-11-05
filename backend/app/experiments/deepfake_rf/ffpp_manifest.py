"""Build a FaceForensics++ C23 manifest from a local dataset directory.

The official manipulated filename is ``target_source.mp4``. The published split
files use the same order: each entry is ``[target, source]``. Deepfakes and
FaceSwap place the source identity onto the target sequence. Face2Face and
NeuralTextures reenact the source onto the target. Either reading still puts
two original sequences into one video.

Grouping by the target alone would let the source original fall in another
split. The manifest therefore links every original id that appears together in
a manipulated filename and keeps that whole connected component in one
``source_group_id``. An unmatched target or source is reported and omitted.
An ambiguous filename is an error.

Nothing is downloaded and no video bytes are copied.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from app.experiments.deepfake_rf.manifest import (
    MANIFEST_COLUMNS,
    is_regression_case,
    load_manifest,
)

DATASET_NAME = "faceforensics++"
OFFICIAL_NAME = "FaceForensics++"
COMPRESSION = "c23"
METHODS = ("Deepfakes", "Face2Face", "FaceSwap", "NeuralTextures")
ORIGINAL_NAME = re.compile(r"^(\d+)\.mp4$", re.IGNORECASE)
MANIPULATED_NAME = re.compile(r"^(\d+)_(\d+)\.mp4$", re.IGNORECASE)
OUTPUT_COLUMNS = (*MANIFEST_COLUMNS, "usage")


class ManifestBuildError(ValueError):
    pass


class ManifestExistsError(ManifestBuildError):
    pass


def canonical_id(raw: str) -> str:
    if not raw.isdigit():
        raise ManifestBuildError(f"Sequence id {raw!r} is not numeric.")
    return str(int(raw)).zfill(3)


def _videos_dir(method_root: Path) -> Path | None:
    candidate = method_root / COMPRESSION / "videos"
    if candidate.is_dir():
        return candidate
    return None


def _mp4_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".mp4")


def _read_split_file(path: Path) -> list[tuple[str, str] | str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestBuildError(f"{path.name} is not valid JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ManifestBuildError(f"{path.name} must be a JSON list.")
    entries: list[tuple[str, str] | str] = []
    kinds: set[str] = set()
    for item in payload:
        if isinstance(item, str) and item.isdigit():
            kinds.add("id")
            entries.append(canonical_id(item))
        elif (
            isinstance(item, list)
            and len(item) == 2
            and all(isinstance(part, str) and part.isdigit() for part in item)
        ):
            kinds.add("pair")
            entries.append((canonical_id(item[0]), canonical_id(item[1])))
        else:
            raise ManifestBuildError(f"{path.name} has an entry that is not an id or a target-source pair.")
    if len(kinds) > 1:
        raise ManifestBuildError(f"{path.name} mixes bare ids and target-source pairs.")
    return entries


def load_official_splits(root: Path) -> dict[tuple[str, str], str]:
    """Map a manipulated pair to train, val, or test when the local splits exist."""
    split_dir = root / "splits"
    if not split_dir.is_dir():
        return {}
    found: dict[tuple[str, str], str] = {}
    for name in ("train", "val", "test"):
        path = split_dir / f"{name}.json"
        if not path.is_file():
            continue
        for entry in _read_split_file(path):
            if not isinstance(entry, tuple):
                raise ManifestBuildError(
                    f"{path.name} lists bare sequence ids. Expected target-source pairs like the published splits."
                )
            if entry in found:
                raise ManifestBuildError(
                    f"Pair {entry[0]}_{entry[1]} is in both {found[entry]} and {name}. The official split is ambiguous."
                )
            found[entry] = name
    return found


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self.parent.setdefault(item, item)

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if (int(left_root), left_root) <= (int(right_root), right_root):
            self.parent[right_root] = left_root
        else:
            self.parent[left_root] = right_root


def _component_ids(union: _UnionFind) -> dict[str, str]:
    members: dict[str, list[str]] = {}
    for item in union.parent:
        members.setdefault(union.find(item), []).append(item)
    labels = {}
    for grouped in members.values():
        ordered = tuple(sorted(grouped, key=lambda value: (int(value), value)))
        label = "ffpp_c23_" + "_".join(ordered)
        for item in ordered:
            labels[item] = label
    return labels


def _note(parts: list[str]) -> str:
    return "; ".join(parts)


def discover_faceforensics(root: Path) -> dict:
    """Read C23 YouTube originals and the four manipulation folders. Does not open video frames."""
    root = Path(root)
    original_dir = root / "original_sequences" / "youtube" / COMPRESSION / "videos"
    manipulated_root = root / "manipulated_sequences"
    if not original_dir.is_dir() or not manipulated_root.is_dir():
        raise ManifestBuildError(
            "Expected original_sequences/youtube/c23/videos and manipulated_sequences under the dataset root. "
            "The dataset is not downloaded."
        )

    originals: dict[str, Path] = {}
    ambiguous: list[str] = []
    for path in _mp4_files(original_dir):
        match = ORIGINAL_NAME.match(path.name)
        if match is None:
            ambiguous.append(str(path))
            continue
        identity = canonical_id(match.group(1))
        if identity in originals:
            raise ManifestBuildError(f"Duplicate original sequence {identity}: {originals[identity]} and {path}")
        originals[identity] = path
    if ambiguous:
        raise ManifestBuildError("Ambiguous original filenames: " + "; ".join(ambiguous))

    manipulations: list[dict] = []
    unknown_methods: list[str] = []
    missing_c23: list[str] = []
    unmatched: list[dict] = []
    seen_ids: dict[str, Path] = {}
    for method_dir in sorted(path for path in manipulated_root.iterdir() if path.is_dir()):
        if method_dir.name not in METHODS:
            unknown_methods.append(method_dir.name)
            continue
        videos = _videos_dir(method_dir)
        if videos is None:
            missing_c23.append(method_dir.name)
            continue
        for path in _mp4_files(videos):
            match = MANIPULATED_NAME.match(path.name)
            if match is None:
                raise ManifestBuildError(f"Ambiguous manipulated filename: {path}")
            target = canonical_id(match.group(1))
            source = canonical_id(match.group(2))
            if target == source:
                raise ManifestBuildError(f"Ambiguous self-pair filename: {path}")
            video_id = f"ffpp_c23_{method_dir.name}_{target}_{source}"
            if video_id in seen_ids:
                raise ManifestBuildError(f"Duplicate manipulated video {video_id}: {seen_ids[video_id]} and {path}")
            seen_ids[video_id] = path
            record = {
                "method": method_dir.name,
                "target": target,
                "source": source,
                "path": path,
                "video_id": video_id,
            }
            if target not in originals or source not in originals:
                missing = [
                    name
                    for name, present in (("target", target in originals), ("source", source in originals))
                    if not present
                ]
                unmatched.append({**record, "missing": missing, "path": str(path)})
                continue
            manipulations.append(record)

    skipped_other_compression: list[str] = []
    actors = root / "original_sequences" / "actors"
    if actors.is_dir():
        skipped_other_compression.append("original_sequences/actors")
    for base in (root / "original_sequences" / "youtube",):
        if base.is_dir():
            for child in base.iterdir():
                if child.is_dir() and child.name != COMPRESSION:
                    skipped_other_compression.append(f"original_sequences/youtube/{child.name}")
    for method in METHODS:
        method_dir = manipulated_root / method
        if not method_dir.is_dir():
            continue
        for child in method_dir.iterdir():
            if child.is_dir() and child.name != COMPRESSION:
                skipped_other_compression.append(f"manipulated_sequences/{method}/{child.name}")

    return {
        "originals": originals,
        "manipulations": manipulations,
        "unmatched": unmatched,
        "unknown_methods": unknown_methods,
        "missing_c23": missing_c23,
        "skipped_other_compression": skipped_other_compression,
    }


def build_rows(discovered: dict, official_pairs: dict[tuple[str, str], str]) -> tuple[list[dict], dict]:
    union = _UnionFind()
    for identity in discovered["originals"]:
        union.add(identity)
    for item in discovered["manipulations"]:
        union.union(item["target"], item["source"])
    labels = _component_ids(union)

    id_splits: dict[str, set[str]] = {}
    for (target, source), split_name in official_pairs.items():
        id_splits.setdefault(target, set()).add(split_name)
        id_splits.setdefault(source, set()).add(split_name)
    cross_split_ids = sorted(identity for identity, names in id_splits.items() if len(names) > 1)

    rows: list[dict] = []
    for identity, path in sorted(discovered["originals"].items()):
        component = labels[identity]
        members = ",".join(component.removeprefix("ffpp_c23_").split("_"))
        official = sorted(id_splits.get(identity, []))
        rows.append(
            {
                "video_id": f"ffpp_c23_original_{identity}",
                "file_path": str(path.resolve()),
                "label": "real",
                "dataset_name": DATASET_NAME,
                "source_group_id": component,
                "capture_condition": "c23/original",
                "usage": "trainable",
                "notes": _note(
                    [
                        f"dataset={OFFICIAL_NAME}",
                        "compression=c23",
                        "method=original",
                        "source_collection=youtube",
                        f"sequence={identity}",
                        f"component={members}",
                        "filename_order=target_source",
                        f"official_split={'+'.join(official) if official else 'not_supplied'}",
                        "access=local_research_copy_not_redistributed",
                    ]
                ),
            }
        )
    for item in sorted(discovered["manipulations"], key=lambda record: (record["method"], record["target"], record["source"])):
        component = labels[item["target"]]
        members = ",".join(component.removeprefix("ffpp_c23_").split("_"))
        pair = (item["target"], item["source"])
        pair_split = official_pairs.get(pair)
        rows.append(
            {
                "video_id": item["video_id"],
                "file_path": str(item["path"].resolve()),
                "label": "fake",
                "dataset_name": DATASET_NAME,
                "source_group_id": component,
                "capture_condition": f"c23/{item['method']}",
                "usage": "trainable",
                "notes": _note(
                    [
                        f"dataset={OFFICIAL_NAME}",
                        "compression=c23",
                        f"method={item['method']}",
                        f"target={item['target']}",
                        f"source={item['source']}",
                        f"component={members}",
                        "filename_order=target_source",
                        f"official_split={pair_split or 'not_supplied'}",
                        "access=local_research_copy_not_redistributed",
                    ]
                ),
            }
        )

    real = sum(row["label"] == "real" for row in rows)
    fake = sum(row["label"] == "fake" for row in rows)
    by_method = {method: sum(row["capture_condition"] == f"c23/{method}" for row in rows) for method in METHODS}
    report = {
        "real": real,
        "fake": fake,
        "by_method": by_method,
        "source_group_count": len({row["source_group_id"] for row in rows}),
        "unmatched": [
            {
                "video_id": item["video_id"],
                "method": item["method"],
                "target": item["target"],
                "source": item["source"],
                "missing": item["missing"],
            }
            for item in discovered["unmatched"]
        ],
        "unknown_methods": discovered["unknown_methods"],
        "missing_c23": discovered["missing_c23"],
        "skipped_other_compression": discovered["skipped_other_compression"],
        "official_cross_split_ids": cross_split_ids,
        "grouping": (
            "Connected components of original sequence ids. "
            "A manipulated file target_source.mp4 links those two ids. "
            "The source_group_id lists every id in the component so an original and its variants stay together."
        ),
    }
    return rows, report


def regression_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    kept = []
    for row in load_manifest(path):
        if not is_regression_case(row):
            continue
        exported = {column: row.get(column, "") for column in MANIFEST_COLUMNS}
        exported["usage"] = "regression_only"
        kept.append(exported)
    return kept


def write_manifest(path: Path, rows: list[dict], *, overwrite: bool = False) -> None:
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise ManifestExistsError(f"{destination} already exists. Re-run with overwrite confirmed to replace it.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTPUT_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})


def build_faceforensics_manifest(
    dataset_root: Path,
    output: Path,
    *,
    existing_manifest: Path | None = None,
    overwrite: bool = False,
) -> dict:
    discovered = discover_faceforensics(dataset_root)
    official = load_official_splits(dataset_root)
    rows, report = build_rows(discovered, official)
    if existing_manifest is not None:
        rows = [*regression_rows(existing_manifest), *rows]
    if not rows:
        raise ManifestBuildError("No FaceForensics++ videos or regression rows were available to write.")
    write_manifest(output, rows, overwrite=overwrite)
    report["output"] = str(Path(output))
    report["rows"] = len(rows)
    return report
