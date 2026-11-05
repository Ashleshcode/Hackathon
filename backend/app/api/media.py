"""Jobs for X media identified by post id and media key.

The client cannot submit a URL. A missing permitted variant or a file that
has not been retrieved stays unavailable, with no detector score.
"""

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.media.x_media_jobs import MediaJobError, create_x_media_job, load_x_media_job

router = APIRouter(tags=["media-jobs"])


class MediaAnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_id: str = Field(min_length=1, max_length=64)
    media_key: str = Field(min_length=1, max_length=128)


def _detector(request: Request):
    return getattr(request.app.state, "detector", None)


@router.post("/api/media/analyze")
def analyze_stored_media(request: Request, body: MediaAnalyzeRequest) -> dict:
    try:
        return create_x_media_job(body.post_id, body.media_key, _detector(request))
    except MediaJobError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from None
    except sqlite3.Error:
        raise HTTPException(status_code=500, detail="The media job could not be saved.") from None


@router.get("/api/media/jobs/{job_id}")
def get_media_job(job_id: str) -> dict:
    job = load_x_media_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Media job {job_id} was not found.")
    return job
