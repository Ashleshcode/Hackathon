"""Campaign sync against official X recent search."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.database.connection import utc_now
from app.database.repository import (
    campaign_exists,
    get_campaign_query,
    persist_x_sync,
    record_x_sync_failure,
    save_campaign_query,
)
from app.x.client import SEARCH_URL, XClient, XConnectorError, build_client
from app.x.env import sync_limits
from app.x.parse import parse_search_payload

SEARCH_WINDOW = timedelta(days=7)
ABSOLUTE_MAX_PAGES = 10
ABSOLUTE_MAX_POSTS = 500


class SyncRejected(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def normalize_start_time(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise SyncRejected(422, "invalid_start_time", "start_time must be an ISO-8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise SyncRejected(422, "invalid_start_time", "start_time must include a timezone.")
    earliest = datetime.now(timezone.utc) - SEARCH_WINDOW - timedelta(minutes=5)
    if parsed < earliest:
        raise SyncRejected(
            422,
            "outside_recent_search_window",
            "Recent search only includes the preceding seven days.",
        )
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_query(query: str) -> str:
    cleaned = " ".join(query.split())
    if not cleaned:
        raise SyncRejected(422, "query_required", "An X recent-search query is required.")
    if len(cleaned) > 512:
        raise SyncRejected(422, "query_too_long", "The X query must be 512 characters or fewer.")
    return cleaned


def _public_media(post_id: str, media_key: str, media: dict | None) -> dict:
    variants = None if media is None else media.get("variants")
    return {
        "post_id": post_id,
        "media_key": media_key,
        "type": None if media is None else media.get("media_type"),
        "variant_access": "present" if variants else "absent",
        "analysed": False,
    }


def fetch_recent_search(
    client: XClient,
    query: str,
    *,
    page_size: int,
    max_pages: int,
    max_posts: int,
    start_time: str | None,
) -> tuple[dict, dict]:
    posts = []
    included = []
    accounts = []
    media = []
    seen_posts = set()
    seen_included = set()
    pages = 0
    next_token = None
    more_pages = False
    stopped_by_limit = False
    while pages < max_pages and len(posts) < max_posts:
        payload = client.search_page(
            query,
            page_size=page_size,
            next_token=next_token,
            start_time=start_time,
        )
        pages += 1
        parsed = parse_search_payload(payload)
        room = max_posts - len(posts)
        page_posts = parsed["posts"]
        if len(page_posts) > room:
            page_posts = page_posts[:room]
            stopped_by_limit = True
            more_pages = True
        for post in page_posts:
            if post["post_id"] not in seen_posts:
                posts.append(post)
                seen_posts.add(post["post_id"])
        accepted_ids = {post["post_id"] for post in posts}
        for post in parsed["included_posts"]:
            if post["post_id"] not in seen_included and post["post_id"] not in accepted_ids:
                included.append(post)
                seen_included.add(post["post_id"])
        accounts.extend(parsed["accounts"])
        media.extend(parsed["media"])
        next_token = parsed["next_token"]
        if stopped_by_limit:
            break
        if not next_token:
            more_pages = False
            break
        if pages >= max_pages:
            more_pages = True
            stopped_by_limit = True
            break
        more_pages = False
    return (
        {"posts": posts, "included_posts": included, "accounts": accounts, "media": media},
        {
            "pages_retrieved": pages,
            "more_pages_available": more_pages,
            "stopped_by_limit": stopped_by_limit,
        },
    )


def _bundle(fetched: dict) -> dict:
    media_by_key = {}
    for item in fetched["media"]:
        media_by_key.setdefault(item["media_key"], item)
    relationships = []
    seen = set()
    for post in [*fetched["posts"], *fetched["included_posts"]]:
        for reference in post["references"]:
            key = (reference["source_post_id"], post["post_id"], reference["type"])
            if key in seen:
                continue
            seen.add(key)
            relationships.append(
                {
                    "source_post_id": reference["source_post_id"],
                    "referencing_post_id": post["post_id"],
                    "type": reference["type"],
                }
            )
    return {
        "accounts": fetched["accounts"],
        "posts": [*fetched["posts"], *fetched["included_posts"]],
        "media_by_key": media_by_key,
        "relationships": relationships,
    }


def sync_campaign(
    campaign_id: str,
    *,
    query: str | None,
    page_size: int | None = None,
    max_pages: int | None = None,
    max_posts: int | None = None,
    start_time: str | None = None,
    client: XClient | None = None,
) -> dict:
    if not campaign_exists(campaign_id):
        raise SyncRejected(404, "campaign_not_found", f"Campaign {campaign_id} was not found.")
    limits = sync_limits()
    chosen_pages = limits["max_pages"] if max_pages is None else max_pages
    chosen_posts = limits["max_posts"] if max_posts is None else max_posts
    chosen_page_size = limits["page_size"] if page_size is None else page_size
    if not 1 <= chosen_pages <= ABSOLUTE_MAX_PAGES:
        raise SyncRejected(422, "invalid_max_pages", "max_pages must be from 1 to 10.")
    if not 1 <= chosen_posts <= ABSOLUTE_MAX_POSTS:
        raise SyncRejected(422, "invalid_max_posts", "max_posts must be from 1 to 500.")
    if not 10 <= chosen_page_size <= 100:
        raise SyncRejected(422, "invalid_page_size", "max_results must be from 10 to 100.")
    chosen_page_size = min(chosen_page_size, max(10, chosen_posts))
    start = normalize_start_time(start_time)
    if query is None:
        stored = get_campaign_query(campaign_id)
        if not stored:
            raise SyncRejected(422, "query_required", "An X recent-search query is required.")
        chosen_query = stored
    else:
        chosen_query = _clean_query(query)
        save_campaign_query(campaign_id, chosen_query)

    owns_client = client is None
    api = client or build_client()
    try:
        fetched, page_info = fetch_recent_search(
            api,
            chosen_query,
            page_size=chosen_page_size,
            max_pages=chosen_pages,
            max_posts=chosen_posts,
            start_time=start,
        )
    except XConnectorError as error:
        record_x_sync_failure(campaign_id, error.code, error.message)
        raise
    finally:
        if owns_client:
            api.close()

    status = "partial" if page_info["stopped_by_limit"] else "completed"
    public_media = []
    for post in [*fetched["posts"], *fetched["included_posts"]]:
        for media_key in post["media_keys"]:
            public_media.append(_public_media(post["post_id"], media_key, None))
    media_by_key = {item["media_key"]: item for item in fetched["media"]}
    for item in public_media:
        item.update(_public_media(item["post_id"], item["media_key"], media_by_key.get(item["media_key"])))

    bundle = _bundle(fetched)
    summary = {
        "campaign_id": campaign_id,
        "status": status,
        "complete": status == "completed",
        "query": chosen_query,
        "search_window": "preceding_seven_days",
        "source": {
            "platform": "x",
            "api": "x_api_v2",
            "endpoint": SEARCH_URL,
        },
        "posts_fetched": len(fetched["posts"]),
        "pages_retrieved": page_info["pages_retrieved"],
        "more_pages_available": page_info["more_pages_available"],
        "stopped_by_limit": page_info["stopped_by_limit"],
        "media": public_media,
        "relationships": bundle["relationships"],
        "analysis": "not_performed",
        "coordination_graph": "unchanged",
        "synced_at": utc_now(),
    }
    return persist_x_sync(campaign_id, bundle, summary)
