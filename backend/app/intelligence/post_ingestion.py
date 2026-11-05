"""Parse CSV/JSON post records into one schema, rejecting bad records row by row.

Problems with a single record become row errors. Only problems with the file as
a whole (unreadable, wrong structure, too many records) raise ImportFileError.
"""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

MAX_RECORDS = 2000
REQUIRED_FIELDS = ("post_id", "platform", "account_id", "timestamp")
OPTIONAL_FIELDS = ("text", "url", "media_hash", "media_reference")
SOURCE_TYPES = ("uploaded_dataset", "curated_sample", "synthetic_demo_data")


class ImportFileError(ValueError):
    """The file as a whole can't be imported."""


class RecordError(ValueError):
    """One record is invalid. The message is shown to the investigator."""


@dataclass(frozen=True)
class Post:
    post_id: str
    platform: str
    account_id: str
    timestamp: datetime
    text: str | None = None
    url: str | None = None
    media_hash: str | None = None
    media_reference: str | None = None

    def to_dict(self) -> dict:
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "account_id": self.account_id,
            "timestamp": self.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "text": self.text,
            "url": self.url,
            "media_hash": self.media_hash,
            "media_reference": self.media_reference,
        }


@dataclass
class ImportResult:
    posts: list[Post] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    total_records: int = 0

    def summary(self) -> dict:
        platforms: dict[str, int] = {}
        for post in self.posts:
            platforms[post.platform] = platforms.get(post.platform, 0) + 1
        return {
            "total_records": self.total_records,
            "accepted": len(self.posts),
            "rejected": len(self.errors),
            "errors": self.errors,
            "platforms": dict(sorted(platforms.items())),
        }


def _clean_identifier(record: dict, name: str) -> str:
    value = record.get(name)
    if value is None or value == "":
        raise RecordError(f"Missing required field: {name}")
    # JSON exports often store IDs as numbers. A bool is an int in Python.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise RecordError(f"Field {name} must be text")
    cleaned = str(value).strip()
    if not cleaned:
        raise RecordError(f"Missing required field: {name}")
    return cleaned


def _clean_optional(record: dict, name: str) -> str | None:
    value = record.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecordError(f"Field {name} must be text")
    return value.strip() or None


def _parse_timestamp(value: str) -> datetime:
    # Timestamps from different platforms are compared with each other, so a
    # missing timezone can't be guessed without risking a false signal.
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise RecordError(f'Invalid timestamp: "{value}"') from None
    if parsed.tzinfo is None:
        raise RecordError(f'Timestamp has no timezone: "{value}"')
    try:
        return parsed.astimezone(timezone.utc)
    except OverflowError:
        raise RecordError(f'Invalid timestamp: "{value}"') from None


def normalise_record(record: dict) -> Post:
    identifiers = {name: _clean_identifier(record, name) for name in REQUIRED_FIELDS}
    media_hash = _clean_optional(record, "media_hash")
    return Post(
        post_id=identifiers["post_id"],
        # "Platform_A" and "platform_a" must count as one platform.
        platform=identifiers["platform"].lower(),
        account_id=identifiers["account_id"],
        timestamp=_parse_timestamp(identifiers["timestamp"]),
        text=_clean_optional(record, "text"),
        url=_clean_optional(record, "url"),
        media_hash=media_hash.lower() if media_hash else None,
        media_reference=_clean_optional(record, "media_reference"),
    )


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError("The file isn't valid UTF-8 text.") from None


def _csv_records(content: bytes) -> list[tuple[int, dict | str]]:
    """Returns (row number, record or error message). The header is row 1."""
    reader = csv.DictReader(io.StringIO(_decode(content), newline=""))
    try:
        headers = reader.fieldnames
        if not headers:
            raise ImportFileError("The CSV file is empty.")
        reader.fieldnames = [header.strip().lower() for header in headers]
        missing = [name for name in REQUIRED_FIELDS if name not in reader.fieldnames]
        if missing:
            raise ImportFileError(f"The CSV file is missing required columns: {', '.join(missing)}.")
        records: list[tuple[int, dict | str]] = []
        for row in reader:
            if None in row:
                records.append((reader.line_num, "Row has more columns than the header"))
            else:
                records.append((reader.line_num, row))
    except csv.Error as error:
        raise ImportFileError(f"The CSV file couldn't be read: {error}.") from None
    return records


def _json_records(content: bytes) -> list[tuple[int, dict | str]]:
    """Returns (position in the list, starting at 1, record or error message)."""
    try:
        data = json.loads(_decode(content))
    except (json.JSONDecodeError, RecursionError):
        raise ImportFileError("The JSON file couldn't be parsed.") from None
    if isinstance(data, dict):
        data = data.get("posts")
    if not isinstance(data, list):
        raise ImportFileError('The JSON file must be a list of posts or an object with a "posts" list.')
    return [
        (index, item if isinstance(item, dict) else "Record must be a JSON object")
        for index, item in enumerate(data, start=1)
    ]


def import_posts(content: bytes, file_format: str) -> ImportResult:
    """file_format is "csv" or "json"."""
    records = _csv_records(content) if file_format == "csv" else _json_records(content)
    if len(records) > MAX_RECORDS:
        raise ImportFileError(f"The file has {len(records)} records. The limit is {MAX_RECORDS}.")

    result = ImportResult(total_records=len(records))
    seen: set[tuple[str, str]] = set()
    for row, record in records:
        try:
            if isinstance(record, str):
                raise RecordError(record)
            post = normalise_record(record)
            key = (post.platform, post.post_id)
            if key in seen:
                raise RecordError(f"Duplicate post_id on {post.platform}: {post.post_id}")
            seen.add(key)
            result.posts.append(post)
        except RecordError as error:
            result.errors.append({"row": row, "message": str(error)})
    return result
