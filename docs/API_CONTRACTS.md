# Veritas AI — API Contracts

**Status:** Revised on 2026-11-05 for the Chrome extension architecture. These routes are not implemented. No platform connector has been verified.

Any change must be agreed by all three members before implementation.

Base path: `/api/v1`

JSON responses use `application/json`. The only multipart route is the optional developer testing upload in section 7. The extension must not call that route.

The extension calls this backend. It does not call Bluesky, Mastodon, X, Reddit, Instagram, or Facebook directly, and it does not scrape pages.

## Shared conventions

- Use stable prefixed IDs. Do not use array positions as identifiers.
- Timestamps are ISO-8601 with a timezone. Store UTC internally.
- Allowed `prediction` values: `real`, `fake`, `uncertain`, `unsupported`.
- A missing face produces `unsupported` or `uncertain`, not `real`.
- `fake_score` is a raw model score, not a calibrated probability. Use `null` when there is no score.
- If inference or a platform fetch fails, return an error or an explicit failure status. Do not invent a score, post, account, or alert.
- `implementation_status` for a connector is one of `not_implemented`, `not_verified`, `verified`.
- `not_verified` means code exists but this team has not completed a successful live call. Do not label a connector `verified` until that call has been recorded.
- Initial connector scope is `bluesky` and `mastodon`. `x`, `reddit`, `instagram`, and `facebook` stay `not_implemented` unless an official authorized API client is added. Scraping is out of contract.
- Do not commit uploaded media, checkpoints, credentials, `.env`, or large datasets.
- Validation errors name the field and the reason.

## 1. Health check

### `GET /health`

```json
{
  "status": "ok",
  "service": "veritas-ai-api",
  "version": "0.2.0"
}
```

## 2. Platform monitoring

A monitor stores the analyst's selected platforms and topics. A refresh asks the backend connectors for matching public posts. It does not mean those connectors already work.

### `GET /api/v1/platforms`

```json
{
  "platforms": [
    {
      "platform": "bluesky",
      "access": "public_api",
      "implementation_status": "not_implemented",
      "last_verified_at": null,
      "notes": "Planned initial connector. No live fetch has been verified."
    },
    {
      "platform": "mastodon",
      "access": "public_api",
      "implementation_status": "not_implemented",
      "last_verified_at": null,
      "notes": "Requires an instance base URL. No live fetch has been verified."
    }
  ]
}
```

Include `x`, `reddit`, `instagram`, and `facebook` with `"access": "official_authorized_api"` and `"implementation_status": "not_implemented"`. Do not return posts for them.

### `POST /api/v1/monitors`

```json
{
  "name": "Topic watch",
  "platforms": ["bluesky", "mastodon"],
  "topics": ["synthetic media"],
  "mastodon_instance": "https://example.invalid",
  "limit_per_platform": 20
}
```

Rules:

- `platforms` and `topics` are required. `topics` must contain at least one non-empty string.
- `limit_per_platform` defaults to 20 and must not exceed 50 for the MVP.
- `mastodon_instance` is required when `mastodon` is selected. Store the base URL; do not assume one global Mastodon server.
- Reject unknown platform names. Accepting `x`, `reddit`, `instagram`, or `facebook` is allowed only so the monitor can record intent. A refresh must not scrape those platforms.

Response:

```json
{
  "monitor_id": "mon_0001",
  "name": "Topic watch",
  "platforms": ["bluesky", "mastodon"],
  "topics": ["synthetic media"],
  "status": "configured",
  "created_at": "2026-11-05T13:30:00+05:30"
}
```

### `GET /api/v1/monitors`

### `GET /api/v1/monitors/{monitor_id}`

Return the stored monitor plus the latest refresh summary. `latest_refresh` is `null` before the first refresh.

### `POST /api/v1/monitors/{monitor_id}/refresh`

No request body. The backend reads the stored monitor and calls only the connectors that are implemented. Each platform result is reported separately.

```json
{
  "monitor_id": "mon_0001",
  "refresh_id": "ref_0001",
  "status": "completed",
  "platform_results": [
    {
      "platform": "bluesky",
      "implementation_status": "not_implemented",
      "fetch_status": "skipped",
      "posts_retrieved": 0,
      "error": null
    }
  ],
  "posts_retrieved": 0,
  "started_at": "2026-11-05T13:31:00+05:30",
  "finished_at": "2026-11-05T13:31:01+05:30"
}
```

`fetch_status` is `skipped`, `succeeded`, or `failed`. `posts_retrieved` counts only posts returned by the connector. A skipped or failed platform contributes zero posts.

### `GET /api/v1/monitors/{monitor_id}/alerts`

Alerts are review prompts derived from stored media jobs or graph signals. An alert is not an accusation.

```json
{
  "monitor_id": "mon_0001",
  "alerts": [
    {
      "alert_id": "alt_0001",
      "severity": "review",
      "reason": "media_analysis_completed",
      "post_id": "post_0001",
      "media_job_id": "job_0001",
      "graph_edge_id": null,
      "summary": "A stored detector result is ready for human review.",
      "created_at": "2026-11-05T13:40:00+05:30"
    }
  ]
}
```

Allowed `severity`: `info`, `review`. Allowed `reason`: `media_analysis_completed`, `media_unsupported`, `graph_relationship_found`, `connector_unavailable`.

## 3. Normalized social posts

Every connector maps its own response into this shape before storage or graph construction. Platform-specific JSON is not sent to the extension as the primary record.

```json
{
  "post_id": "post_0001",
  "monitor_id": "mon_0001",
  "platform": "bluesky",
  "platform_post_id": "platform-native-id",
  "instance": null,
  "account_id": "account-native-id",
  "account_handle": "example.invalid",
  "timestamp": "2026-11-05T10:00:00Z",
  "text": "Post text supplied by the platform API.",
  "post_url": "https://example.invalid/post/1",
  "topics": ["synthetic media"],
  "retrieval": {
    "method": "official_public_api",
    "connector": "bluesky",
    "refresh_id": "ref_0001",
    "retrieved_at": "2026-11-05T13:31:00+05:30",
    "implementation_status": "not_verified"
  },
  "media": [
    {
      "media_id": "med_0001",
      "media_type": "image",
      "mime_type": "image/jpeg",
      "source_url": "https://example.invalid/media/1.jpg"
    }
  ],
  "provenance_label": "platform_api"
}
```

Rules:

- Required: `post_id`, `monitor_id`, `platform`, `platform_post_id`, `account_id`, `timestamp`, `retrieval`, `provenance_label`.
- `text` may be empty. `media` may be an empty array.
- `instance` is the Mastodon base URL, and `null` for Bluesky.
- `provenance_label` is `platform_api` for connector results. Fixture records use `synthetic_demo` or `curated_public_sample` and must not use `platform_api`.
- `retrieval.method` is `official_public_api` or `official_authorized_api`. There is no scraping method.
- Preserve the platform's post ID, account ID, timestamp, URL, and media URL.

### `GET /api/v1/monitors/{monitor_id}/posts`

```json
{
  "monitor_id": "mon_0001",
  "posts": [],
  "count": 0
}
```

`posts` contains normalized post objects. An empty list is valid when no connector has returned posts.

## 4. Media-analysis jobs

The product path analyses media already attached to a stored post. The client supplies a `media_id`. The backend resolves the stored official `source_url`. The product path does not accept an arbitrary URL or a file upload.

### `POST /api/v1/media-jobs`

```json
{
  "media_id": "med_0001"
}
```

Response:

```json
{
  "job_id": "job_0001",
  "media_id": "med_0001",
  "post_id": "post_0001",
  "monitor_id": "mon_0001",
  "media_type": "image",
  "status": "queued",
  "result": null,
  "created_at": "2026-11-05T13:35:00+05:30"
}
```

`status` is `queued`, `running`, `completed`, `failed`, or `unsupported`.

### `GET /api/v1/media-jobs/{job_id}`

While the job is unfinished, `result` stays `null`. A completed image result:

```json
{
  "job_id": "job_0001",
  "media_id": "med_0001",
  "post_id": "post_0001",
  "monitor_id": "mon_0001",
  "media_type": "image",
  "status": "completed",
  "result": {
    "model": {
      "name": "record-at-runtime",
      "checkpoint_dataset": "record-at-runtime",
      "version": "record-at-runtime"
    },
    "face_count": 1,
    "prediction": "uncertain",
    "fake_score": null,
    "score_semantics": "raw_model_score_not_calibrated_probability",
    "warnings": []
  },
  "created_at": "2026-11-05T13:35:00+05:30",
  "finished_at": "2026-11-05T13:35:05+05:30"
}
```

A completed video result uses the same job envelope. Its `result` contains:

- `frames_sampled`
- `frames_with_faces`
- `frame_results`: `timestamp_seconds`, `face_detected`, `prediction`, `fake_score`
- `aggregate_prediction`
- `aggregate_fake_score`
- `aggregation_method`
- `score_semantics`
- `warnings`

Video rules:

- Preserve frame timestamps.
- Sample at most 20 frames.
- If no sampled frame has a usable face, set `aggregate_prediction` to `unsupported` or `uncertain` and explain why in `warnings`.
- Do not mark the whole video fake because of one frame.
- Record the aggregation method and the number of usable frames.

Failed jobs return `status: "failed"`, `result: null`, and an `error` string. They do not include a fabricated score.

## 5. Campaign graph results

The graph is built from normalized posts stored for one monitor. It is not built from a hard-coded drawing.

### `POST /api/v1/monitors/{monitor_id}/graph`

No request body. Rebuild the graph from the current stored posts.

### `GET /api/v1/monitors/{monitor_id}/graph`

```json
{
  "monitor_id": "mon_0001",
  "graph_id": "graph_0001",
  "provenance_labels": ["platform_api"],
  "nodes": [
    {
      "id": "account:bluesky:account-native-id",
      "type": "account",
      "label": "example.invalid",
      "platform": "bluesky"
    },
    {
      "id": "post:post_0001",
      "type": "post",
      "label": "post_0001",
      "platform": "bluesky",
      "timestamp": "2026-11-05T10:00:00Z"
    }
  ],
  "edges": [
    {
      "id": "edge_0001",
      "source": "account:bluesky:account-native-id",
      "target": "post:post_0001",
      "type": "published",
      "signals": []
    }
  ],
  "clusters": [],
  "methodology": "Describe the signals and thresholds that were actually used."
}
```

Edge types: `published`, `similar_text`, `similar_media`, `shared_url`, `temporally_coordinated`.

Every similarity or coordination edge includes evidence:

```json
{
  "name": "text_similarity",
  "value": 0.92,
  "method": "tfidf_cosine",
  "threshold": 0.85
}
```

Rules:

- An edge is an observed relationship, not proof of maliciousness.
- Do not return an opaque coordination score unless the contributing signals are also present.
- The extension must show `provenance_labels` and state that clusters need human review.
- An empty graph is valid when the monitor has no stored posts.

## 6. Investigation reports

### `POST /api/v1/investigations`

```json
{
  "monitor_id": "mon_0001",
  "media_job_ids": ["job_0001"]
}
```

`media_job_ids` may be empty. The report then includes dissemination findings and explicitly lists the missing media analysis. It must not invent detector results.

```json
{
  "investigation_id": "inv_0001",
  "report_id": "rep_0001",
  "monitor_id": "mon_0001",
  "status": "completed"
}
```

### `GET /api/v1/reports/{report_id}`

```json
{
  "report_id": "rep_0001",
  "investigation_id": "inv_0001",
  "monitor_id": "mon_0001",
  "media_findings": [],
  "dissemination_findings": [],
  "alerts": [],
  "uncertainties": [],
  "recommended_actions": [
    "Review the stored posts and detector outputs before drawing a conclusion."
  ],
  "provenance_labels": [],
  "generated_at": "2026-11-05T13:45:00+05:30"
}
```

`media_findings` copy stored job results, model identity, and limitations. `dissemination_findings` copy stored graph signals. `recommended_actions` are human-review steps only. The report must not add posts, accounts, scores, or claims that are absent from stored records.

## 7. Developer testing interface

These routes are for local development only. The extension popup and side panel must not call them, and the demo must not depend on them.

### `POST /api/v1/dev/media-jobs/upload`

`multipart/form-data`

- `file`: required image or MP4
- `media_type`: `image` or `video`
- `provenance_label`: required, `synthetic_demo` or `curated_public_sample`

Response: the same media-job object as section 4, with `post_id` and `monitor_id` set to `null`.

### `POST /api/v1/dev/posts/import`

Accepts a JSON array of normalized posts whose `provenance_label` is `synthetic_demo` or `curated_public_sample`. Reject any item labelled `platform_api`. This fixture exists so the graph can be tested before a connector is verified.

Enforce file type, size limits, and safe temporary-file handling on the upload route.
