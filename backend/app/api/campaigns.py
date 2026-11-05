"""Campaign routes. Member 1 registers `router` in main.py."""

import sqlite3
from pathlib import PurePath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.database.repository import get_x_campaign_view
from app.intelligence import campaign_store
from app.intelligence.graph_engine import ALGORITHM_NAME, GraphTooLargeError, account_node_id, build_graph
from app.intelligence.post_check import check_post
from app.intelligence.post_ingestion import SOURCE_TYPES, ImportFileError, import_posts
from app.intelligence.similarity import normalise_url
from app.x.client import XConnectorError
from app.x.env import bearer_token
from app.x.sync import SyncRejected, sync_campaign

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _detect_format(file: UploadFile) -> str:
    extension = PurePath(file.filename or "").suffix.lower()
    if extension in (".csv", ".json"):
        return extension[1:]
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type == "text/csv":
        return "csv"
    if content_type == "application/json":
        return "json"
    raise HTTPException(status_code=415, detail="Upload a .csv or .json file.")


# A plain def, so FastAPI runs parsing and graph building on a worker thread.
@router.post("/import")
def import_campaign(file: UploadFile = File(...), source_type: str = Form("uploaded_dataset")) -> dict:
    if source_type not in SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"source_type must be one of: {', '.join(SOURCE_TYPES)}.")
    file_format = _detect_format(file)

    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than the 10 MB limit.")

    try:
        result = import_posts(content, file_format)
    except ImportFileError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

    try:
        graph = build_graph(result.posts)
    except GraphTooLargeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None

    import_summary = result.summary()
    graph["provenance"] = source_type
    graph["import_summary"] = import_summary
    campaign = {
        "status": "completed" if result.posts else "no_valid_records",
        "provenance": source_type,
        "source_file": file.filename,
        "import_summary": import_summary,
        "posts": [post.to_dict() for post in result.posts],
    }
    campaign_store.save_campaign(campaign, graph)
    return campaign


@router.get("")
def list_campaigns() -> list[dict]:
    """Imported campaigns a post can be compared against, newest first."""
    imported = [c for c in campaign_store.list_campaigns() if not c.get("parent_campaign_id")]
    return [
        {
            "campaign_id": campaign["campaign_id"],
            "source_file": campaign.get("source_file"),
            "provenance": campaign["provenance"],
            "post_count": len(campaign["posts"]),
        }
        for campaign in reversed(imported)
    ]


class PagePost(BaseModel):
    """One post read from the current page by the browser extension."""

    url: str = Field(max_length=2048)
    platform: str = Field(min_length=1, max_length=64)
    post_text: str | None = Field(default=None, max_length=5000)
    account: str | None = Field(default=None, max_length=256)
    timestamp: str | None = Field(default=None, max_length=64)
    media_hash: str | None = Field(default=None, max_length=256)

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str) -> str:
        if not normalise_url(value):
            raise ValueError("url must be an http or https address")
        return value


@router.post("/{campaign_id}/check-post")
def check_campaign_post(campaign_id: str, page: PagePost) -> dict:
    """Compares a page post with a campaign. The campaign itself isn't changed.

    A new post is saved in a separate copy, so the dashboard can show it in the
    graph. The response's campaign_id is the one to open.
    """
    campaign = campaign_store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} was not found.")
    if campaign.get("parent_campaign_id"):
        raise HTTPException(status_code=409, detail="Compare against an imported campaign, not a checked copy.")

    try:
        result = check_post(campaign, page.model_dump())
        open_campaign_id = campaign_id
        if not result["post_in_dataset"]:
            graph = build_graph([*result["existing_posts"], result["subject"]])
            checked_node = account_node_id(result["subject"])
            for node in graph["nodes"]:
                node["is_checked_post"] = node["id"] == checked_node
            graph["provenance"] = campaign["provenance"]
            graph["import_summary"] = campaign["import_summary"]
            open_campaign_id = campaign_store.save_campaign(
                {
                    **campaign,
                    "parent_campaign_id": campaign_id,
                    "extension_post": {"post_id": result["post"]["post_id"], "url": page.url},
                    "posts": [*campaign["posts"], result["post"]],
                },
                graph,
            )
    except GraphTooLargeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None

    return {
        "status": "completed",
        "campaign_id": open_campaign_id,
        "post_in_dataset": result["post_in_dataset"],
        "timestamp_known": result["timestamp_known"],
        "coordination": result["coordination"],
        "dataset": {
            "campaign_id": campaign_id,
            "source_file": campaign.get("source_file"),
            "provenance": campaign["provenance"],
            "post_count": len(campaign["posts"]),
        },
        "algorithm": ALGORITHM_NAME,
        "limitations": result["limitations"],
    }


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str) -> dict:
    campaign = campaign_store.get_campaign(campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} was not found.")
    return campaign


@router.get("/{campaign_id}/graph")
def get_campaign_graph(campaign_id: str) -> dict:
    graph = campaign_store.get_graph(campaign_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} was not found.")
    return graph


class XSyncRequest(BaseModel):
    query: str | None = None
    max_results: int | None = Field(default=None, ge=10, le=100)
    max_pages: int | None = Field(default=None, ge=1, le=10)
    max_posts: int | None = Field(default=None, ge=1, le=500)
    start_time: str | None = None


def _x_http_error(status_code: int, code: str, message: str, retry_after: str | None = None) -> HTTPException:
    detail = {"code": code, "message": message, "complete": False}
    if retry_after:
        detail["retry_after"] = retry_after
    return HTTPException(status_code=status_code, detail=detail)


@router.post("/{campaign_id}/sync/x")
def sync_campaign_from_x(campaign_id: str, body: XSyncRequest | None = None) -> dict:
    """Fetch recent public X posts for one campaign. This does not run on a schedule."""
    if not bearer_token():
        raise _x_http_error(
            503,
            "x_connector_not_configured",
            "X ingestion is not configured. Set X_BEARER_TOKEN on the backend.",
        )
    request = body or XSyncRequest()
    try:
        return sync_campaign(
            campaign_id,
            query=request.query,
            page_size=request.max_results,
            max_pages=request.max_pages,
            max_posts=request.max_posts,
            start_time=request.start_time,
        )
    except SyncRejected as error:
        raise _x_http_error(error.status_code, error.code, error.message) from None
    except XConnectorError as error:
        raise _x_http_error(error.status_code, error.code, error.message, error.retry_after) from None
    except sqlite3.Error:
        try:
            from app.database.repository import record_x_sync_failure

            record_x_sync_failure(campaign_id, "database_error", "The X sync could not be saved.")
        except sqlite3.Error:
            pass
        raise HTTPException(status_code=500, detail="The X sync could not be saved.") from None


@router.get("/{campaign_id}/x")
def get_campaign_x_records(campaign_id: str) -> dict:
    view = get_x_campaign_view(campaign_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} was not found.")
    return view
