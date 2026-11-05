"""Compare one post from the browser extension against an imported campaign.

All relationship logic comes from graph_engine.build_graph, so the same signals,
thresholds and evidence apply. This module adds no scoring of its own.
"""

import hashlib

from .graph_engine import GraphConfig, account_node_id, build_graph
from .post_ingestion import Post, RecordError, normalise_record
from .similarity import normalise_url

# build_graph needs a timestamp on every post. A post with no known time gets
# this placeholder for comparison only, so it can't produce a timing signal. It
# is never shown: the stored post has a null timestamp.
_NO_TIME_PLACEHOLDER = "1970-01-01T00:00:00Z"

LIMITATIONS = [
    "Compared only against the selected campaign. Posts outside it were not considered.",
    "Signals show observed similarity. They don't establish intent or prove coordination.",
    "The page post has no media hash, so identical media can't be matched yet.",
]


def _build_page_post(page: dict) -> tuple[Post, bool]:
    """Returns the normalised post, and whether its timestamp is known."""
    url_hash = hashlib.sha256(page["url"].encode()).hexdigest()[:12]
    record = {
        "post_id": f"page_{url_hash}",
        "platform": page["platform"],
        # A missing name must not merge unrelated pages into one account.
        "account_id": page.get("account") or f"unknown_account_{url_hash}",
        "timestamp": page.get("timestamp") or _NO_TIME_PLACEHOLDER,
        "text": page.get("post_text"),
        "url": page["url"],
        "media_hash": page.get("media_hash"),
    }
    try:
        return normalise_record(record), bool(page.get("timestamp"))
    except RecordError:
        # A date we can't place exactly (for example, no timezone) counts as unknown.
        return normalise_record({**record, "timestamp": _NO_TIME_PLACEHOLDER}), False


def _find_same_post(posts: list[Post], page_url: str) -> Post | None:
    key = normalise_url(page_url)
    if not key:
        return None
    return next((post for post in posts if post.url and normalise_url(post.url) == key), None)


def _signals_for(subject: Post, others: list[Post], config: GraphConfig) -> list[dict]:
    """Signals between this post and other accounts' posts, using the engine's own evidence."""
    # The account's other posts are left out, so everything here is about this post.
    subject_node = account_node_id(subject)
    graph = build_graph([subject, *[post for post in others if account_node_id(post) != subject_node]], config)
    labels = {node["id"]: node["label"] for node in graph["nodes"]}

    signals = []
    for edge in graph["edges"]:
        if subject_node not in (edge["source"], edge["target"]):
            continue
        other_node = edge["target"] if edge["source"] == subject_node else edge["source"]
        for signal in edge["signals"]:
            signals.append(
                {
                    "type": signal["type"],
                    "evidence": f"With {labels[other_node]}: {signal['evidence']}",
                    "post_ids": signal["post_ids"],
                    "related_account": labels[other_node],
                }
            )
    return signals


def check_post(campaign: dict, page: dict, config: GraphConfig | None = None) -> dict:
    """Returns the comparison result. Raises GraphTooLargeError if the graph is too dense."""
    config = config or GraphConfig()
    posts = [normalise_record(post) for post in campaign["posts"]]

    existing = _find_same_post(posts, page["url"])
    timestamp_known = True
    if existing:
        subject = existing
    else:
        subject, timestamp_known = _build_page_post(page)

    signals = _signals_for(subject, [post for post in posts if post is not subject], config)
    related_posts = {post_id for signal in signals for post_id in signal["post_ids"]} - {subject.post_id}

    limitations = list(LIMITATIONS)
    if not timestamp_known:
        limitations.append("The page post has no usable timestamp, so posting times couldn't be compared.")

    post = subject.to_dict()
    if not timestamp_known:
        post["timestamp"] = None

    return {
        "subject": subject,
        "post": post,
        "post_in_dataset": existing is not None,
        "timestamp_known": timestamp_known,
        "coordination": {
            "status": "signals_found" if signals else "none_found",
            "related_post_count": len(related_posts),
            "signals": signals,
        },
        "limitations": limitations,
        "existing_posts": posts,
    }
