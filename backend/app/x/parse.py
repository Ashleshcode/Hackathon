"""Turn one recent-search payload into posts, accounts, media, and references."""

from __future__ import annotations

RELATIONSHIP_TYPES = {
    "retweeted": "reposted",
    "quoted": "quoted",
    "replied_to": "replied_to",
}


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _metrics(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    kept = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        kept[str(key)] = item
    return kept or None


def _account(user: dict) -> dict | None:
    account_id = _text(user.get("id"))
    if account_id is None:
        return None
    account = {
        "account_id": account_id,
        "username": _text(user.get("username")),
        "display_name": _text(user.get("name")),
        "verified": user.get("verified") if isinstance(user.get("verified"), bool) else None,
        "verified_type": _text(user.get("verified_type")),
    }
    return account


def _media(item: dict) -> dict | None:
    media_key = _text(item.get("media_key"))
    if media_key is None:
        return None
    variants = item.get("variants") if isinstance(item.get("variants"), list) else None
    return {
        "media_key": media_key,
        "media_type": _text(item.get("type")),
        "url": _text(item.get("url")),
        "preview_image_url": _text(item.get("preview_image_url")),
        "duration_ms": _optional_int(item.get("duration_ms")),
        "width": _optional_int(item.get("width")),
        "height": _optional_int(item.get("height")),
        "alt_text": _text(item.get("alt_text")),
        "variants": variants,
    }


def _references(tweet: dict) -> list[dict]:
    raw = tweet.get("referenced_tweets")
    if not isinstance(raw, list):
        return []
    found = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        relationship = RELATIONSHIP_TYPES.get(str(item.get("type") or ""))
        target = _text(item.get("id"))
        if relationship is None or target is None:
            continue
        found.append({"type": relationship, "source_post_id": target})
    return found


def _post(tweet: dict, origin: str) -> dict | None:
    post_id = _text(tweet.get("id"))
    if post_id is None:
        return None
    attachments = tweet.get("attachments") if isinstance(tweet.get("attachments"), dict) else {}
    media_keys = []
    for key in attachments.get("media_keys") or []:
        cleaned = _text(key)
        if cleaned and cleaned not in media_keys:
            media_keys.append(cleaned)
    return {
        "post_id": post_id,
        "text": tweet.get("text") if isinstance(tweet.get("text"), str) else None,
        "author_id": _text(tweet.get("author_id")),
        "created_at": _text(tweet.get("created_at")),
        "conversation_id": _text(tweet.get("conversation_id")),
        "public_metrics": _metrics(tweet.get("public_metrics")),
        "media_keys": media_keys,
        "references": _references(tweet),
        "origin": origin,
    }


def parse_search_payload(payload: dict) -> dict:
    includes = payload.get("includes") if isinstance(payload.get("includes"), dict) else {}
    accounts = []
    seen_accounts = set()
    for user in includes.get("users") or []:
        if not isinstance(user, dict):
            continue
        account = _account(user)
        if account and account["account_id"] not in seen_accounts:
            accounts.append(account)
            seen_accounts.add(account["account_id"])

    media = []
    seen_media = set()
    for item in includes.get("media") or []:
        if not isinstance(item, dict):
            continue
        parsed = _media(item)
        if parsed and parsed["media_key"] not in seen_media:
            media.append(parsed)
            seen_media.add(parsed["media_key"])

    posts = []
    for tweet in payload.get("data") or []:
        if isinstance(tweet, dict):
            parsed = _post(tweet, "recent_search")
            if parsed:
                posts.append(parsed)

    included_posts = []
    search_ids = {post["post_id"] for post in posts}
    for tweet in includes.get("tweets") or []:
        if not isinstance(tweet, dict):
            continue
        parsed = _post(tweet, "recent_search_expansion")
        if parsed and parsed["post_id"] not in search_ids:
            included_posts.append(parsed)

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    next_token = _text(meta.get("next_token"))
    return {
        "posts": posts,
        "included_posts": included_posts,
        "accounts": accounts,
        "media": media,
        "next_token": next_token,
    }
