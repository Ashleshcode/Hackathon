# Veritas AI browser extension

A Manifest V3 extension for Chrome and Chromium-based browsers. It is a quick entry point: it helps an investigator decide whether a public post warrants investigation, then opens the Veritas dashboard for the deep review. It contains no detector of its own and never concludes that content is fake or that an account is malicious.

## Build and load

From the `frontend` folder:

```bash
npm run build:extension
```

1. Open `chrome://extensions` (or `edge://extensions`, `brave://extensions`).
2. Turn on **Developer mode**.
3. Click **Load unpacked** and choose `frontend/dist-extension`.

Rebuild and click the reload icon on the extension card after any change.

## Modes

- **Demo** (default): no network requests. Results are fictional samples labelled "Synthetic demo data", and they say nothing about the page being viewed. **Open Full Investigation** needs the mock dashboard on port 5173 (`npm run dev`).
- **Live**: compares one YouTube video URL with a campaign you pick. That compare does not read X or Instagram pages and does not call a media-analysis route. A separate button, **Analyse this video**, can record the visible tab. That action is described below and is independent of demo or live mode.

### Running Live mode

From the repository root, using the existing project virtual environment:

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --port 8000
```

From `frontend`:

```bash
VITE_USE_MOCKS=false npm run dev -- --port 5174
```

Import a campaign in that dashboard at http://localhost:5174/campaigns, then choose it under "Compare against" in the popup. Campaigns are stored in the backend SQLite file and remain after a restart.

## What it can access

- **Permissions:** `activeTab`, `storage`, `tabCapture`, and `offscreen`, plus host access to `http://localhost:8000` only. There is no `scripting` permission, no content script, and no access to browsing history, cookies, or the debugger.
- **Service worker:** `background.js` waits for the Analyse click, opens the offscreen document, and asks Chrome for a one-time stream id. It does not record by itself and it does not watch pages.
- **Sent only after clicking "Compare this URL with the campaign" on a YouTube watch, short, or embed URL:** `url`, `platform`, and null text, account, and timestamp. Page text and media are not sent. Requests omit credentials.
- **Not read:** X page content, Instagram pages, cookies, tokens, or browsing history. Opening the popup does not store the tab and does not start a recording.
- **Flag for Review and Add to Watchlist:** saved in this browser only. Nothing is sent to any platform.

## Analyse this video

Chrome 116 or newer. The popup explains the action before it starts: Veritas captures approximately 8 seconds of the currently visible browser tab and sends that recording to the configured Veritas backend.

1. The click is handled by the service worker. It creates `offscreen.html` with reason `USER_MEDIA` before it calls `chrome.tabCapture.getMediaStreamId` for the active tab.
2. The offscreen document calls `getUserMedia` with that stream id, `audio: false`, and records with `MediaRecorder` for about 8 seconds. The MIME type is the first supported WebM type.
3. The recording is posted as multipart field `file` to `POST /api/analyze/video`. No page URL is sent. The popup then shows the stored report: id, job status, media type, detector status, prediction, raw score, score semantics, warnings, and the video frame counts. **Reload stored report** calls `GET /api/reports/{report_id}`.
4. **Stop capture** ends the recording and discards it. Closing the recorded tab does the same. Closing the popup does not stop an active capture; the toolbar badge stays visible until it finishes.
5. Tracks are stopped and the offscreen document is closed when the operation ends. The video blob is dropped after upload or failure. It is not written to `chrome.storage`.

This analyses rendered frames from the tab, not the original platform video file. Audio deepfake analysis is not implemented. Chrome can refuse `chrome://` pages, DRM or protected playback, and some sites. A black or failed recording is reported as a failure, not as a detector result. This has not been manually verified on X or Instagram.

### Manual Chrome check

- Load `frontend/dist-extension` in Chrome 116 or newer and confirm the popup does not record when it opens.
- On an ordinary page with a playing video, click **Analyse this video**. Confirm the countdown, the badge after the popup closes, and that **Stop capture** discards the recording.
- Let one capture finish against a local backend. Confirm the popup shows the returned report id and detector fields, and that a raw score of 0.5 is shown as uncertain.
- Confirm a second click during capture does not start another recording.
- Confirm the backend is unreachable message when the API is stopped, and that no success is shown.
- Repeat on X and Instagram only as a manual check. Do not treat a unit test as proof that those sites can be captured.

## Page support

| Platform | Pages | Notes |
|---|---|---|
| X | None | Page content is not extracted. The popup does not call X. Backend campaign sync is a separate route and is not used here. |
| YouTube | `/watch`, `/shorts/`, `/embed/`, `youtu.be` | The analyst must click compare or Look up this video. Only the video id is taken from the URL. Look up asks the local backend for the public title and channel. Audiovisual content is not retrieved, and the listing does not change the face-score result. |
| Instagram | None | Page extraction has been removed. |
| Anything else | None | Offers "Open Veritas" and "Open campaigns". |

Platform page structures change without notice. When extraction fails, the popup reports that nothing was detected rather than guessing.

## Coordination check (built)

**Owner: Member 3.** `app/intelligence/post_check.py` and `app/api/campaigns.py`.

- `GET /api/campaigns` lists imported campaigns: `campaign_id`, `source_file`, `provenance`, `post_count`.
- `POST /api/campaigns/{id}/check-post` compares the post with that campaign using `build_graph`, so the signals, thresholds and evidence are the same as in the dashboard. It accepts `url`, `platform`, `post_text`, `account`, `timestamp` and an optional `media_hash`.

The response has `campaign_id`, `post_in_dataset`, `timestamp_known`, `coordination` (`status`, `related_post_count`, `signals[{type, evidence, post_ids, related_account}]`), `dataset`, `algorithm` and `limitations`.

Behaviour:

- The imported campaign is never changed. A new post goes into a separate copy, and the returned `campaign_id` opens that copy with the post highlighted in the graph.
- If the page's URL already appears in the campaign, that post is used, so it can't match itself.
- A missing or timezone-less timestamp stays unknown, so no timing signal can result. It is never replaced with a guessed time.
- The page post has no media hash, so `same_media_hash` can't fire yet. Caption, URL and timing are compared.

## Media analysis contract: `POST /api/extension/analyze`

**Not called.** `POST /api/extension/analyze` is not registered. The extension does not request it and does not treat a sample body as a detector result. Media in a live campaign result stays "not available". **Analyse this video** is a different action: it posts one recorded WebM file to `POST /api/analyze/video` and reads `GET /api/reports/{report_id}`. It does not send a page URL. The contract below remains the unimplemented extension-analyze shape, not the tab-capture request.

Request:

```json
{
  "url": "https://x.com/example/status/123",
  "platform": "x",
  "content_type": "mixed",
  "post_text": "Visible text or null",
  "account": "@example or null",
  "timestamp": "ISO 8601 or null",
  "media": [
    { "type": "image", "url": "https://..." },
    { "type": "video", "url": null, "poster_url": "https://... or null" }
  ]
}
```

Response:

```json
{
  "analysis_id": "E001",
  "report_id": "R1234 or null",
  "limitations": ["Plain text shown to the investigator"],
  "media": {
    "status": "completed",
    "media_type": "image",
    "risk_level": "high",
    "score": 0.87,
    "score_type": "model_output",
    "model": "model_identifier"
  }
}
```

Field rules (anything else is shown as a malformed response):

| Field | Allowed values |
|---|---|
| `media.status` | `completed`, `inconclusive`, `no_media`, `unsupported` (required) |
| `media.risk_level` | `high`, `medium`, `low` or `null`. Decided by the backend; the extension never derives it from the score. |
| `media.score` | A number from 0 to 1 or `null`. Never replace a missing score with 0. |
| `report_id` | The ID of an existing report, or `null`, which disables the report button |

Do not add a verdict field.

### Member 1 also needs to provide

- **Image analysis:** the request has image URLs, not files. The backend has to fetch them, or the team agrees another flow. Fetching URLs supplied by a client needs safeguards: http(s) only, no private or local addresses, and size and time limits.
- **`report_id`:** a report that combines this media result with the campaign in the coordination response.
- **Optional `media_hash`:** if the backend hashes fetched images the same way as the imported dataset, passing the hash to `check-post` enables `same_media_hash` matching.

### Member 2 needs to provide

- **Video analysis for extension requests:** X and YouTube video can't be forwarded as files, because `video.url` is usually `null`. Agree which videos can be fetched in a permitted way. Otherwise return `media.status: "unsupported"` or `"inconclusive"` with `score: null`, and direct the investigator to manual upload.
- **Mapping to `media`:** `video_assessment` and the aggregation result need to map onto these fields, including `risk_level` and a limitation stating that only sampled frames were analysed.
