> **Superseded.** This file is the original kickoff snapshot. Use the repository-root `PROJECT_CONTEXT.md`. Veritas AI is a Chrome extension, not an upload website.

# Veritas AI — Project Context

## Problem statement

**DL-SJBIT-HK26-GOVP006 — AI-Driven Detection & Countermeasures Against Fake Social Media Content**

Build a hackathon prototype that accepts multi-format media and platform-labelled social-post data, detects possible synthetic/manipulated media, identifies suspicious dissemination patterns, and prepares evidence-based investigation summaries.

## Product objective

A human analyst should be able to complete one end-to-end workflow:

1. Upload an image or video for face-based manipulation analysis.
2. Import social-post records from multiple platform-labelled sources (CSV or JSON).
3. Identify related posts and accounts using explainable similarity/timing signals.
4. Explore the account/post/media relationships in an interactive graph.
5. Generate an investigation report from the actual media and graph outputs.

## Scope boundary for the 22-hour build

- Use a verified pretrained detector; do not train a detector from scratch.
- Initial detector scope is **face-focused image/video manipulation detection**. It is not a universal detector for every AI-generated image, voice, scene, or claim.
- Video is analysed using sampled frames and timestamps.
- Social data is imported from CSV/JSON and labelled by source platform. Do not claim unrestricted live access to X, Instagram, Facebook, or TikTok.
- Demo records must be labelled `synthetic_demo` or `curated_public_sample` as appropriate.
- Graph signals indicate patterns requiring review; they do not prove malicious intent or identify a person as a disinformation actor.
- The LLM/report component may explain structured evidence but must not invent evidence, sources, accounts, or model results.
- No automatic takedowns, public accusations, or autonomous moderation.

## Initial technology choices

- Frontend: React + Vite
- Backend: Python 3.11 + FastAPI
- ML: PyTorch + a verified pretrained model
- Media: OpenCV + FFmpeg
- Graph: NetworkX
- Graph visualization: Cytoscape.js
- Storage: SQLite for the hackathon prototype
- Similarity: perceptual hashing for images/media; TF-IDF or sentence embeddings for text, depending on time and install reliability

## Team ownership

See `docs/TEAM_WORK_SPLIT.md`. Keep file ownership separate and use feature branches. Shared contracts in `docs/API_CONTRACTS.md` are the integration source of truth.

## Definition of done

The MVP is done when a judge can, from the UI:

- upload an image and receive an actual detector result or an explicit inconclusive/unsupported result;
- upload a video and see sampled-frame timestamps and an aggregate assessment;
- import platform-labelled social posts;
- view a graph generated from imported records and inspect why edges exist;
- generate a report containing the actual detector and graph outputs;
- run the documented workflow without manually editing records or launching hidden scripts.

## Evidence and honesty rules

- Record model name, checkpoint/dataset variant, software version, and inference settings.
- Distinguish a raw model score from a calibrated probability.
- If the model has not been evaluated by this team on a test set, do not claim an accuracy for our system.
- Keep detector verdicts, coordination signals, and analyst conclusions as separate fields.
- Clearly disclose synthetic demo data and limitations in the UI and presentation.
