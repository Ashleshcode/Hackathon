"""Read and write campaigns, posts, graph edges, and analysis jobs."""

import json
import sqlite3
from typing import Any

from app.database.connection import session, utc_now


class DuplicateCampaignError(ValueError):
    """A campaign id is already stored. The existing row is left unchanged."""


class DuplicateAnalysisJobError(ValueError):
    """An analysis job id is already stored."""


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"))


def _loads(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def insert_campaign(campaign: dict, graph: dict) -> None:
    campaign_id = campaign["campaign_id"]
    with session() as connection:
        try:
            connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, status, provenance, source_file, parent_campaign_id,
                    extension_post_json, import_summary_json, algorithm_json,
                    limitations_json, clusters_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    campaign["status"],
                    campaign["provenance"],
                    campaign.get("source_file"),
                    campaign.get("parent_campaign_id"),
                    _dumps(campaign.get("extension_post")),
                    _dumps(campaign["import_summary"]),
                    _dumps(graph.get("algorithm")),
                    _dumps(graph.get("limitations", [])),
                    _dumps(graph.get("clusters", [])),
                    utc_now(),
                ),
            )
        except sqlite3.IntegrityError as error:
            if "campaigns.campaign_id" not in str(error):
                raise
            raise DuplicateCampaignError(f"Campaign {campaign_id} already exists.") from error

        for position, post in enumerate(campaign["posts"]):
            cursor = connection.execute(
                """
                INSERT INTO posts (
                    campaign_id, post_id, platform, account_id, timestamp, text, url,
                    media_hash, media_reference, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    post["post_id"],
                    post["platform"],
                    post["account_id"],
                    post.get("timestamp"),
                    post.get("text"),
                    post.get("url"),
                    post.get("media_hash"),
                    post.get("media_reference"),
                    position,
                ),
            )
            if post.get("media_hash") or post.get("media_reference"):
                connection.execute(
                    """
                    INSERT INTO media_assets (campaign_id, post_row_id, media_hash, media_reference)
                    VALUES (?, ?, ?, ?)
                    """,
                    (campaign_id, cursor.lastrowid, post.get("media_hash"), post.get("media_reference")),
                )

        for position, node in enumerate(graph.get("nodes", [])):
            checked = node["is_checked_post"] if "is_checked_post" in node else None
            connection.execute(
                """
                INSERT INTO accounts (
                    campaign_id, node_id, account_id, platform, label, node_type,
                    cluster_id, post_count, is_checked_post, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    node["id"],
                    node["account_id"],
                    node["platform"],
                    node["label"],
                    node.get("type", "account"),
                    node.get("cluster_id"),
                    node["post_count"],
                    None if checked is None else int(bool(checked)),
                    position,
                ),
            )

        for position, edge in enumerate(graph.get("edges", [])):
            connection.execute(
                """
                INSERT INTO graph_edges (campaign_id, edge_id, source_node, target_node, signals_json, position)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign_id,
                    edge["id"],
                    edge["source"],
                    edge["target"],
                    _dumps(edge["signals"]),
                    position,
                ),
            )


def _campaign_from_row(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
    posts = [
        {
            "post_id": post["post_id"],
            "platform": post["platform"],
            "account_id": post["account_id"],
            "timestamp": post["timestamp"],
            "text": post["text"],
            "url": post["url"],
            "media_hash": post["media_hash"],
            "media_reference": post["media_reference"],
        }
        for post in connection.execute(
            "SELECT * FROM posts WHERE campaign_id = ? ORDER BY position",
            (row["campaign_id"],),
        )
    ]
    campaign = {
        "status": row["status"],
        "provenance": row["provenance"],
        "source_file": row["source_file"],
        "import_summary": _loads(row["import_summary_json"]),
        "posts": posts,
        "campaign_id": row["campaign_id"],
    }
    if row["parent_campaign_id"]:
        campaign["parent_campaign_id"] = row["parent_campaign_id"]
    extension_post = _loads(row["extension_post_json"])
    if extension_post is not None:
        campaign["extension_post"] = extension_post
    return campaign


def get_campaign(campaign_id: str) -> dict | None:
    with session() as connection:
        row = connection.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            return None
        return _campaign_from_row(connection, row)


def list_campaigns() -> list[dict]:
    with session() as connection:
        rows = connection.execute("SELECT * FROM campaigns ORDER BY rowid").fetchall()
        return [_campaign_from_row(connection, row) for row in rows]


def get_graph(campaign_id: str) -> dict | None:
    with session() as connection:
        row = connection.execute("SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            return None
        nodes = []
        for node in connection.execute(
            "SELECT * FROM accounts WHERE campaign_id = ? ORDER BY position",
            (campaign_id,),
        ):
            item = {
                "id": node["node_id"],
                "type": node["node_type"],
                "label": node["label"],
                "account_id": node["account_id"],
                "platform": node["platform"],
                "cluster_id": node["cluster_id"],
                "post_count": node["post_count"],
            }
            if node["is_checked_post"] is not None:
                item["is_checked_post"] = bool(node["is_checked_post"])
            nodes.append(item)
        edges = [
            {
                "id": edge["edge_id"],
                "source": edge["source_node"],
                "target": edge["target_node"],
                "signals": _loads(edge["signals_json"]),
            }
            for edge in connection.execute(
                "SELECT * FROM graph_edges WHERE campaign_id = ? ORDER BY position",
                (campaign_id,),
            )
        ]
        graph = {
            "nodes": nodes,
            "edges": edges,
            "clusters": _loads(row["clusters_json"]),
            "algorithm": _loads(row["algorithm_json"]),
            "limitations": _loads(row["limitations_json"]),
            "provenance": row["provenance"],
            "import_summary": _loads(row["import_summary_json"]),
            "campaign_id": campaign_id,
        }
        return graph


def list_graph_edges(campaign_id: str) -> list[dict]:
    graph = get_graph(campaign_id)
    if graph is None:
        return []
    return graph["edges"]


def save_analysis_job(
    *,
    job_id: str,
    status: str,
    campaign_id: str | None = None,
    post_id: str | None = None,
    platform: str | None = None,
    media_asset_id: int | None = None,
    status_reason: str | None = None,
    result: dict | None = None,
) -> str:
    with session() as connection:
        try:
            connection.execute(
                """
                INSERT INTO analysis_jobs (
                    job_id, campaign_id, post_id, platform, media_asset_id,
                    status, status_reason, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    campaign_id,
                    post_id,
                    platform,
                    media_asset_id,
                    status,
                    status_reason,
                    _dumps(result),
                    utc_now(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateAnalysisJobError(f"Analysis job {job_id} already exists.") from error
    return job_id


def persist_analysis(
    *,
    asset_id: str,
    media_type: str,
    storage_name: str | None,
    byte_size: int,
    sha256: str,
    job_id: str,
    status: str,
    status_reason: str | None,
    result: dict | None,
    created_at: str,
    completed_at: str | None,
) -> int:
    """Insert the asset and the job in one transaction."""
    with session() as connection:
        cursor = connection.execute(
            """
            INSERT INTO media_assets (
                asset_id, media_type, storage_name, byte_size, sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (asset_id, media_type, storage_name, byte_size, sha256, created_at),
        )
        asset_row_id = int(cursor.lastrowid)
        try:
            connection.execute(
                """
                INSERT INTO analysis_jobs (
                    job_id, media_asset_id, status, status_reason, result_json,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    asset_row_id,
                    status,
                    status_reason,
                    _dumps(result),
                    created_at,
                    completed_at,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateAnalysisJobError(f"Analysis job {job_id} already exists.") from error
    return asset_row_id


def get_report(report_id: str) -> dict | None:
    with session() as connection:
        row = connection.execute(
            """
            SELECT
                jobs.job_id, jobs.status, jobs.status_reason, jobs.result_json,
                jobs.created_at, jobs.completed_at,
                assets.asset_id, assets.media_type, assets.byte_size, assets.sha256
            FROM analysis_jobs AS jobs
            LEFT JOIN media_assets AS assets ON assets.id = jobs.media_asset_id
            WHERE jobs.job_id = ?
            """,
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "report_id": row["job_id"],
            "job_id": row["job_id"],
            "status": row["status"],
            "status_reason": row["status_reason"],
            "media_type": row["media_type"],
            "media_asset_id": row["asset_id"],
            "byte_size": row["byte_size"],
            "sha256": row["sha256"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
            "result": _loads(row["result_json"]),
        }


def get_analysis_job(job_id: str) -> dict | None:
    with session() as connection:
        row = connection.execute("SELECT * FROM analysis_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return {
            "job_id": row["job_id"],
            "campaign_id": row["campaign_id"],
            "post_id": row["post_id"],
            "platform": row["platform"],
            "media_asset_id": row["media_asset_id"],
            "status": row["status"],
            "status_reason": row["status_reason"],
            "result": _loads(row["result_json"]),
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }


def campaign_exists(campaign_id: str) -> bool:
    with session() as connection:
        row = connection.execute(
            "SELECT 1 FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        return row is not None


def save_campaign_query(campaign_id: str, query: str) -> None:
    with session() as connection:
        connection.execute(
            """
            INSERT INTO campaign_sources (campaign_id, platform, query, updated_at)
            VALUES (?, 'x', ?, ?)
            ON CONFLICT(campaign_id, platform) DO UPDATE SET
                query = excluded.query,
                updated_at = excluded.updated_at
            """,
            (campaign_id, query, utc_now()),
        )


def get_campaign_query(campaign_id: str) -> str | None:
    with session() as connection:
        row = connection.execute(
            "SELECT query FROM campaign_sources WHERE campaign_id = ? AND platform = 'x'",
            (campaign_id,),
        ).fetchone()
        return None if row is None else row["query"]


def _coalesce(new_value, old_value):
    return old_value if new_value is None else new_value


def _upsert_account(connection: sqlite3.Connection, campaign_id: str, account: dict, now: str) -> str:
    row = connection.execute(
        """
        SELECT username, display_name, verified, verified_type
        FROM x_accounts WHERE campaign_id = ? AND account_id = ?
        """,
        (campaign_id, account["account_id"]),
    ).fetchone()
    verified = None if account["verified"] is None else int(account["verified"])
    if row is None:
        connection.execute(
            """
            INSERT INTO x_accounts (
                campaign_id, account_id, username, display_name, verified, verified_type, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                campaign_id,
                account["account_id"],
                account["username"],
                account["display_name"],
                verified,
                account["verified_type"],
                now,
            ),
        )
        return "inserted"
    updated = (
        _coalesce(account["username"], row["username"]),
        _coalesce(account["display_name"], row["display_name"]),
        row["verified"] if verified is None else verified,
        _coalesce(account["verified_type"], row["verified_type"]),
    )
    current = (row["username"], row["display_name"], row["verified"], row["verified_type"])
    if updated == current:
        return "unchanged"
    connection.execute(
        """
        UPDATE x_accounts
        SET username = ?, display_name = ?, verified = ?, verified_type = ?, updated_at = ?
        WHERE campaign_id = ? AND account_id = ?
        """,
        (*updated, now, campaign_id, account["account_id"]),
    )
    return "updated"


def _upsert_post(connection: sqlite3.Connection, campaign_id: str, post: dict, now: str) -> tuple[int, str]:
    row = connection.execute(
        """
        SELECT id FROM posts
        WHERE campaign_id = ? AND platform = 'x' AND post_id = ?
        """,
        (campaign_id, post["post_id"]),
    ).fetchone()
    if row is None:
        position = connection.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM posts WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO posts (
                campaign_id, post_id, platform, account_id, timestamp, text, url,
                media_hash, media_reference, position
            ) VALUES (?, ?, 'x', ?, ?, ?, NULL, NULL, NULL, ?)
            """,
            (
                campaign_id,
                post["post_id"],
                post["author_id"] or "",
                post["created_at"],
                post["text"],
                position,
            ),
        )
        post_row_id = int(cursor.lastrowid)
        state = "inserted"
    else:
        post_row_id = int(row["id"])
        connection.execute(
            """
            UPDATE posts
            SET account_id = COALESCE(NULLIF(?, ''), account_id),
                timestamp = COALESCE(?, timestamp),
                text = COALESCE(?, text)
            WHERE id = ?
            """,
            (post["author_id"] or "", post["created_at"], post["text"], post_row_id),
        )
        state = "known"
    connection.execute(
        """
        INSERT INTO x_post_details (
            post_row_id, conversation_id, public_metrics_json, origin, source_endpoint, ingested_at
        ) VALUES (?, ?, ?, ?, 'GET /2/tweets/search/recent', ?)
        ON CONFLICT(post_row_id) DO UPDATE SET
            conversation_id = COALESCE(excluded.conversation_id, x_post_details.conversation_id),
            public_metrics_json = COALESCE(excluded.public_metrics_json, x_post_details.public_metrics_json),
            ingested_at = excluded.ingested_at
        """,
        (
            post_row_id,
            post["conversation_id"],
            _dumps(post["public_metrics"]),
            post["origin"],
            now,
        ),
    )
    return post_row_id, state


def _record_x_sync(connection: sqlite3.Connection, campaign_id: str, status: str, summary: dict) -> None:
    connection.execute(
        """
        INSERT INTO x_sync_runs (campaign_id, status, summary_json, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (campaign_id, status, _dumps(summary), summary["synced_at"]),
    )


def persist_x_sync(campaign_id: str, bundle: dict, summary: dict) -> dict:
    """Save one fetched sync. The caller has already finished the HTTP calls."""
    now = summary["synced_at"]
    with session() as connection:
        account_counts = {"inserted": 0, "updated": 0}
        seen_accounts = set()
        for account in bundle["accounts"]:
            if account["account_id"] in seen_accounts:
                continue
            seen_accounts.add(account["account_id"])
            result = _upsert_account(connection, campaign_id, account, now)
            if result == "inserted":
                account_counts["inserted"] += 1
            elif result == "updated":
                account_counts["updated"] += 1
        for post in bundle["posts"]:
            author_id = post.get("author_id")
            if author_id and author_id not in seen_accounts:
                result = _upsert_account(
                    connection,
                    campaign_id,
                    {
                        "account_id": author_id,
                        "username": None,
                        "display_name": None,
                        "verified": None,
                        "verified_type": None,
                    },
                    now,
                )
                seen_accounts.add(author_id)
                if result == "inserted":
                    account_counts["inserted"] += 1

        post_rows: dict[str, int] = {}
        inserted = 0
        known = 0
        for post in bundle["posts"]:
            post_row_id, state = _upsert_post(connection, campaign_id, post, now)
            post_rows[post["post_id"]] = post_row_id
            if post["origin"] == "recent_search":
                if state == "inserted":
                    inserted += 1
                else:
                    known += 1
        resolved = sum(1 for post in bundle["posts"] if post["origin"] != "recent_search")

        media_seen = 0
        for post in bundle["posts"]:
            post_row_id = post_rows[post["post_id"]]
            for media_key in post["media_keys"]:
                media = bundle["media_by_key"].get(media_key) or {}
                media_seen += 1
                connection.execute(
                    """
                    INSERT INTO x_media (
                        campaign_id, post_row_id, media_key, media_type, url, preview_image_url,
                        duration_ms, width, height, alt_text, variants_json, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(post_row_id, media_key) DO UPDATE SET
                        media_type = COALESCE(excluded.media_type, x_media.media_type),
                        url = COALESCE(excluded.url, x_media.url),
                        preview_image_url = COALESCE(excluded.preview_image_url, x_media.preview_image_url),
                        duration_ms = COALESCE(excluded.duration_ms, x_media.duration_ms),
                        width = COALESCE(excluded.width, x_media.width),
                        height = COALESCE(excluded.height, x_media.height),
                        alt_text = COALESCE(excluded.alt_text, x_media.alt_text),
                        variants_json = COALESCE(excluded.variants_json, x_media.variants_json),
                        ingested_at = excluded.ingested_at
                    """,
                    (
                        campaign_id,
                        post_row_id,
                        media_key,
                        media.get("media_type"),
                        media.get("url"),
                        media.get("preview_image_url"),
                        media.get("duration_ms"),
                        media.get("width"),
                        media.get("height"),
                        media.get("alt_text"),
                        _dumps(media.get("variants")),
                        now,
                    ),
                )

        relationships_inserted = 0
        relationships_known = 0
        unresolved_ids: set[str] = set()
        for relationship in bundle["relationships"]:
            target_known = relationship["source_post_id"] in post_rows or connection.execute(
                "SELECT 1 FROM posts WHERE campaign_id = ? AND platform = 'x' AND post_id = ?",
                (campaign_id, relationship["source_post_id"]),
            ).fetchone()
            if target_known:
                resolved_flag = 1
            else:
                resolved_flag = 0
                unresolved_ids.add(relationship["source_post_id"])
            existing = connection.execute(
                """
                SELECT id FROM post_relationships
                WHERE campaign_id = ? AND platform = 'x' AND source_post_id = ?
                  AND referencing_post_id = ? AND relationship_type = ?
                """,
                (
                    campaign_id,
                    relationship["source_post_id"],
                    relationship["referencing_post_id"],
                    relationship["type"],
                ),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO post_relationships (
                        campaign_id, platform, source_post_id, referencing_post_id,
                        relationship_type, evidence, observed_at, referenced_resolved
                    ) VALUES (?, 'x', ?, ?, ?, 'x_api_v2_referenced_tweets', ?, ?)
                    """,
                    (
                        campaign_id,
                        relationship["source_post_id"],
                        relationship["referencing_post_id"],
                        relationship["type"],
                        now,
                        resolved_flag,
                    ),
                )
                relationships_inserted += 1
            else:
                connection.execute(
                    """
                    UPDATE post_relationships
                    SET observed_at = ?, referenced_resolved = ?
                    WHERE id = ?
                    """,
                    (now, resolved_flag, existing["id"]),
                )
                relationships_known += 1

        summary = {
            **summary,
            "posts_inserted": inserted,
            "posts_already_known": known,
            "referenced_posts_resolved": resolved,
            "referenced_posts_unresolved": len(unresolved_ids),
            "accounts_inserted": account_counts["inserted"],
            "accounts_updated": account_counts["updated"],
            "media_references": media_seen,
            "relationships_inserted": relationships_inserted,
            "relationships_already_known": relationships_known,
        }
        _record_x_sync(connection, campaign_id, summary["status"], summary)
        return summary


def record_x_sync_failure(campaign_id: str, code: str, message: str) -> None:
    with session() as connection:
        connection.execute(
            """
            INSERT INTO x_sync_runs (campaign_id, status, summary_json, created_at)
            VALUES (?, 'failed', ?, ?)
            """,
            (
                campaign_id,
                _dumps({"code": code, "message": message, "complete": False}),
                utc_now(),
            ),
        )


def latest_successful_sync(campaign_id: str) -> dict | None:
    with session() as connection:
        row = connection.execute(
            """
            SELECT status, summary_json FROM x_sync_runs
            WHERE campaign_id = ? AND status IN ('completed', 'partial')
            ORDER BY id DESC LIMIT 1
            """,
            (campaign_id,),
        ).fetchone()
        if row is None:
            return None
        summary = _loads(row["summary_json"])
        summary["status"] = row["status"]
        return summary


def get_x_campaign_view(campaign_id: str) -> dict | None:
    with session() as connection:
        campaign = connection.execute(
            "SELECT campaign_id FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if campaign is None:
            return None
        query_row = connection.execute(
            "SELECT query FROM campaign_sources WHERE campaign_id = ? AND platform = 'x'",
            (campaign_id,),
        ).fetchone()
        accounts = [
            {
                "account_id": row["account_id"],
                "username": row["username"],
                "name": row["display_name"],
                "verified": None if row["verified"] is None else bool(row["verified"]),
                "verified_type": row["verified_type"],
            }
            for row in connection.execute(
                "SELECT * FROM x_accounts WHERE campaign_id = ? ORDER BY account_id",
                (campaign_id,),
            )
        ]
        account_by_id = {account["account_id"]: account for account in accounts}
        posts = []
        for row in connection.execute(
            """
            SELECT posts.*, details.conversation_id, details.public_metrics_json, details.ingested_at
            FROM posts
            JOIN x_post_details AS details ON details.post_row_id = posts.id
            WHERE posts.campaign_id = ? AND posts.platform = 'x'
            ORDER BY posts.position
            """,
            (campaign_id,),
        ):
            author = account_by_id.get(row["account_id"], {"account_id": row["account_id"]})
            media = []
            for item in connection.execute(
                "SELECT * FROM x_media WHERE post_row_id = ? ORDER BY media_key",
                (row["id"],),
            ):
                variants = _loads(item["variants_json"])
                media.append(
                    {
                        "media_key": item["media_key"],
                        "type": item["media_type"],
                        "duration_ms": item["duration_ms"],
                        "width": item["width"],
                        "height": item["height"],
                        "alt_text": item["alt_text"],
                        "preview_image_url": item["preview_image_url"],
                        "variant_access": "present" if variants else "absent",
                        "analysed": False,
                    }
                )
            relationships = [
                {"type": item["relationship_type"], "target_post_id": item["source_post_id"]}
                for item in connection.execute(
                    """
                    SELECT relationship_type, source_post_id FROM post_relationships
                    WHERE campaign_id = ? AND referencing_post_id = ?
                    ORDER BY relationship_type, source_post_id
                    """,
                    (campaign_id, row["post_id"]),
                )
            ]
            posts.append(
                {
                    "post_id": row["post_id"],
                    "platform": "x",
                    "text": row["text"],
                    "created_at": row["timestamp"],
                    "author": {
                        "author_id": author.get("account_id"),
                        "username": author.get("username"),
                        "name": author.get("name"),
                        "verified": author.get("verified"),
                        "verified_type": author.get("verified_type"),
                    },
                    "conversation_id": row["conversation_id"],
                    "public_metrics": _loads(row["public_metrics_json"]),
                    "relationships": relationships,
                    "media": media,
                    "ingested_at": row["ingested_at"],
                    "provenance": {
                        "api": "x_api_v2",
                        "endpoint": "recent_search",
                        "implementation_status": "not_verified",
                    },
                }
            )
        relationships = [
            {
                "source_post_id": row["source_post_id"],
                "referencing_post_id": row["referencing_post_id"],
                "type": row["relationship_type"],
                "platform": row["platform"],
                "evidence": row["evidence"],
                "observed_at": row["observed_at"],
                "referenced_resolved": bool(row["referenced_resolved"]),
            }
            for row in connection.execute(
                """
                SELECT * FROM post_relationships
                WHERE campaign_id = ? ORDER BY id
                """,
                (campaign_id,),
            )
        ]
        sync_row = connection.execute(
            """
            SELECT status, summary_json FROM x_sync_runs
            WHERE campaign_id = ? AND status IN ('completed', 'partial')
            ORDER BY id DESC LIMIT 1
            """,
            (campaign_id,),
        ).fetchone()
        return {
            "campaign_id": campaign_id,
            "query": None if query_row is None else query_row["query"],
            "search_window": "preceding_seven_days",
            "latest_sync": None if sync_row is None else _loads(sync_row["summary_json"]),
            "accounts": accounts,
            "posts": posts,
            "relationships": relationships,
            "analysis": "not_performed",
            "coordination_graph": "unchanged",
        }


def find_x_media(post_id: str, media_key: str) -> dict | None:
    """Return the newest stored X media row for this post and media key."""
    with session() as connection:
        row = connection.execute(
            """
            SELECT
                media.media_type, media.url, media.preview_image_url, media.variants_json,
                media.storage_name, media.campaign_id, posts.post_id
            FROM x_media AS media
            JOIN posts ON posts.id = media.post_row_id
            WHERE posts.platform = 'x' AND posts.post_id = ? AND media.media_key = ?
            ORDER BY media.id DESC
            LIMIT 1
            """,
            (post_id, media_key),
        ).fetchone()
        if row is None:
            return None
        return {
            "media_type": row["media_type"],
            "url": row["url"],
            "preview_image_url": row["preview_image_url"],
            "variants": _loads(row["variants_json"]),
            "storage_name": row["storage_name"],
            "campaign_id": row["campaign_id"],
            "post_id": row["post_id"],
        }


def save_x_media_job(job: dict) -> dict:
    """Store one X media job. The response body is returned unchanged."""
    with session() as connection:
        connection.execute(
            """
            INSERT INTO analysis_jobs (
                job_id, campaign_id, post_id, platform, status, status_reason,
                result_json, created_at, completed_at
            ) VALUES (?, ?, ?, 'x', ?, ?, ?, ?, ?)
            """,
            (
                job["job_id"],
                job["campaign_id"],
                job["post_id"],
                job["status"],
                job["status_reason"],
                _dumps({"kind": "x_media_job", "job": job["response"]}),
                job["created_at"],
                job["completed_at"],
            ),
        )
    return job["response"]


def get_x_media_job(job_id: str) -> dict | None:
    with session() as connection:
        row = connection.execute(
            "SELECT result_json FROM analysis_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        payload = _loads(row["result_json"])
        if not isinstance(payload, dict) or payload.get("kind") != "x_media_job":
            return None
        return payload.get("job")
