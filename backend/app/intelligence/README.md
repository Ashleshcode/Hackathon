# Coordination graph

This is an account-similarity graph. It is not a directional propagation graph.

Edges come from an exact `media_hash` already present on an imported record, TF-IDF caption similarity, a shared URL, and close posting times as a supporting signal only. Timing never creates an edge by itself. The engine does not read X repost, quote, or reply relationships, and it does not invent a media hash when the import omitted one.

Explicit X repost, quote, and reply rows are stored in `post_relationships` by `POST /api/campaigns/{campaign_id}/sync/x`. They are not written into `graph_edges`. `GET /api/investigations/{id}/graph` is still the future visualization and is not registered.

`backend/data/synthetic_demo_data.csv` is fictional. Import it only as `synthetic_demo_data`. It is not observed platform activity.

`campaign_store.py` writes campaigns, posts, and graph edges to `backend/data/veritas.db`. They remain after the API process stops. This is not background monitoring.

## Coordination signals

This module imports post records and builds an account graph. Its output shows observed similarity for a person to review. It doesn't determine intent, and there is deliberately no combined coordination score.

## Signals

An edge links two accounts when at least one pair of their posts shares content. Posts from the same account are never compared.

| Signal | Rule |
|---|---|
| `same_media_hash` | The posts have an identical `media_hash`. The hash comes from the imported record; perceptual matching isn't implemented. |
| `similar_caption` | TF-IDF cosine similarity of 0.6 or more, using words and word pairs without English stop words or URLs. Captions need at least 4 content words. |
| `shared_url` | The posts share a URL, from the `url` field or the text, after minor normalisation. |
| `close_posting_time` | Posts that already share content were posted within 10 minutes of each other. |

**Timing alone never creates an edge.** Otherwise, any two posts from the same busy period would be linked.

## Clusters

A cluster is a connected group of 3 or more accounts joined by edges with 2 or more different signals. Weaker links still appear as edges, but they don't form a cluster.

## Checking one post from the browser extension

`POST /api/campaigns/{id}/check-post` compares one page post with a campaign through `build_graph`, so these same rules apply. The imported campaign isn't changed; a new post is saved in a separate copy that the dashboard can open. See `frontend/extension/README.md`.

## Limitations

- The thresholds are hackathon defaults tuned on the synthetic demo dataset. They haven't been validated on real data.
- TF-IDF compares shared words, so paraphrased text can be missed. Its weights also depend on the other posts in the import.
- Sharing the same story or link can be perfectly legitimate, and the graph can't tell the difference.
- Only imported records are considered by this similarity engine. An X sync can add posts to the campaign, but it does not rebuild these edges.
- Campaigns are stored in SQLite. Re-importing a file creates a new campaign instead of updating the old one.
- Files are limited to 10 MB and 2,000 records. Imports producing over 5,000 relationships are refused, because the graph would be too dense to draw.
- Timestamps must include a timezone. A record without one is rejected, because guessing could create false timing signals.

## Settings

Thresholds are in `GraphConfig` in `graph_engine.py`, and the values used are returned in each graph's `algorithm` field.

## Running it

These routes are registered on the single application in `backend/app/main.py`. Start it from the repository root with the existing `.venv`:

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000
```

```bash
.venv/Scripts/python.exe -m pytest backend/tests
```

Do not start a second FastAPI application for the same routes. The report service can read results through `campaign_store.get_campaign(id)` and `campaign_store.get_graph(id)`.
