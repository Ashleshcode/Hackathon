# Veritas AI — Project Context

## Problem statement

**DL-SJBIT-HK26-GOVP006 — AI-Driven Detection & Countermeasures Against Fake Social Media Content**

Build a hackathon prototype that helps a human analyst investigate posts on X and, when they explicitly ask, place one YouTube video in the context of permitted external references. The analyst inspects face-focused media findings where the platform API allows the media to be retrieved, sees explainable relationships, and reads an evidence-based investigation.

## Product decision

Veritas AI is a **Chrome extension**. The primary experience is a Manifest V3 extension with a popup and a side panel.

It is not a website where users upload videos or images. Manual upload remains an optional developer test only. It is not the product UI and must not be the demo path.

## Platform priorities

These connectors are specified and **not verified**. No live X or YouTube call has been made from this repository.

| Priority | Platform | Role |
|---|---|---|
| 1 | X | Primary full integration through the official X API v2. |
| 2 | YouTube | Contextual reference only, through the official YouTube Data API, for one video the user explicitly submits. |

Bluesky and Mastodon are not part of this finalized scope. Reddit, Instagram, and Facebook are not part of it either.

### X

The backend uses the official X API v2 for:

- recent post search
- post lookup
- author and timestamp retrieval
- repost, quote, and reply relationships
- video media metadata
- video variant URL resolution when the API response and the applicable developer terms include a permitted variant
- creation of a video or image analysis job for that permitted media

The extension must not scrape `x.com`. It must not use a content script to read an X feed, timeline, or page. X credentials stay in the backend environment.

### YouTube

The extension may read the current YouTube video URL only after the user explicitly requests an investigation. It extracts that video's ID and asks the backend for permitted metadata for that single video. The backend may search permitted X records for references to that URL and show those references in a graph.

YouTube restrictions:

- Do not download or scrape YouTube audiovisual content.
- Do not use `tabCapture`, screen capture, or stream ripping as a workaround.
- Do not aggregate YouTube Data API results across unrelated content owners. One user-submitted video ID per context request.
- Do not claim the video's audiovisual content has been deepfake-analysed.
- Keep the lookup user-initiated.
- Do not store browsing history. Persisting the one video ID the user submitted as part of an investigation is allowed. Persisting other tabs, searches, or watch history is not.

## Core user workflow

1. The analyst opens the extension.
2. For X, the analyst submits a recent-search query. The backend calls X API v2 and returns posts, authors, timestamps, relationship types, and media metadata.
3. The analyst can open one post. The backend performs an official post lookup.
4. If X API v2 returned a permitted video variant, the analyst can create a media-analysis job. If it did not, the job is unavailable and no webpage scrape fills the gap.
5. For YouTube, the analyst explicitly requests an investigation of the current watch page. The extension sends that video ID only. The backend returns metadata and any permitted X references. It does not analyse the YouTube audiovisual stream.
6. The side panel shows the investigation and an explainable graph.

The extension calls the local FastAPI backend only. It never contains `X_BEARER_TOKEN` or `YOUTUBE_API_KEY`.

## Scope boundary

- Use a verified pretrained detector later. Do not train one from scratch. Do not implement the model in this architecture pass.
- Detector scope is face-focused image and video analysis. It is not a universal detector for every synthetic image, voice, scene, or claim.
- Video sampling, when a permitted file is available, keeps timestamps and stops at 20 frames.
- A missing or unreadable face is `unsupported` or `uncertain`, with a null score.
- Graph edges from reposts, quotes, and replies are official relationship records. Any additional similarity edge must include its evidence. None of these prove malicious intent.
- The code integrated from Member 3 is a separate account-similarity coordination graph. It uses exact imported media hashes, TF-IDF caption similarity, shared URLs, and close posting times only as support for an edge that already shares content. It does not store X repost, quote, or reply direction. That directional propagation graph is still a future task on `GET /api/investigations/{id}/graph`.
- Campaign records, posts, and coordination-graph edges are stored in `backend/data/veritas.db`. Restarting the API keeps those rows. This is not persistent background monitoring.
- Reports may summarize stored evidence only.
- No automatic takedowns, public accusations, or autonomous moderation.
- Do not claim a live integration, a model accuracy, or a successful Chrome load until that check has actually been run.
- Fixture records, if used, are labelled `synthetic_demo` or `curated_public_sample` and are not labelled as live API data.

## Technology choices

- Product UI: Chrome Extension, Manifest V3, popup, side panel, and a YouTube-only explicit action
- Backend: Python 3.11 and FastAPI
- Platform access: official X API v2 and official YouTube Data API v3
- Inference, later: PyTorch and a verified pretrained model
- Media, for permitted X media only: OpenCV and FFmpeg
- Graph: NetworkX, shown in the side panel
- Storage: SQLite for investigations the user created
- Secrets: backend `.env` only, with placeholders in `.env.example`

`frontend/extension/` is the one extension source. Do not copy it into the root `extension/` tree. The root `extension/` folders are still empty placeholders for the side panel and the explicit YouTube action.

`frontend/src/` is the investigation dashboard that reads the coordination graph. It is not a second extension, and its upload panels are a developer test, not the product path. The popup must not scrape `x.com`. Member 3's current popup injects a page reader into the active tab, including an individual X post. That behavior is retained from the imported source and is not yet aligned with the rule against reading X pages.

## Team ownership

See `docs/TEAM_WORK_SPLIT.md`. The root `TEAM_WORK_SPLIT.md` is the same document. `docs/API_CONTRACTS.md` is the integration source of truth.

`veritas_ai_kickoff_pack/` is the original upload-first starter. Do not implement from it.

## Definition of done

The MVP is done when an analyst can, from the extension:

- run an X recent search and open one post through the backend, or see an explicit unverified or error status;
- see author, timestamp, and repost, quote, or reply relationships that the official payload actually contained;
- create an analysis job only for X media whose permitted variant was resolved, and see an honest unavailable state otherwise;
- explicitly investigate one current YouTube video and see metadata plus external X references, without a claim that the YouTube audiovisual stream was analysed;
- open the investigation and a graph built from those stored records;
- do all of this without uploading a file, scraping `x.com`, downloading YouTube media, or storing browsing history.

## Evidence and honesty rules

- Record the API name, endpoint, retrieval time, model name, checkpoint, and inference settings for any derived result.
- Distinguish a raw model score from a calibrated probability.
- If this team has not evaluated the model, do not claim an accuracy.
- Keep detector verdicts, official relationship records, similarity signals, and analyst conclusions separate.
- A YouTube context result must say that audiovisual analysis was not performed.
