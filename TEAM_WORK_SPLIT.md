# Veritas AI — Team Work Split

**Project:** AI-Driven Detection & Countermeasures Against Fake Social Media Content  
**Team size:** 3 members  
**Product UI:** Chrome Extension, Manifest V3, popup and side panel  
**Platforms:** X API v2 first. YouTube Data API only for one explicitly requested video.  
**Contract:** `docs/API_CONTRACTS.md`

The product is not an upload website. Do not scrape `x.com` or YouTube. Do not implement the detector in the architecture pass.

---

## 1. Product objective

An analyst uses the extension to:

1. Search recent X posts and open a post through the official X API v2.
2. See the author, timestamp, and any repost, quote, or reply relationship the payload contains.
3. Create an analysis job only when X resolved a permitted media variant.
4. Explicitly investigate the current YouTube video, see its permitted metadata, and see X references to that URL.
5. Read the investigation and an explainable graph.

The extension calls local FastAPI. `X_BEARER_TOKEN` and `YOUTUBE_API_KEY` stay in the backend `.env`.

Detector output, official relationship records, similarity signals, and the analyst's conclusion stay separate. A graph edge is not an accusation. A YouTube metadata record is not a deepfake result.

---

## 2. Team allocation

| Member | Machine | Primary ownership | Secondary ownership |
|---|---|---|---|
| **Member 1 — Backend and X** | GPU machine 1 | FastAPI, SQLite, X API v2 connector, investigation routes | YouTube Data API context connector and secret handling |
| **Member 2 — Permitted media jobs** | GPU machine 2 | Analysis jobs for X media whose variant URL was officially resolved | Frame sampling with OpenCV and FFmpeg |
| **Member 3 — Extension and graph** | CPU-capable machine | Popup, side panel, backend client, and the explicit YouTube action | NetworkX graph for X relationships and YouTube references |

Do not modify the global Python 3.13 PyTorch install. The project `.venv` already has `torch==2.14.1+cu130` and stays as it is until a later, separate install task. Do not download a detector checkpoint yet.

`frontend/` is not the product. `extension/shared/` and `extension/icons/` stay. New extension code belongs in the finalized folders below.

`backend/app/agents/` is reserved. The MVP does not add an autonomous agent.

---

## 3. Member 1 — Backend and X

### Objective

Own the FastAPI process, SQLite investigations, the X connector, and the YouTube context connector.

### Responsibilities

1. Implement `GET /health`, `POST /api/x/search`, `GET /api/x/posts/{post_id}`, `POST /api/youtube/context`, `POST /api/investigations`, `GET /api/investigations/{id}`, and register the media and graph routers.
2. Read `X_BEARER_TOKEN` and `YOUTUBE_API_KEY` from the environment. Never log the raw values or return them.
3. Call only official X API v2 recent search and post lookup. Request author, created time, referenced tweets, and video media fields.
4. Map `retweeted`, `quoted`, and `replied_to` to `reposted`, `quoted`, and `replied_to`.
5. Resolve a video variant only from `variants` in the official media object. If it is absent, report `variant_access: "absent"` and do not scrape a page for a URL.
6. Implement YouTube `videos.list` for the single submitted video ID. Do not search YouTube across other owners. Do not download audiovisual bytes.
7. Keep `implementation_status` honest. Empty results are not replaced with sample posts.
8. Assemble `GET /api/investigations/{id}` from stored rows only.

Suggested files:

```text
backend/app/main.py
backend/app/api/x.py
backend/app/api/youtube.py
backend/app/api/investigations.py
backend/app/connectors/x_api.py
backend/app/connectors/youtube_api.py
backend/app/database/database.py
backend/app/schemas/x_post.py
backend/app/schemas/investigation.py
backend/tests/test_x_contract.py
backend/tests/test_youtube_context.py
```

### Does not own

- Frame extraction.
- Extension screens and the YouTube tab action.
- Graph edge layout, except registering Member 3's router.
- A content script on `x.com`.

---

## 4. Member 2 — Permitted media jobs

### Objective

Analyse X image or video bytes only after Member 1 has resolved a permitted variant URL.

### Responsibilities

1. Implement `POST /api/media/analyze` and `GET /api/media/jobs/{job_id}`.
2. Accept `post_id` and `media_key` only. Reject a client-supplied URL and reject any YouTube target.
3. When `variant_access` is `absent`, return `unavailable` and do not fetch another copy of the file.
4. When a permitted file exists, validate it, sample at most 20 video frames, and keep timestamps.
5. Call the shared detector interface later. Until that model exists, return `detector_not_implemented` and a null score. Do not invent a prediction.
6. Do not add a product upload form. A developer fixture must be labelled `synthetic_demo` and cannot be disguised as an X API result.

Suggested files:

```text
backend/app/api/media.py
backend/app/media/media_jobs.py
backend/app/media/frame_sampling.py
backend/app/media/video_processor.py
backend/tests/test_media_jobs.py
```

### Does not own

- X or YouTube HTTP clients.
- Extension UI.
- Graph construction.
- Model training or checkpoint download.

---

## 5. Member 3 — Extension and graph

### Objective

Build the Manifest V3 extension and the investigation graph.

### Responsibilities

1. Add `extension/manifest.json` when implementation starts. It is not in the repository yet, so Chrome cannot load the extension today.
2. Popup: X search box and a control that opens one returned post. No file picker.
3. Side panel: post details, variant availability, media-job status, YouTube context, and the graph.
4. `extension/services/`: call `http://127.0.0.1` backend routes only. Do not embed API keys.
5. `extension/content/`: used only for an explicit YouTube action. Read the current watch URL after the analyst invokes the extension, extract one video ID, and send it to the backend. Do not run this on `x.com`. Do not observe tab changes, and do not save a browsing history.
6. Request `activeTab` for that explicit action. Do not request a content script match on `x.com`. Do not use `tabCapture`.
7. Build the NetworkX graph from stored X relationships and, when present, one YouTube reference node without a detector score.
8. Show `not_implemented` and `not_verified` as returned. Do not draw fixture posts as a live X feed.

Suggested files:

```text
extension/manifest.json
extension/popup/
extension/sidepanel/
extension/background/
extension/content/youtube_context.js
extension/services/api.js
backend/app/intelligence/graph_engine.py
backend/app/api/graph.py
backend/tests/test_graph_engine.py
```

`extension/manifest.json` and `youtube_context.js` are future files. This task does not create them.

### Does not own

- X or YouTube server credentials.
- Media download and frame sampling.
- Detector inference.
- FastAPI process startup. Member 1 registers the graph router.

---

## 6. Shared routes

| Route | Owner |
|---|---|
| `POST /api/x/search` | Member 1 |
| `GET /api/x/posts/{post_id}` | Member 1 |
| `POST /api/youtube/context` | Member 1 |
| `POST /api/media/analyze` | Member 2 |
| `POST /api/investigations` | Member 1 |
| `GET /api/investigations/{id}` | Member 1, shown by Member 3 |
| `GET /api/investigations/{id}/graph` | Member 3 service, Member 1 registration, Member 3 UI |

Change `docs/API_CONTRACTS.md` before changing both sides of a field.

---

## 7. Branches

```text
main
feature/x-backend            # Member 1
feature/x-media-jobs         # Member 2
feature/extension-graph      # Member 3
```

Do not do feature work directly on `main`.

---

## 8. Definition of done

- [ ] The extension loads unpacked and can submit an X search.
- [ ] Search and post lookup show official author, time, and relationship fields, or an explicit not-implemented or error state.
- [ ] A media job is created only for permitted X media, and a missing variant stays `unavailable`.
- [ ] YouTube context is user-initiated, covers one video, and states that audiovisual analysis was not performed.
- [ ] The investigation and graph views use stored records only.
- [ ] The extension contains no platform secret and no `x.com` content script.
- [ ] The demo does not depend on file upload.

## Out of scope

- Scraping `x.com` or YouTube, including `tabCapture`.
- Downloading YouTube audiovisual content.
- Storing browsing history.
- Aggregating YouTube metadata for videos the user did not submit.
- Training a detector or claiming the model is integrated before a real inference run.
- Autonomous moderation or takedown.
