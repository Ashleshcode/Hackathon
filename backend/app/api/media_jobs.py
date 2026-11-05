"""Media-job routes from sections 4 and 7 of ``docs/API_CONTRACTS.md``.

``router`` is the product path, which accepts only a stored ``media_id``.
``dev_router`` is the developer upload. The extension must never call it, and
it answers 404 unless ``VERITAS_ENABLE_DEV_ROUTES=1`` is set.
"""

import os
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field

from app.media.interfaces import FrameDetector, JobRepository, MediaStore
from app.media.media_jobs import (
    InMemoryJobRepository,
    MediaJobService,
    MediaNotFoundError,
    MediaStoreUnavailableError,
)

MAX_IMAGE_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = 200 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024

# Extensions accepted per format on the developer upload route.
IMAGE_EXTENSIONS = {
    "jpeg": {".jpg", ".jpeg"},
    "png": {".png"},
    "webp": {".webp"},
}
VIDEO_EXTENSIONS = {"mp4": {".mp4"}}

router = APIRouter(prefix="/api/v1/media-jobs", tags=["media-jobs"])
dev_router = APIRouter(prefix="/api/v1/dev/media-jobs", tags=["developer-only"])

_service = MediaJobService(InMemoryJobRepository())


class MediaJobCreateRequest(BaseModel):
    """Only a stored media ID is accepted, so a URL or extra field is rejected."""

    model_config = ConfigDict(extra="forbid")

    media_id: str = Field(pattern=r"^med_[A-Za-z0-9_-]+$", max_length=128)


def configure_media_jobs(
    media_store: MediaStore | None = None,
    detector: FrameDetector | None = None,
    job_repository: JobRepository | None = None,
) -> None:
    """Connect Member 1's storage and detector. Call once at startup.

    Without a ``job_repository``, jobs are kept in memory and lost on restart.
    A test-only mock detector is rejected here. There is no option to allow it.
    """
    global _service
    if job_repository is None:
        job_repository = InMemoryJobRepository()
    _service = MediaJobService(job_repository, media_store, detector)


def get_media_job_service() -> MediaJobService:
    return _service


def require_dev_routes_enabled() -> None:
    if os.environ.get("VERITAS_ENABLE_DEV_ROUTES") != "1":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not Found")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_media_job(
    request: MediaJobCreateRequest,
    background_tasks: BackgroundTasks,
    service: MediaJobService = Depends(get_media_job_service),
) -> dict:
    try:
        job = service.create_job(request.media_id)
    except MediaNotFoundError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"media_id: no stored media with ID {request.media_id}",
        ) from None
    except MediaStoreUnavailableError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None

    background_tasks.add_task(service.process_job, job.job_id)
    return job.to_response()


@router.get("/{job_id}")
def get_media_job(
    job_id: str,
    service: MediaJobService = Depends(get_media_job_service),
) -> dict:
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"job_id: no job with ID {job_id}"
        )
    return job.to_response()


def _detect_upload_format(header: bytes) -> str | None:
    """Identify a file from its leading bytes, not the client's claims."""
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    if header[4:8] == b"ftyp":
        return "mp4"
    return None


def _save_validated_upload(file: UploadFile, media_type: str) -> Path:
    """Validate an upload and copy it to a temporary file.

    The temporary name is random, so the client's filename never reaches the
    file system. The caller owns the returned file and must delete it.
    """
    allowed = IMAGE_EXTENSIONS if media_type == "image" else VIDEO_EXTENSIONS
    max_bytes = (
        MAX_IMAGE_UPLOAD_BYTES if media_type == "image" else MAX_VIDEO_UPLOAD_BYTES
    )

    extension = Path(file.filename or "").suffix.lower()
    if not any(extension in extensions for extensions in allowed.values()):
        raise HTTPException(
            415,
            detail=f"file: extension '{extension}' is not allowed for {media_type}",
        )

    header = file.file.read(12)
    if not header:
        raise HTTPException(
            422, detail="file: uploaded file is empty"
        )

    detected = _detect_upload_format(header)
    if detected is None or extension not in allowed.get(detected, set()):
        raise HTTPException(
            415,
            detail=f"file: content does not match a {extension} {media_type} file",
        )

    # FastAPI has already spooled the request by this point, so this limit stops
    # oversized files from being kept and analysed, not from being received.
    file.file.seek(0)
    descriptor, temp_name = tempfile.mkstemp(prefix="veritas_dev_", suffix=extension)
    temp_path = Path(temp_name)
    try:
        written = 0
        with os.fdopen(descriptor, "wb") as temp_file:
            while chunk := file.file.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        413,
                        detail=(
                            f"file: {media_type} uploads must not exceed "
                            f"{max_bytes} bytes"
                        ),
                    )
                temp_file.write(chunk)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def _process_upload_then_delete(
    service: MediaJobService, job_id: str, temp_path: Path
) -> None:
    try:
        service.process_job(job_id, local_path=temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


@dev_router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_dev_routes_enabled)],
)
def upload_dev_media_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    media_type: Literal["image", "video"] = Form(...),
    provenance_label: Literal["synthetic_demo", "curated_public_sample"] = Form(...),
    service: MediaJobService = Depends(get_media_job_service),
) -> dict:
    temp_path = _save_validated_upload(file, media_type)
    try:
        job = service.create_dev_upload_job(media_type, provenance_label)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(
        _process_upload_then_delete, service, job.job_id, temp_path
    )
    return job.to_response()


def create_standalone_app() -> FastAPI:
    """Run only these routes until Member 1's ``app/main.py`` exists.

    Storage and the detector are not connected here, so the product route
    answers 503 and uploaded jobs fail with an explanation. Use with::

        uvicorn app.api.media_jobs:create_standalone_app --factory
    """
    app = FastAPI(title="Veritas AI media jobs (standalone)")
    app.include_router(router)
    app.include_router(dev_router)
    return app
