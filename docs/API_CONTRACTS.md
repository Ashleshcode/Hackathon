# Veritas AI — API Contracts

**Status:** Campaign X sync and `POST /api/youtube/context` are implemented and covered by mocked tests. No live X API or YouTube Data API call has been verified from this repository. Sections 2 through 4 and section 6, except `GET /health`, are still not implemented. Do not mark `verified` until a real call from this codebase has been recorded.

`docs/API_CONTRACTS.md` replaces the earlier Bluesky and Mastodon monitor draft. The extension must follow this document.

The extension calls this local backend only. It does not call `api.x.com`, `www.googleapis.com`, `x.com`, or `youtube.com` for data collection. Platform credentials are read from the backend environment:

- `X_BEARER_TOKEN`
- `YOUTUBE_API_KEY`

Those values must never appear in `extension/`, `frontend/`, source committed to Git, or a response body.

## Shared conventions

- JSON uses `application/json`. There is no product upload route.
- IDs returned by X or YouTube are kept as the platform IDs. Internal investigation IDs use a stable prefix.
- Timestamps are ISO-8601 with a timezone.
- `implementation_status` is `not_implemented`, `not_verified`, or `verified`. This repository is still `not_implemented`. Do not mark `verified` until a real call from this codebase has been recorded.
- Allowed detector `prediction` values, once a model exists: `real`, `fake`, `uncertain`, `unsupported`.
- `fake_score` is a raw model score, or `null`. It is not a calibrated probability.
- Do not invent posts, authors, variant URLs, metadata, or scores when an API call fails or a field is absent.
- Do not scrape `x.com`. Do not use an extension content script on X.
- Do not download YouTube audiovisual content, use `tabCapture`, or aggregate YouTube data for videos the user did not submit.
- Validation errors name the field and the reason.

Official upstream shapes this contract maps, without claiming they were called here:

- X API v2 recent search: `GET /2/tweets/search/recent`
- X API v2 post lookup: `GET /2/tweets/:id`
- X expansions used for this contract: `author_id`, `referenced_tweets.id`, `attachments.media_keys`
- X fields used for this contract: tweet `created_at`, `author_id`, `conversation_id`, `text`, `referenced_tweets`, `attachments`; user `username`, `name`; media `type`, `duration_ms`, `width`, `height`, `preview_image_url`, `variants`
- YouTube Data API v3: `videos.list` with `part=snippet,contentDetails` and a single `id`

`referenced_tweets.type` maps as follows: `retweeted` to `reposted`, `quoted` to `quoted`, `replied_to` to `replied_to`.

## 1. Health

### `GET /health`

```json
{
  "status": "ok",
  "service": "veritas-ai-api",
  "version": "0.3.0"
}
```

## 2. X recent search

### `POST /api/x/search`

This standalone route is not implemented. Campaign ingestion uses section 11 instead. The extension does not call either route yet. The request below remains the future standalone shape. The extension would send the analyst's query, not a scraped page.

```json
{
  "query": "synthetic media",
  "max_results": 10,
  "start_time": null
}
```

Rules:

- `query` is required and must be a non-empty string acceptable to X recent search.
- `max_results` defaults to 10. The backend must stay inside the official recent-search bounds, currently 10 through 100.
- `start_time`, when present, is ISO-8601.
- Store this query only because the analyst submitted it. Do not record other browser activity.

```json
{
  "query_id": "xq_0001",
  "implementation_status": "not_implemented",
  "source": {
    "platform": "x",
    "api": "x_api_v2",
    "endpoint": "GET /2/tweets/search/recent"
  },
  "result_count": 0,
  "posts": [],
  "next_token": null,
  "warnings": []
}
```

Each item in `posts` uses the normalized X post in section 7. Until the connector is implemented, return `implementation_status: "not_implemented"`, `result_count: 0`, and `posts: []`. Do not fill the array with fixtures.

## 3. X post lookup

### `GET /api/x/posts/{post_id}`

`post_id` is the official X post ID. The backend calls official post lookup and requests author, timestamp, referenced posts, and media expansions.

```json
{
  "implementation_status": "not_implemented",
  "source": {
    "platform": "x",
    "api": "x_api_v2",
    "endpoint": "GET /2/tweets/:id"
  },
  "post": null,
  "warnings": []
}
```

When implemented, `post` is one normalized X post. A missing post is HTTP 404. An unauthorized or rate-limited API response is returned as an error and does not become a synthetic post.

## 4. Media analysis

### `POST /api/media/analyze`

Creates an analysis job for one piece of X media already returned by section 2 or section 3. The client identifies the media. It does not supply a download URL.

```json
{
  "post_id": "1234567890",
  "media_key": "13_1234567890"
}
```

The backend loads the stored official media object for that pair. It resolves a video variant only from `variants` included in the X API response. It chooses the variant according to a documented rule, starting with the highest `bit_rate` MP4 that the response actually contained. If no permitted variant URL is present, it does not scrape `x.com` and does not guess a URL.

```json
{
  "job_id": "job_0001",
  "post_id": "1234567890",
  "media_key": "13_1234567890",
  "platform": "x",
  "media_type": "video",
  "variant_access": "absent",
  "status": "unavailable",
  "status_reason": "x_api_did_not_provide_a_permitted_variant",
  "result": null,
  "created_at": "2026-11-05T14:30:00+05:30"
}
```

`variant_access` is `present` or `absent`. The variant URL is backend-only and must not be copied into this response or into extension storage.

`status` is `queued`, `running`, `completed`, `failed`, `unsupported`, or `unavailable`.

Reject the request with HTTP 422 when `platform` would be YouTube or the target is a YouTube URL. The error code is `youtube_audiovisual_analysis_not_permitted`. YouTube context never creates this job.

A completed image or video `result` uses:

- `model.name`, `model.checkpoint_dataset`, `model.version`
- `prediction`
- `fake_score`
- `score_semantics`: `raw_model_score_not_calibrated_probability`
- `warnings`

Video results also include `frames_sampled`, `frames_with_faces`, `frame_results` (`timestamp_seconds`, `face_detected`, `prediction`, `fake_score`), `aggregate_prediction`, `aggregate_fake_score`, and `aggregation_method`. Sampling is capped at 20 frames. No usable face produces `unsupported` or `uncertain` and a null score. One suspicious frame does not by itself label the whole video fake.

`POST /api/media/analyze` is implemented for media already stored by the X sync. The body accepts only `post_id` and `media_key`. A video variant counts as present when the stored X payload contains a `video/mp4` variant. The variant URL is not returned and is not fetched. Until a later retrieval step links a local file, the job status is `unavailable` and `result` is null. When a local file is linked, the existing shared detector scores it. Per-frame thresholds are unchanged. New video decisions use `video_aggregation_v2`, described in section 10. A missing face is reported as prediction `unsupported` with a null score and `detector_status` `no_face`. This route is separate from the direct byte routes in section 10.

### `GET /api/media/jobs/{job_id}`

Returns the same job object. This read route supports the side panel. It is not a second way to submit media.

## 5. YouTube context

### `POST /api/youtube/context`

User-initiated context for one video. The extension may send this only after the analyst explicitly requests an investigation of the current watch page.

```json
{
  "video_url": "https://www.youtube.com/watch?v=aaaaaaaaaaa",
  "video_id": null
}
```

Rules:

- Provide `video_url` or `video_id`. A watch URL, short URL, or embed URL may be parsed to one 11-character video ID.
- Reject playlist pages, channel pages, search pages, and the YouTube home page.
- Call `videos.list` for that one ID only.
- Do not call YouTube search across unrelated videos or channels.
- Do not download the stream, storyboard, caption track for analysis, or player JavaScript.
- After metadata returns, the backend may run an official X recent search for the exact watch URL. That search is the external reference lookup. Its X posts use section 7.
- Do not write this request to a browsing-history table. The returned context may be attached to an investigation only when the analyst creates one.

```json
{
  "context_id": "yt_0001",
  "implementation_status": "not_implemented",
  "video_id": "aaaaaaaaaaa",
  "metadata": null,
  "audiovisual_analysis": "not_performed",
  "audiovisual_analysis_reason": "YouTube audiovisual content is not downloaded or analysed.",
  "external_references": {
    "platform": "x",
    "query": "url:\"https://www.youtube.com/watch?v=aaaaaaaaaaa\"",
    "implementation_status": "not_implemented",
    "posts": []
  },
  "warnings": []
}
```

When metadata is available, `metadata` contains only permitted single-video fields: `title`, `channel_title`, `channel_id`, `published_at`, `duration`, and `description`. It is context, not a detector result.

## 6. Investigations

### `POST /api/investigations`

Creates an investigation from records the analyst already requested. This route is the source of the IDs used by the two GET routes below.

```json
{
  "x_query_id": "xq_0001",
  "x_post_ids": ["1234567890"],
  "media_job_ids": ["job_0001"],
  "youtube_context_id": null
}
```

At least one of `x_query_id`, a non-empty `x_post_ids`, or `youtube_context_id` is required. Unknown IDs are a validation error. The response:

```json
{
  "investigation_id": "inv_0001",
  "status": "completed",
  "created_at": "2026-11-05T14:40:00+05:30"
}
```

`status` means the stored record was assembled. It does not mean a platform call was verified.

### `GET /api/investigations/{id}`

```json
{
  "investigation_id": "inv_0001",
  "status": "completed",
  "x_posts": [],
  "media_jobs": [],
  "youtube_context": null,
  "uncertainties": [],
  "recommended_actions": [
    "Review the stored official records before drawing a conclusion."
  ],
  "created_at": "2026-11-05T14:40:00+05:30"
}
```

`x_posts` and `media_jobs` are copies of stored records. `youtube_context`, when present, must still say `audiovisual_analysis: "not_performed"`. `uncertainties` lists missing variants, unimplemented connectors, and media the detector could not score. The report must not add posts or scores that were not stored.

### `GET /api/investigations/{id}/graph`

```json
{
  "investigation_id": "inv_0001",
  "graph_id": "graph_0001",
  "nodes": [],
  "edges": [],
  "methodology": "Official X referenced_tweets become reposted, quoted, and replied_to edges. A YouTube node appears only for the one submitted video and has no detector score. Additional similarity edges must include their signal evidence."
}
```

Node types: `x_account`, `x_post`, `youtube_video`.

Edge types: `published`, `reposted`, `quoted`, `replied_to`, `references_youtube_url`, `similar_text`, `similar_media`.

Official relationship edges can use an empty `signals` array because the X payload is the evidence, and the edge `type` must be one of the official mapped types. Similarity edges must include:

```json
{
  "name": "text_similarity",
  "value": 0.92,
  "method": "tfidf_cosine",
  "threshold": 0.85
}
```

A YouTube node must not contain `prediction` or `fake_score`. An empty graph is valid.

## 7. Normalized X post

```json
{
  "post_id": "1234567890",
  "platform": "x",
  "text": "Text returned by X API v2.",
  "created_at": "2026-11-05T09:00:00Z",
  "author": {
    "author_id": "9876543210",
    "username": "example",
    "name": "Example"
  },
  "conversation_id": "1234567890",
  "relationships": [
    {
      "type": "replied_to",
      "target_post_id": "1234567000"
    }
  ],
  "media": [
    {
      "media_key": "13_1234567890",
      "type": "video",
      "duration_ms": 10000,
      "width": 1280,
      "height": 720,
      "preview_image_url": null,
      "variant_access": "absent"
    }
  ],
  "provenance": {
    "api": "x_api_v2",
    "endpoint": "recent_search",
    "retrieved_at": "2026-11-05T14:30:00+05:30",
    "implementation_status": "not_verified"
  }
}
```

`relationships` contains only referenced tweets present in the official payload. `variant_access` reports whether a permitted variant URL was resolved. The URL itself is omitted.

## 8. Developer testing

`POST /api/v1/dev/media-jobs/upload` from the previous draft is not a product route. Do not add an upload control to the popup or side panel. A local fixture, if a member needs one before API credentials work, must be labelled `synthetic_demo` and must not be returned as an X or YouTube API result.

## 9. Coordination graph already in the API

These routes come from the integrated campaign module. They do not implement section 6. `GET /api/investigations/{id}/graph` is still the future directional graph and is not registered.

| Route | What it does now |
|---|---|
| `POST /api/campaigns/import` | Imports a CSV or JSON file into SQLite and builds the similarity graph. |
| `GET /api/campaigns` | Lists imported campaigns. Checked copies are omitted. |
| `GET /api/campaigns/{campaign_id}` | Returns one stored campaign. |
| `GET /api/campaigns/{campaign_id}/graph` | Returns the account-similarity graph for that campaign. |
| `POST /api/campaigns/{campaign_id}/check-post` | Compares one submitted post with that campaign without changing the original import. |

The graph algorithm is `evidence_signals_v1`. An edge can carry `same_media_hash`, `similar_caption` (TF-IDF cosine at least 0.6), `shared_url`, and `close_posting_time` only when another content signal is already present and the posts are within 10 minutes. The caption threshold here is 0.6. The 0.85 example in section 6 belongs to the future investigation graph, not to this engine.

Hashes are used only when the imported record already has `media_hash`. The service does not compute or invent one. `backend/data/synthetic_demo_data.csv` is fictional and must stay labelled `synthetic_demo_data`.

Campaigns, accounts, posts, media hashes that were already on an imported record, coordination-graph edges, and analysis-job rows are stored in `backend/data/veritas.db`. Importing the same file again creates a new campaign id. Saving the same campaign id twice is rejected, and the original row stays as it was. A missing media hash is stored as null. It is not invented.

Restarting the API does not drop these rows. That is not background monitoring, and it is not the directional propagation graph. Direct byte analysis creates an analysis job through the routes in section 10. A stored job keeps the detector result it received and does not invent a score. Section 11 stores X accounts, posts, media metadata, and explicit relationships without creating an analysis job and without changing `graph_edges`.

Routes the imported UI calls that are not implemented on this app:

- `POST /api/extension/analyze`
- `GET /api/overview`
- Every route in sections 2 through 6 except `GET /health`

The dashboard does not call `POST /api/analyze/image`, `POST /api/analyze/video`, or `GET /api/reports/{report_id}`. The extension calls the video route and the report route only after the user clicks "Analyse this video". The request contract is unchanged and is described in section 10.

## 10. Direct media analysis

`POST /api/analyze/image` and `POST /api/analyze/video` accept one multipart field, `file`. They do not accept a remote URL. The original filename is not used as a path and is not returned. The extension may POST a user-initiated recording of the visible tab to the existing video route. That recording is rendered tab video, not the platform's original file, and the request still has exactly one `file` field.

A caller receives HTTP 200 only when the job status is `completed`. That means the shared detector finished and the result was stored. `completed` is not a claim that the media is fake.

```json
{
  "report_id": "rpt_abc",
  "job_id": "rpt_abc",
  "status": "completed",
  "status_reason": null,
  "media_type": "image",
  "media_asset_id": "ma_abc",
  "byte_size": 1234,
  "sha256": "hex sha256 of the file bytes",
  "created_at": "2026-11-05T10:00:00.000000Z",
  "completed_at": "2026-11-05T10:00:00.000000Z",
  "result": {
    "status": "scored",
    "media_type": "image",
    "prediction": "uncertain",
    "fake_score": 0.5,
    "score_semantics": "raw_model_score_not_calibrated_probability",
    "model": {"name": "ms_eff_gcvit_b0", "checkpoint_dataset": "ff++"},
    "error_code": null,
    "error_message": null,
    "warnings": []
  }
}
```

`prediction` is `real`, `fake`, `uncertain`, or null. A score of 0.5 stays `uncertain`. `no_face` is a completed detector result with `fake_score` and `prediction` null. Video results add `frames_sampled`, `frames_scored`, `frames_with_faces`, `aggregation_method`, `aggregate_prediction`, `aggregate_fake_score`, and `frame_results` (`timestamp_seconds`, `face_detected`, `status`, `prediction`, `fake_score`). New analyses add `aggregation_policy` `video_aggregation_v2` and `aggregation_evidence`. A stored report is returned as it was saved. Older reports keep `video_aggregation_v1` when that version was stored with them, and are not recalculated. V2 labels a video fake only when the median is at least 0.8, temporal evidence is sufficient, enough scored frames pass the documented quality floors, and the high scores are not only low-quality detections. Temporal evidence is two bursts separated by more than 1 second, or one burst lasting more than 2 seconds. Real still requires every scored frame to be at or below 0.2. Frame results may also include detector confidence, face box size, face area ratio, crop size, quality warnings, and burst id. Per-frame scores are unchanged.

`sha256` is a hash of the stored bytes. It is not the perceptual `media_hash` used by the coordination graph.

Other responses:

| Case | HTTP | `status` |
|---|---|---|
| Empty file | 422 | `failed`, no job row |
| Undecodable file | 422 | `failed`, and `GET` returns 409 |
| Detector exception | 422 | `failed`, no exception text |
| Unsupported type | 415 | `failed`, no job row |
| File over the route limit | 413 | `failed`, no job row |
| Database write failure | 500 | no completed job and the stored file is removed |
| Unknown report | 404 | none |

`GET /api/reports/{report_id}` returns the stored object only when `status` is `completed`. A stored failed job returns 409 with that job. Nothing on this route is a sample score.

Image files are limited to 20 MB and video files to 100 MB. Bytes are stored under `backend/data/media/` with a server-chosen name. The response does not include that path.

## 11. Campaign X sync

`POST /api/campaigns/{campaign_id}/sync/x` calls `GET https://api.x.com/2/tweets/search/recent` for one existing campaign. The bearer token is `X_BEARER_TOKEN` on the backend. If it is missing, the response is HTTP 503 and `code` is `x_connector_not_configured`. The rest of the API still starts.

Recent search only returns public posts from the preceding seven days. A `start_time` older than that window is rejected locally. This route does not run on a schedule, does not scrape `x.com`, and does not download media.

```json
{
  "query": "synthetic media",
  "max_results": 10,
  "max_pages": 1,
  "max_posts": 10,
  "start_time": null
}
```

`query` is stored on the campaign's X source. A later call can omit it and reuse the stored query. `max_results` is the page size, from 10 to 100, and defaults to 10. `max_pages` defaults to 5 and cannot exceed 10. `max_posts` defaults to 100 and cannot exceed 500. Each page is one billed X API request. The caps above are the defaults from `.env.example`.

HTTP 200 means the rows that were fetched were saved. `complete` is true only when X did not offer another page and the configured cap was not reached. A capped sync is `status: "partial"` and `complete: false`.

```json
{
  "campaign_id": "Cabc",
  "status": "completed",
  "complete": true,
  "query": "synthetic media",
  "search_window": "preceding_seven_days",
  "source": {
    "platform": "x",
    "api": "x_api_v2",
    "endpoint": "https://api.x.com/2/tweets/search/recent"
  },
  "posts_fetched": 1,
  "posts_inserted": 1,
  "posts_already_known": 0,
  "referenced_posts_resolved": 0,
  "referenced_posts_unresolved": 0,
  "accounts_inserted": 1,
  "accounts_updated": 0,
  "media_references": 0,
  "relationships_inserted": 0,
  "relationships_already_known": 0,
  "pages_retrieved": 1,
  "more_pages_available": false,
  "stopped_by_limit": false,
  "media": [],
  "relationships": [],
  "analysis": "not_performed",
  "coordination_graph": "unchanged",
  "synced_at": "2026-11-05T10:00:00.000000Z"
}
```

`relationships` uses the original post as `source_post_id` and the repost, quote, or reply as `referencing_post_id`. X `retweeted` is stored as `reposted`, `quoted` stays `quoted`, and `replied_to` stays `replied_to`. Replies are conversation references, not propagation. These rows go in `post_relationships`. They are not added to `graph_edges`, which remains the inferred account-similarity graph. A referenced id with no expanded post is stored as a relationship and does not receive invented text.

`media` lists keys and types only. `variant_access` says whether X included variants. The variant URL is stored for a later retrieval step and is not returned. `analysed` is false. No analysis job is created.

`GET /api/campaigns/{campaign_id}/x` returns the stored query, the latest saved sync, accounts, posts, media metadata without variant URLs, and the explicit relationships. Unknown campaigns are HTTP 404.

| X result | HTTP | `code` |
|---|---|---|
| No token | 503 | `x_connector_not_configured` |
| Authentication failed | 401 | `x_authentication_failed` |
| Access denied | 403 | `x_permission_denied` |
| Credits exhausted | 402 | `x_credits_exhausted` |
| Rate limit | 429 | `x_rate_limited` |
| Network or X server failure after retries | 502 | `x_network_error` or `x_server_error` |
| Database transaction failure | 500 | no completed sync row |

Permanent 4xx responses are not retried. Network errors and HTTP 500, 502, 503, and 504 are retried up to three attempts. A failed request does not mark the sync completed. Repeating a sync updates the same account, post, media key, and relationship instead of inserting duplicates.
