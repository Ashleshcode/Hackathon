"""SQLite campaign storage. Records stay in backend/data/veritas.db across restarts.

This is not background monitoring. Nothing is collected unless a route saves it.
"""

import uuid

from app.database.repository import get_campaign, get_graph, insert_campaign, list_campaigns


def save_campaign(campaign: dict, graph: dict) -> str:
    campaign_id = f"C{uuid.uuid4().hex[:8]}"
    campaign["campaign_id"] = campaign_id
    graph["campaign_id"] = campaign_id
    insert_campaign(campaign, graph)
    return campaign_id


__all__ = ["get_campaign", "get_graph", "list_campaigns", "save_campaign"]
