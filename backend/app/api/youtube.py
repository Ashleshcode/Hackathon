"""YouTube Data API context for one video the analyst submitted.

The response is listing metadata. It is not a detector result.
"""

from fastapi import APIRouter, HTTPException

from app.youtube.client import YouTubeConnectorError
from app.youtube.context import lookup_context
from app.youtube.ids import InvalidYouTubeTarget

router = APIRouter(tags=["youtube"])


@router.post("/api/youtube/context")
def youtube_context(body: dict) -> dict:
    try:
        return lookup_context(body)
    except InvalidYouTubeTarget as error:
        raise HTTPException(
            status_code=422,
            detail={"field": error.field, "code": "invalid_youtube_target", "message": error.message},
        ) from None
    except YouTubeConnectorError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from None
