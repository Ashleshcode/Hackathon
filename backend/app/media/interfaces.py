"""Integration boundary between media jobs and Member 1's code.

Media jobs need three things that Member 1 owns. They are described here as
small interfaces, so this module does not copy the database or the detector:

* ``MediaStore``: looks up a stored ``media_id`` and provides a local file.
* ``FrameDetector``: runs the shared production detector on one image.
* ``JobRepository``: persists jobs. An in-memory default exists until SQLite
  storage is ready.

Member 1 connects them once at startup, in ``app/main.py``::

    from app.api.media_jobs import configure_media_jobs, dev_router, router

    configure_media_jobs(media_store=..., detector=..., job_repository=...)
    app.include_router(router)
    if os.environ.get("VERITAS_ENABLE_DEV_ROUTES") == "1":
        app.include_router(dev_router)

All three are called from worker threads, not the thread that created them. A
SQLite implementation should open a connection per call. Detector calls are
made one at a time, but the store and repository may be called concurrently.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

# Contract values, kept in one place so they cannot drift apart.
SCORE_SEMANTICS = "raw_model_score_not_calibrated_probability"
ALLOWED_PREDICTIONS = {"real", "fake", "uncertain", "unsupported"}


class MediaFetchError(Exception):
    """A stored media record exists, but its file could not be obtained."""


@dataclass(frozen=True)
class StoredMedia:
    """The fields media jobs need from a stored post's media attachment."""

    media_id: str
    post_id: str | None
    monitor_id: str | None
    media_type: str
    mime_type: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class ModelInfo:
    """Model identity, matching ``result.model`` in the API contract."""

    name: str
    checkpoint_dataset: str
    version: str


@dataclass(frozen=True)
class DetectionResult:
    """What the detector reports for one image or one video frame.

    ``fake_score`` is the raw model score. It is not a calibrated probability,
    and it must be ``None`` when there is no usable score. Use plain Python or
    NumPy numbers: call ``.item()`` on a PyTorch tensor first.
    """

    face_count: int
    prediction: str
    fake_score: float | None
    warnings: tuple[str, ...] = field(default_factory=tuple)


class MediaStore(Protocol):
    """Implemented by Member 1's storage layer."""

    def get_media(self, media_id: str) -> StoredMedia | None:
        """Return the stored media record, or ``None`` if it does not exist."""
        ...

    def get_local_path(self, media: StoredMedia) -> Path:
        """Return a readable local file for this media.

        The store owns the file, including any download from the stored
        ``source_url``. Media jobs never fetch URLs and never delete this file.
        Raise ``MediaFetchError`` if the file cannot be obtained.
        """
        ...


class FrameDetector(Protocol):
    """Implemented by Member 1's shared detector, loaded once per process."""

    model_info: ModelInfo

    def analyze_image(self, image: np.ndarray) -> DetectionResult:
        """Analyse one OpenCV image (H x W x 3, BGR, uint8)."""
        ...


class JobRepository(Protocol):
    """Stores jobs. Member 1 may replace the in-memory default with SQLite."""

    def save(self, job: Any) -> None:
        """Insert or replace a ``MediaJob``, using ``job.job_id`` as the key.

        Keep every field, including the ``result`` dict. ``dataclasses.asdict``
        gives a form that can be stored as JSON. A raised error here cannot be
        recorded on the job, so it would stay in its previous status.
        """
        ...

    def get(self, job_id: str) -> Any | None:
        """Return the ``MediaJob``, or ``None`` if it does not exist."""
        ...
