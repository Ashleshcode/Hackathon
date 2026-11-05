"""SQLite connection for the Veritas API process.

The development database is backend/data/veritas.db. Tests must call
set_database_path with a temporary file before initializing tables.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.database.models import INDEXES_SQL, TABLES_SQL

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = BACKEND_ROOT / "data" / "veritas.db"
DEFAULT_MEDIA_DIRECTORY = BACKEND_ROOT / "data" / "media"

_database_path = DEFAULT_DATABASE_PATH
_media_directory = DEFAULT_MEDIA_DIRECTORY


def get_database_path() -> Path:
    return _database_path


def set_database_path(path: Path) -> None:
    global _database_path
    _database_path = Path(path)


def get_media_directory() -> Path:
    return _media_directory


def set_media_directory(path: Path) -> None:
    global _media_directory
    _media_directory = Path(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def connect(path: Path | None = None) -> sqlite3.Connection:
    database = Path(path) if path is not None else get_database_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def session(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _migrate(connection: sqlite3.Connection) -> None:
    """Add analysis columns to a database created by the first persistence pass."""
    if "media_assets" in {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }:
        columns = _columns(connection, "media_assets")
        if "sha256" not in columns:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                CREATE TABLE media_assets_new (
                    id INTEGER PRIMARY KEY,
                    asset_id TEXT UNIQUE,
                    campaign_id TEXT REFERENCES campaigns(campaign_id),
                    post_row_id INTEGER REFERENCES posts(id),
                    media_type TEXT,
                    storage_name TEXT,
                    byte_size INTEGER,
                    sha256 TEXT,
                    media_hash TEXT,
                    media_reference TEXT,
                    created_at TEXT,
                    UNIQUE (post_row_id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO media_assets_new (id, campaign_id, post_row_id, media_hash, media_reference)
                SELECT id, campaign_id, post_row_id, media_hash, media_reference FROM media_assets
                """
            )
            connection.execute("DROP TABLE media_assets")
            connection.execute("ALTER TABLE media_assets_new RENAME TO media_assets")
            connection.execute("PRAGMA foreign_keys = ON")
    if "x_media" in {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    } and "storage_name" not in _columns(connection, "x_media"):
        connection.execute("ALTER TABLE x_media ADD COLUMN storage_name TEXT")
    if "analysis_jobs" in {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    } and "completed_at" not in _columns(connection, "analysis_jobs"):
        connection.execute("ALTER TABLE analysis_jobs ADD COLUMN completed_at TEXT")


def initialize_database(path: Path | None = None) -> Path:
    """Create tables if they are missing. Does not load the detector."""
    database = Path(path) if path is not None else get_database_path()
    connection = connect(database)
    try:
        connection.executescript(TABLES_SQL)
        _migrate(connection)
        connection.executescript(INDEXES_SQL)
        connection.commit()
    finally:
        connection.close()
    return database
