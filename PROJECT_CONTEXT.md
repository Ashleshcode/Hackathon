# Veritas AI — Project Context

## Problem statement

**DL-SJBIT-HK26-GOVP006 — AI-Driven Detection & Countermeasures Against Fake Social Media Content**

Build a hackathon prototype that helps a human analyst monitor selected social platforms for chosen topics, inspect attached images and videos for possible face-focused manipulation, see explainable relationships among the retrieved posts, and read an evidence-based investigation report.

## Product decision

Veritas AI is a **Chrome extension** for multi-platform social-media monitoring. The primary experience is a Manifest V3 extension with a popup and a side panel.

It is not a website where users upload videos or images for deepfake detection. Manual media upload is allowed only as an optional developer testing interface. It is not part of the product UI and must not be the demo path.

## Core user workflow

1. The analyst opens the extension.
2. The analyst selects social platforms and monitoring topics.
3. The extension asks the backend to retrieve matching posts through authorized platform APIs.
4. The backend analyses images and videos attached to those posts.
5. Graph intelligence identifies related posts and possible coordinated dissemination.
6. The extension displays alerts and investigation reports.

The extension talks to the local FastAPI backend. Platform credentials and official API calls stay in the backend. The extension must not scrape social-media pages.

## Initial platform connectors

These connectors are planned. None has been implemented or verified in this repository.

| Platform | Initial rule |
|---|---|
| Bluesky | Public API. First connector to build. |
| Mastodon | Public API of a configured instance. First connector to build. |
| X, Reddit, Instagram, Facebook | Official authorized APIs only. Do not scrape, replay session cookies, or automate a logged-in browser. |

Until a connector has been run successfully against the real API, its status is `not_implemented` or `not_verified`. Do not present sample records as live platform data.

## Scope boundary

- Use a verified pretrained detector. Do not train a detector from scratch.
- Detector scope is **face-focused image and video manipulation detection**. It is not a universal detector for every AI-generated image, voice, scene, or claim.
- Video is analysed with sampled frames and timestamps. Cap sampling at 20 frames for the MVP.
- Demo or fixture records must be labelled `synthetic_demo` or `curated_public_sample`.
- Graph signals are patterns that need review. They do not prove malicious intent or identify a person as a disinformation actor.
- Reports may summarize stored evidence. They must not invent posts, accounts, sources, or model results.
- No automatic takedowns, public accusations, or autonomous moderation.
- Do not claim a live integration, a model accuracy, or a successful Chrome load until that check has actually been run.

## Technology choices

- Product UI: Chrome Extension, Manifest V3, popup and side panel
- Backend: Python 3.11 and FastAPI
- Inference: PyTorch and a verified pretrained model
- Media: OpenCV and FFmpeg
- Graph: NetworkX, with an explainable view in the extension side panel
- Storage: SQLite on the local investigation machine
- Similarity: perceptual hashing for media, and TF-IDF or another lightweight text comparison

The empty `frontend/` directory is a leftover placeholder from the earlier website plan. It is not the product UI.

## Team ownership

See `docs/TEAM_WORK_SPLIT.md`. The copy at `TEAM_WORK_SPLIT.md` is the same document. Keep file ownership separate and use feature branches. `docs/API_CONTRACTS.md` is the integration source of truth.

The original upload-first kickoff remains in `veritas_ai_kickoff_pack/` for history. Do not implement from that pack.

## Definition of done

The MVP is done when an analyst can, from the extension:

- choose platforms and topics in the popup;
- request a refresh and see either posts retrieved by a connector the team has actually run, or an explicit `not_implemented` / `not_verified` status;
- open the side panel and inspect alerts for attached media;
- see a graph built from the stored posts and the evidence for each relationship;
- open a report assembled from stored media-analysis jobs and graph results;
- complete that workflow without uploading a file and without presenting fixture data as a live feed.

## Evidence and honesty rules

- Record model name, checkpoint or dataset variant, software version, and inference settings.
- Distinguish a raw model score from a calibrated probability.
- If this team has not evaluated the model on a test set, do not claim an accuracy for the system.
- Keep detector verdicts, coordination signals, and analyst conclusions as separate fields.
- Disclose fixture data, unsupported media, and unverified connectors in the extension and in the presentation.
