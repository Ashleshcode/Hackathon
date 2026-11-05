# Veritas AI — Integration Checklist

The product is the Chrome extension. X is the primary integration. YouTube is one explicit video's metadata and its permitted X references. Do not check an item until the command or screen has actually been run.

No live X API v2 or YouTube Data API call has been verified.

## Before feature coding

- [x] Shared Git repository exists.
- [x] Active docs are `PROJECT_CONTEXT.md`, `README.md`, `docs/API_CONTRACTS.md`, `docs/TEAM_WORK_SPLIT.md`, and this checklist.
- [x] `.env.example` lists `X_BEARER_TOKEN` and `YOUTUBE_API_KEY` as empty placeholders.
- [ ] `.env` exists only on the backend machine and is not committed. Extension source contains neither value.
- [x] This machine has `D:\Hackathon\.venv` on Python 3.11.7.
- [x] `.venv` imports `torch==2.14.1+cu130` and `torchvision==0.29.1+cu130`, and CUDA is available on the RTX 4060 Laptop GPU.
- [x] DeepGuard 1.1.1 and the shared detector are installed in `.venv` only. PyTorch remains `torch==2.14.1+cu130`. See `docs/MODEL_VALIDATION.md`. Global Python was not modified for this pass.
- [ ] FFmpeg is still missing from `PATH`.

## Member 1 — X and YouTube context

- [ ] FastAPI serves `GET /health`.
- [ ] `POST /api/x/search` calls official recent search, or returns `not_implemented` and an empty `posts` array.
- [ ] `GET /api/x/posts/{post_id}` returns author, timestamp, and referenced relationship types from the official payload.
- [ ] Video `variants` are read only from that payload. A missing variant stays `variant_access: "absent"`.
- [ ] `POST /api/youtube/context` requests `videos.list` for one submitted video ID.
- [ ] The YouTube response says audiovisual analysis was not performed.
- [ ] Failed API calls are not replaced with sample posts.

## Member 2 — media jobs

- [ ] `POST /api/media/analyze` accepts only `post_id` and `media_key`.
- [ ] A YouTube URL is rejected with `youtube_audiovisual_analysis_not_permitted`.
- [ ] A permitted X video, once available, keeps frame timestamps and stops at 20 frames.
- [ ] Direct byte routes in section 10 remain a separate backend test interface. `POST /api/media/analyze` does not download X variants yet.
- [ ] The extension has no upload control.

## Member 3 — extension and graph

- [ ] `manifest.json` is added and the unpacked extension loads. Until that file exists, this item stays open.
- [ ] Popup submits `POST /api/x/search` and can open `GET /api/x/posts/{post_id}`.
- [ ] The YouTube action runs only when the analyst invokes it, sends one video ID, and does not record other tabs.
- [ ] The manifest does not match `x.com` with a content script and does not request `tabCapture`.
- [ ] `extension/services/` talks only to the local backend and contains no API key.
- [ ] Side panel renders `GET /api/investigations/{id}` and `GET /api/investigations/{id}/graph`.
- [ ] A YouTube graph node has no detector score.

## Integration hardening

Checked against the registered FastAPI routes and the extension source. No live X or YouTube API call was made in this pass.

### Working routes

- `GET /health` returns `status`, `service`, `version`, and `detector.initialized`. The shared detector is created once in the application lifespan. The health request does not create another one.
- `POST /api/campaigns/import`
- `GET /api/campaigns`
- `GET /api/campaigns/{campaign_id}`
- `GET /api/campaigns/{campaign_id}/graph`
- `POST /api/campaigns/{campaign_id}/check-post`
- `POST /api/campaigns/{campaign_id}/sync/x` reads official recent search when `X_BEARER_TOKEN` is set. Tests mock the HTTP call. A missing token returns `x_connector_not_configured` and does not stop the rest of the API.
- `GET /api/campaigns/{campaign_id}/x` returns the stored accounts, posts, media metadata, and explicit relationships. Variant URLs stay in the database.

`campaigns.router`, `analysis.router`, and `media.router` are each included once, in `backend/app/main.py`. Campaigns, posts, coordination-graph edges, media assets, and analysis jobs are stored in `backend/data/veritas.db`. Startup creates those tables and then initializes the shared detector once. The graph is still an account-similarity graph. It is not the directional propagation graph. Nothing is monitored in the background.

- `POST /api/analyze/image`
- `POST /api/analyze/video`
- `GET /api/reports/{report_id}`

These three routes accept bytes from a trusted caller and return the stored detector result. The dashboard does not call them. The extension calls `POST /api/analyze/video` and `GET /api/reports/{report_id}` only after the user clicks "Analyse this video".

- `POST /api/media/analyze` accepts only a stored X `post_id` and `media_key`. It does not accept or fetch a URL. Without a linked local file the job is `unavailable` and has no score. With a linked file, the shared detector scores it.
- `GET /api/media/jobs/{job_id}` returns that stored job. The dashboard and extension do not call either route.

### Unsupported routes

These are not registered. The dashboard and extension do not call them, and they do not substitute a sample success:

- `POST /api/extension/analyze`
- `GET /api/overview` — the overview uses `GET /api/campaigns`. Media and investigation counts stay null.

Also still absent: `POST /api/x/search`, `GET /api/x/posts/{post_id}`, `POST /api/youtube/context`, `POST /api/investigations`, `GET /api/investigations/{id}`, and `GET /api/investigations/{id}/graph`.

Campaign X sync is not `POST /api/x/search`. It does not download media and it does not add rows to `graph_edges`. Replies are stored as `replied_to` and are not treated as propagation.

### Extension restrictions

- Manifest V3. Permissions are `activeTab`, `storage`, `tabCapture`, and `offscreen`, plus host access to `http://localhost:8000` only. No content script. No `scripting`, history, cookies, or debugger permission. No `<all_urls>`.
- A service worker and an offscreen document exist only for the "Analyse this video" action. Opening the popup does not start a recording. Capture is one active tab, video only, about 8 seconds, and it stops on cancel, error, tab close, or completion. The recording is not stored in extension storage.
- Tab capture has not been manually verified on X or Instagram. A unit test cannot prove that a site allows capture.
- X page content is not extracted. X investigation waits for the official backend X API connector.
- Instagram page extraction is removed.
- YouTube is a click on "Compare this URL with the campaign". The extension reads the video id from the tab URL. It does not read the player, title, or thumbnail, and it does not retrieve audiovisual content. YouTube metadata itself is not connected.
- Opening the popup does not write a browsing history. Flag and watchlist entries are saved only when the analyst clicks those buttons, and only in this browser.
- The extension remains the primary UI. Campaign import and the coordination graph stay available in the dashboard.

### Direct media analysis

Backend tests cover image and video bytes, uncertain and no-face detector results, corrupt and unsupported files, oversized files, a detector exception, a failed database write, report retrieval, an unknown report id, and a report that remains after another startup. The tests use a stand-in detector. They do not download weights or use the GPU.

The dashboard upload and report screens stay disabled. `POST /api/media/analyze` for an X `post_id` and `media_key` is still not implemented.

### Remaining integration work

- The extension does not call the campaign X sync route yet. `POST /api/x/search` and `GET /api/x/posts/{post_id}` are still absent.
- A live X call has not been verified. `backend/scripts/x_recent_search_smoke.py` is manual and is not part of pytest.
- YouTube Data API context for one explicit video, without audiovisual download.
- Controlled retrieval of an X variant URL into a local file. The media job route already scores a file once that link exists.
- Investigation reports and `GET /api/investigations/{id}/graph`.
- Directional propagation graph from official repost, quote, and reply relationships.
- No X background monitoring in this phase.

## Final freeze

- [ ] Record one real X search response or the exact API error. Do not describe an unrun call as verified.
- [ ] Record one real single-video YouTube metadata response or the exact API error.
- [ ] Confirm no YouTube media file was downloaded.
- [ ] Confirm `.env` is untracked and the extension bundle has no bearer token or API key.
- [ ] Rehearse from the extension without a file upload.
