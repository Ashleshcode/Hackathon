"""Point every backend test at a temporary SQLite file."""

import pytest

from app.database.connection import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_MEDIA_DIRECTORY,
    initialize_database,
    set_database_path,
    set_media_directory,
)


@pytest.fixture(autouse=True)
def isolated_x_credentials(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr("app.x.env.load_backend_env", lambda: None)


@pytest.fixture(autouse=True)
def temporary_database(tmp_path):
    path = tmp_path / "test.db"
    set_database_path(path)
    set_media_directory(tmp_path / "media")
    initialize_database()
    assert path != DEFAULT_DATABASE_PATH
    assert tmp_path / "media" != DEFAULT_MEDIA_DIRECTORY
    yield path
