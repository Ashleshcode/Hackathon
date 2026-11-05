> **Superseded.** This file is the original kickoff snapshot. Use `docs/API_CONTRACTS.md` at the repository root. The current contract is extension monitoring, not upload-first analysis.

# Veritas AI — API Contracts (MVP)

**Status:** Initial integration contract. Any change must be agreed by all three members before implementation.

Base path: `/api/v1`

JSON responses use `application/json` unless the request is multipart upload.

## 1. Health check

### `GET /health`

Response:

```json
{
  "status": "ok",
  "service": "veritas-ai-api",
  "version": "0.1.0"
}
```

## 2. Image analysis

### `POST /api/v1/analyze/image`

Request: `multipart/form-data`

- `file`: required image file (JPEG/PNG/WebP)
- `source_label`: optional string, e.g. `user_upload`

Response shape:

```json
{
  "analysis_id": "img_0001",
  "media_type": "image",
  "filename": "sample.jpg",
  "model": {
    "name": "ms_eff_gcvit_b0",
    "checkpoint_dataset": "ff++",
    "version": "record-at-runtime"
  },
  "face_count": 1,
  "prediction": "fake",
  "fake_score": 0.87,
  "score_semantics": "raw_model_score_not_calibrated_probability",
  "status": "completed",
  "warnings": [],
  "created_at": "2026-11-05T12:00:00+05:30"
}
```

Allowed `prediction`: `real`, `fake`, `uncertain`, `unsupported`.

Rules:
- `face_count == 0` should normally produce `unsupported` or `uncertain`, not `real`.
- If inference fails, return an appropriate HTTP error; do not fabricate a score.
- Keep the exact model output in `fake_score`; do not describe it as calibrated confidence.

## 3. Video analysis

### `POST /api/v1/analyze/video`

Request: `multipart/form-data`

- `file`: required video file (MP4 recommended)
- `num_frames`: optional integer, default 20, hard maximum 20 for MVP
- `source_label`: optional string

Response shape:

```json
{
  "analysis_id": "vid_0001",
  "media_type": "video",
  "filename": "sample.mp4",
  "model": {
    "name": "ms_eff_gcvit_b0",
    "checkpoint_dataset": "ff++",
    "version": "record-at-runtime"
  },
  "frames_sampled": 20,
  "frames_with_faces": 15,
  "frame_results": [
    {
      "timestamp_seconds": 1.25,
      "face_detected": true,
      "prediction": "fake",
      "fake_score": 0.81
    }
  ],
  "aggregate_prediction": "uncertain",
  "aggregate_fake_score": 0.58,
  "aggregation_method": "document-the-method-used",
  "score_semantics": "aggregate_raw_model_score_not_calibrated_probability",
  "status": "completed",
  "warnings": []
}
```

Rules:
- Preserve frame timestamps.
- If no sampled frame has a detectable face, return `unsupported`/`uncertain` and explain why.
- Do not label the entire video fake because of one suspicious frame.
- Document the aggregation method and the number of usable frames.

## 4. Social-post import

### `POST /api/v1/campaigns/import`

Request: JSON body or uploaded CSV file. For the MVP, the frontend may parse CSV and send normalized JSON.

Normalized post fields:

```json
{
  "source_dataset_label": "synthetic_demo",
  "posts": [
    {
      "post_id": "p001",
      "platform": "platform_a",
      "account_id": "account_01",
      "timestamp": "2026-11-05T10:00:00Z",
      "text": "Example post text",
      "media_sha256": "optional-exact-file-hash",
      "media_phash": "optional-perceptual-hash",
      "media_reference": "optional-local-reference-or-url",
      "post_url": "optional-public-post-url"
    }
  ]
}
```

Response:

```json
{
  "campaign_id": "camp_0001",
  "posts_imported": 40,
  "accounts_found": 18,
  "source_dataset_label": "synthetic_demo",
  "status": "completed"
}
```

Rules:
- Required per post: `post_id`, `platform`, `account_id`, `timestamp`.
- `text` may be empty; missing optional media fields must be allowed.
- Validate timestamps and normalize to UTC internally.
- Preserve platform and dataset provenance.

## 5. Campaign graph

### `GET /api/v1/campaigns/{campaign_id}/graph`

Response:

```json
{
  "campaign_id": "camp_0001",
  "source_dataset_label": "synthetic_demo",
  "nodes": [
    {
      "id": "account:account_01",
      "type": "account",
      "label": "account_01",
      "platform": "platform_a"
    },
    {
      "id": "post:p001",
      "type": "post",
      "label": "p001",
      "platform": "platform_a",
      "timestamp": "2026-11-05T10:00:00Z"
    }
  ],
  "edges": [
    {
      "id": "edge_001",
      "source": "account:account_01",
      "target": "post:p001",
      "type": "published",
      "signals": []
    }
  ],
  "clusters": [],
  "methodology": "Explain the signals and thresholds used."
}
```

Recommended edge types: `published`, `similar_text`, `similar_media`, `shared_url`, `temporally_coordinated`.

Every similarity/coordination edge must include evidence in `signals`, for example:

```json
{
  "name": "text_similarity",
  "value": 0.92,
  "method": "tfidf_cosine",
  "threshold": 0.85
}
```

Rules:
- A graph edge represents an observed relationship, not proof of maliciousness.
- Avoid a single opaque `coordination_score` unless its contributing signals are also returned.
- UI must display the source dataset label and a caution that clusters require human review.

## 6. Investigation report

### `POST /api/v1/investigations`

Request:

```json
{
  "campaign_id": "camp_0001",
  "analysis_ids": ["img_0001", "vid_0001"]
}
```

Response:

```json
{
  "investigation_id": "inv_0001",
  "report_id": "rep_0001",
  "status": "completed"
}
```

### `GET /api/v1/reports/{report_id}`

Response sections:

- `media_findings`: detector outputs, model identity, limitations
- `dissemination_findings`: observed graph signals and cluster evidence
- `uncertainties`: missing data, unsupported media, model caveats
- `recommended_actions`: human-review steps only
- `source_dataset_label`: provenance of imported social-post records
- `generated_at`: timestamp

The report generator may summarize these structured fields. It must not create new evidence or claims.

## 7. Shared conventions

- Use UUIDs or stable prefixed IDs; do not rely on array positions as identifiers.
- Timestamps returned by the API should be ISO-8601 with timezone.
- Upload endpoints must enforce allowed extensions, size limits, and safe temporary-file handling.
- Do not commit uploaded media, checkpoints, credentials, `.env`, or large datasets to Git.
- All endpoints return meaningful validation errors; no silent fallback to fabricated data.
- API changes require a coordinated update to this document and affected frontend/backend code.
