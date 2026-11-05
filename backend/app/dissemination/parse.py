"""Parse Twitter15 and Twitter16 tree files. This module does not download data."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

DATASET_REFERENCE = "https://github.com/gszswork/Twitter15_16_dataset"
CANONICAL_DATASETS = {"twitter15": "twitter15", "twitter16": "twitter16"}


class ParseError(ValueError):
    pass


@dataclass
class TreeNode:
    user_id: str
    tweet_id: str
    delay_minutes: float | None
    raw_delay: str


@dataclass
class TreeEdge:
    parent: TreeNode
    child: TreeNode
    line_number: int


@dataclass
class ParsedTree:
    source_tweet_id: str
    edges: list[TreeEdge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def canonical_dataset_name(name: str) -> str | None:
    return CANONICAL_DATASETS.get(name.strip().lower())


def case_id_for(dataset_name: str, source_tweet_id: str) -> str:
    return f"prop_{dataset_name}_{source_tweet_id}"


def parse_delay(value: str) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _parse_node(text: str) -> TreeNode | None:
    body = text.strip()
    if len(body) < 2 or body[0] != "[" or body[-1] != "]":
        return None
    inner = body[1:-1]
    for quote in ("'", '"'):
        try:
            fields = next(csv.reader([inner], delimiter=",", quotechar=quote, skipinitialspace=True))
        except csv.Error:
            continue
        if len(fields) != 3:
            continue
        user_id, tweet_id, raw_delay = (field.strip() for field in fields)
        if not user_id or not tweet_id:
            return None
        return TreeNode(user_id, tweet_id, parse_delay(raw_delay), raw_delay)
    return None


def is_root_sentinel(node: TreeNode) -> bool:
    return node.user_id == "ROOT" and node.tweet_id == "ROOT"


def parse_tree_text(source_tweet_id: str, text: str) -> ParsedTree:
    parsed = ParsedTree(source_tweet_id=source_tweet_id)
    seen: set[tuple[str, str]] = set()
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "->" not in line:
            parsed.warnings.append(f"line {line_number}: missing parent-to-child arrow")
            continue
        left, right = line.split("->", 1)
        parent = _parse_node(left)
        child = _parse_node(right)
        if parent is None or child is None:
            parsed.warnings.append(f"line {line_number}: node tuple could not be read")
            continue
        if is_root_sentinel(child):
            parsed.warnings.append(f"line {line_number}: child is the ROOT sentinel")
            continue
        if not is_root_sentinel(parent) and parent.tweet_id == child.tweet_id:
            parsed.warnings.append(f"line {line_number}: skipped a self-loop on {child.tweet_id}")
            continue
        key = (parent.tweet_id, child.tweet_id)
        if key in seen:
            parsed.warnings.append(f"line {line_number}: duplicate edge {parent.tweet_id} -> {child.tweet_id}")
            continue
        seen.add(key)
        if parent.delay_minutes is None and not is_root_sentinel(parent):
            parsed.warnings.append(f"line {line_number}: parent delay {parent.raw_delay!r} is not a number")
        if child.delay_minutes is None:
            parsed.warnings.append(f"line {line_number}: child delay {child.raw_delay!r} is not a number")
        parsed.edges.append(TreeEdge(parent, child, line_number))
    return parsed


def read_tree_file(path: Path) -> ParsedTree:
    source_tweet_id = path.stem
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        parsed = ParsedTree(source_tweet_id=source_tweet_id)
        parsed.warnings.append(f"file is not UTF-8: {exc.reason}")
        return parsed
    return parse_tree_text(source_tweet_id, text)


def read_label_file(path: Path) -> tuple[dict[str, str], list[str]]:
    labels: dict[str, str] = {}
    warnings: list[str] = []
    if not path.is_file():
        return labels, ["label.txt is missing"]
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        return labels, [f"label.txt is not UTF-8: {exc.reason}"]
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            warnings.append(f"label.txt line {line_number}: missing label separator")
            continue
        label, source_tweet_id = line.split(":", 1)
        label = label.strip()
        source_tweet_id = source_tweet_id.strip()
        if not label or not source_tweet_id:
            warnings.append(f"label.txt line {line_number}: blank label or source id")
            continue
        if source_tweet_id in labels:
            warnings.append(f"label.txt line {line_number}: duplicate label for {source_tweet_id}")
            continue
        labels[source_tweet_id] = label
    return labels, warnings


def read_source_posts(path: Path) -> tuple[dict[str, str], list[str]]:
    posts: dict[str, str] = {}
    warnings: list[str] = []
    if not path.is_file():
        return posts, ["source_tweets.txt is missing"]
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        return posts, [f"source_tweets.txt is not UTF-8: {exc.reason}"]
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        if "\t" not in raw_line:
            warnings.append(f"source_tweets.txt line {line_number}: missing tab separator")
            continue
        source_tweet_id, text = raw_line.split("\t", 1)
        source_tweet_id = source_tweet_id.strip()
        text = text.strip()
        if not source_tweet_id or not text:
            warnings.append(f"source_tweets.txt line {line_number}: blank source id or text")
            continue
        if source_tweet_id in posts:
            warnings.append(f"source_tweets.txt line {line_number}: duplicate source text for {source_tweet_id}")
            continue
        posts[source_tweet_id] = text
    return posts, warnings
