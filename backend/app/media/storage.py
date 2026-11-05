"""Store analysis bytes under a server-chosen name."""

import hashlib
from pathlib import Path

from app.database.connection import get_media_directory


def media_path(storage_name: str) -> Path:
    directory = get_media_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / storage_name
    if path.parent != directory:
        raise ValueError("Storage name must be a single file name.")
    return path


def write_bytes(storage_name: str, data: bytes) -> Path:
    path = media_path(storage_name)
    temporary = path.with_name(f"{path.name}.partial")
    temporary.write_bytes(data)
    temporary.replace(path)
    return path


def delete_stored(storage_name: str | None) -> None:
    if not storage_name:
        return
    path = get_media_directory() / storage_name
    if path.is_file() and path.parent == get_media_directory():
        path.unlink()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
