# Veritas AI — Team Work Split

**Project:** AI-Driven Detection & Countermeasures Against Fake Social Media Content  
**Team size:** 3 members  
**Product UI:** Chrome Extension, Manifest V3, popup and side panel  
**Working model:** One shared repository, separate feature branches, and `docs/API_CONTRACTS.md` as the integration contract.

The earlier website-upload plan is retired. Do not build the demo around file upload or CSV import. Those remain optional developer tests.

---

## 1. Product objective

A human analyst uses the extension to:

1. Select social platforms and monitoring topics.
2. Ask the backend to retrieve matching posts through authorized platform APIs.
3. Analyse images and videos attached to those posts.
4. Inspect explainable relationships among the stored posts.
5. Read alerts and an investigation report built from stored results.

The extension calls the local FastAPI backend. Platform API calls stay in the backend. The extension must not scrape pages.

### Scope boundary

This is a hackathon prototype. Bluesky and Mastodon public APIs are the initial connectors, and neither is verified yet. X, Reddit, Instagram, and Facebook may be added only through official authorized APIs. Demo fixtures must be labelled `synthetic_demo` or `curated_public_sample` and must not be presented as a live feed.

Keep these results separate:

- **Media detector output:** a model score for one piece of media.
- **Coordination signal:** an observed relationship such as similar text, similar media, or close timestamps.
- **Analyst conclusion:** a human decision. The system must not declare an account malicious because a score or graph signal is elevated.

---

## 2. Team allocation

| Member | Machine | Primary ownership | Secondary ownership |
|---|---|---|---|
| **Member 1 — Backend and connectors** | GPU machine 1 | FastAPI, SQLite, platform monitoring, Bluesky and Mastodon connectors, investigation reports | Shared detector adapter and backend integration |
| **Member 2 — Media jobs** | GPU machine 2 | Image and video job processing, frame sampling, OpenCV and FFmpeg | Media-job tests and the developer-only upload route |
| **Member 3 — Extension and graph** | CPU-capable machine | Manifest V3 popup, side panel, and service worker | NetworkX graph and its evidence view |

The GPU machines are development machines, not a cluster. Load one detector in the backend process and reuse it for images and sampled frames. Member 3 does not need a GPU.

The existing `frontend/` placeholders are not the product. Do not turn them into the demo UI.

---

## 3. Member 1 — Backend and connectors

### Objective

Own the FastAPI application, local SQLite storage, platform monitoring, and the report assembled from other members' outputs.

### Responsibilities

1. Implement the health, monitor, refresh, post, alert, and report routes in `docs/API_CONTRACTS.md`.
2. Store monitors, normalized posts, media jobs, graphs, and reports in SQLite.
3. Add Bluesky and Mastodon connectors that map official API responses into the normalized post schema.
4. Keep each connector's `implementation_status` at `not_implemented` until code exists, then `not_verified` until a live call succeeds. Do not mark `verified` from documentation or a mocked response.
5. On refresh, skip unimplemented platforms with `posts_retrieved: 0`. Never fill a failed fetch with sample posts.
6. Leave X, Reddit, Instagram, and Facebook unimplemented. Do not add scrapers, cookie replay, or logged-in browser automation.
7. Register Member 2's media-job router and Member 3's graph router.
8. Build a report only from stored media jobs and stored graph results.
9. Keep the optional developer routes under `/api/v1/dev/` out of the extension.

Suggested files:

```text
backend/app/main.py
backend/app/api/monitors.py
backend/app/api/reports.py
backend/app/connectors/bluesky.py
backend/app/connectors/mastodon.py
backend/app/storage/database.py
backend/app/models/deepfake_detector.py
backend/app/models/model_manager.py
backend/tests/test_monitors.py
backend/tests/test_reports.py
```

The detector adapter is still Member 1's file, but do not install or download a model until the team starts that task. The current `.venv` already has CUDA PyTorch and must be preserved. Do not modify global Python 3.13.

### Deliverables

- [ ] FastAPI application and SQLite schema.
- [ ] Monitor, refresh, posts, and alerts routes.
- [ ] Bluesky and Mastodon connectors with honest status fields.
- [ ] Report route that copies stored findings only.
- [ ] Detector adapter when model work is scheduled.

### Does not own

- Frame extraction and video aggregation.
- Extension popup, side panel, or service worker.
- Graph edge rules, except for registering the router.

---

## 4. Member 2 — Media jobs

### Objective

Turn a stored media attachment into a timestamped image or video analysis job.

### Responsibilities

1. Accept a job created from a stored `media_id`. Resolve the media from storage. Do not accept an arbitrary URL on the product route.
2. Validate images and common video files. Use OpenCV and FFmpeg.
3. Sample at most 20 video frames and keep each frame's timestamp.
4. Call Member 1's detector interface. Use a mock with the same result fields until that interface exists, and label mock output so it cannot reach the demo path.
5. Return `unsupported` or `uncertain` with a null score when no usable face is found.
6. Do not mark a whole video fake because of one frame. Document the aggregation rule.
7. Implement `POST /api/v1/dev/media-jobs/upload` as a developer test only.

Suggested files:

```text
backend/app/media/video_processor.py
backend/app/media/frame_sampling.py
backend/app/media/media_jobs.py
backend/app/api/media_jobs.py
backend/tests/test_media_jobs.py
backend/tests/test_video_processing.py
```

### Deliverables

- [ ] Job creation from a stored attachment.
- [ ] Timestamped frame sampling capped at 20 frames.
- [ ] Honest unsupported results for no-face and unreadable media.
- [ ] Developer upload route isolated from the extension.
- [ ] Tests for a valid file, a corrupt file, and a no-face file.

### Does not own

- Platform connectors and monitor configuration.
- Extension screens.
- Graph construction.
- A second copy of the production model.

---

## 5. Member 3 — Extension and graph

### Objective

Build the analyst-facing Manifest V3 extension and the explainable graph behind the side panel.

### Responsibilities

1. Add `manifest.json` only when implementing the extension. The current `extension/` folders are empty placeholders.
2. Popup: select platforms and topics, create a monitor, and request a refresh.
3. Side panel: show connector status, stored posts, alerts, graph evidence, and the investigation report.
4. Service worker: call the local FastAPI backend. Do not inject scrapers into social-media pages.
5. Show `not_implemented` and `not_verified` exactly as the backend returns them.
6. Build the NetworkX graph from stored normalized posts. Every similarity or coordination edge needs a signal name, value, method, and threshold.
7. Include one labelled `synthetic_demo` fixture for graph development. The side panel must show that label and must not call those posts a live feed.
8. Do not put a file-upload control in the popup or side panel.

Suggested files:

```text
extension/manifest.json
extension/popup/
extension/sidepanel/
extension/background/
extension/shared/
extension/icons/
backend/app/intelligence/graph_engine.py
backend/app/intelligence/similarity.py
backend/app/api/graph.py
backend/tests/test_graph_engine.py
```

`extension/manifest.json` is listed as a future file. It does not exist yet, and this task does not create it.

### Deliverables

- [ ] Unpacked Manifest V3 extension with popup and side panel.
- [ ] Monitor controls wired to the backend contract.
- [ ] Side panel for alerts, posts, graph evidence, and reports.
- [ ] Graph engine with evidence-backed edges and an empty-state result.
- [ ] A labelled synthetic fixture that cannot be mistaken for platform API data.

### Does not own

- Detector inference or checkpoint downloads.
- Video sampling.
- FastAPI entry-point registration. Member 1 registers the graph router.
- The retired React website.

---

## 6. Shared contract

| Function | Owner | Interface |
|---|---|---|
| Platform catalog and monitors | Member 1 | `/api/v1/platforms`, `/api/v1/monitors` |
| Refresh and normalized posts | Member 1 | `/api/v1/monitors/{id}/refresh`, `/posts` |
| Alerts | Member 1, shown by Member 3 | `/api/v1/monitors/{id}/alerts` |
| Media jobs | Member 2, registered by Member 1 | `/api/v1/media-jobs` |
| Graph | Member 3, registered by Member 1 | `/api/v1/monitors/{id}/graph` |
| Investigation report | Member 1, shown by Member 3 | `/api/v1/investigations`, `/api/v1/reports/{id}` |
| Developer upload and fixture import | Member 2 and Member 3 | `/api/v1/dev/*` only |

Change a field in `docs/API_CONTRACTS.md` before changing both sides. Do not have two members edit the same file at the same time.

---

## 7. Branches

```text
main
feature/platform-backend       # Member 1
feature/media-jobs             # Member 2
feature/extension-graph        # Member 3
```

Do not do feature work directly on `main`.

Suggested commit style:

```text
feat: add monitor refresh API
feat: add sampled video media job
feat: add extension side panel
fix: keep unverified connectors from returning fixture posts
```

---

## 8. Checkpoints

| Window | Required checkpoint | If missed |
|---|---|---|
| First slice | Extension shell, monitor API, and one media-job path | Keep connector status explicit. Do not invent a live feed. |
| Middle slice | Popup talks to refresh. Side panel shows a stored job or a clear empty state. | Stop extra platforms. Bluesky or Mastodon only. |
| Late slice | Report opens from stored jobs and graph edges. | Use the deterministic report. No extra narrative layer. |
| Freeze | Demo from the extension without upload | Fix blockers only. |

---

## 9. Definition of done

- [ ] The extension loads unpacked and opens the popup and side panel.
- [ ] The analyst can select platforms and topics and create a monitor.
- [ ] Refresh shows real per-platform status. Unverified connectors do not produce fake live posts.
- [ ] Attached media can produce a job result, or an explicit unsupported result.
- [ ] The graph is built from stored posts, and each coordination edge shows its evidence.
- [ ] The report uses stored media and graph outputs only.
- [ ] The demo does not require the developer upload screen.
- [ ] Synthetic fixtures and model limits are visible in the side panel.

## Out of scope until the checklist above is complete

- Unauthorized scraping of any platform.
- Training a detector or a language model.
- Claiming Bluesky, Mastodon, X, Reddit, Instagram, or Facebook works before a recorded successful call.
- Automatic takedown or account action.
- A website upload product.

---

## 10. Handover

| Member | Hands over |
|---|---|
| **Member 1** | FastAPI app, SQLite storage, platform connectors with honest status, report service, and the shared model adapter when model work begins. |
| **Member 2** | Media jobs, frame sampling, unsupported-media handling, and the isolated developer upload route. |
| **Member 3** | Manifest V3 popup and side panel, graph engine, labelled fixture, and the investigation views. |
