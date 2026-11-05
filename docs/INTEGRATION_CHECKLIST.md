# Veritas AI — Integration Checklist

The product UI is the Chrome extension. Do not integrate a website upload flow into the demo. Manual upload remains the optional developer route in `docs/API_CONTRACTS.md`.

No item below is complete merely because a document names it. Check an item only after the command or screen has actually been run.

## Before feature coding

- [x] Shared Git repository exists.
- [x] Active docs are `PROJECT_CONTEXT.md`, `README.md`, `docs/API_CONTRACTS.md`, `docs/TEAM_WORK_SPLIT.md`, and this checklist.
- [ ] Team agrees the extension popup, side panel, and backend contracts before writing modules.
- [x] This machine has `D:\Hackathon\.venv` on Python 3.11.7.
- [x] `nvidia-smi` recorded an RTX 4060 Laptop GPU, driver 616.92, 8188 MiB.
- [x] `.venv` imports `torch==2.14.1+cu130` and `torchvision==0.29.1+cu130`, and `torch.cuda.is_available()` is true.
- [ ] DeepGuard is not installed yet. Install it only in `.venv`, and do not upgrade global Python 3.13 `torch 2.6.0+cu124`.
- [ ] FFmpeg is still missing from `PATH`.

## First build slice

### Member 1 — backend and connectors

- [ ] FastAPI starts from the documented command and `GET /health` matches the contract.
- [ ] SQLite stores monitors, normalized posts, media jobs, and reports.
- [ ] `GET /api/v1/platforms` reports Bluesky and Mastodon as `not_implemented` until a live call succeeds.
- [ ] Creating a monitor does not fabricate posts.
- [ ] Refresh returns a per-platform `fetch_status`. Skipped connectors add zero posts.
- [ ] X, Reddit, Instagram, and Facebook cannot be fetched by scraping.

### Member 2 — media jobs

- [ ] A media job can be queued from a stored `media_id`.
- [ ] Video sampling preserves timestamps and stops at 20 frames.
- [ ] Unsupported or no-face media returns `unsupported` or `uncertain` and a null score.
- [ ] The developer upload route works only under `/api/v1/dev/` and is not called by the extension.

### Member 3 — extension and graph

- [ ] Manifest V3 extension loads unpacked from the folder that contains `manifest.json`.
- [ ] Popup collects platforms and topics and calls the monitor API.
- [ ] Side panel shows alerts, stored posts, graph evidence, and a report.
- [ ] Graph edges come from stored normalized posts and include their signal evidence.
- [ ] Empty monitors render an empty state instead of mock live posts.

## Integration gates

### Gate 1

- [ ] Extension shell opens, or the missing-manifest reason is still the recorded blocker.
- [ ] Monitor create and refresh return the contract without invented posts.
- [ ] One media job returns a real detector result, or the recorded installation error.
- [ ] Graph code accepts fixture posts labelled `synthetic_demo`.

### Gate 2

- [ ] Popup refresh displays the backend's real platform statuses.
- [ ] At least one connector is `verified` with a recorded request, or it remains explicitly unverified.
- [ ] Side panel can open a stored alert and its media-job result.
- [ ] Graph view explains one edge from stored posts.

### Gate 3

- [ ] One investigation runs from the extension without a file upload.
- [ ] The report contains only stored media and graph outputs.
- [ ] Fixture data is visibly labelled and is not presented as a live platform feed.

## Final freeze

- [ ] Test a connector success and a connector failure without filling either with sample posts.
- [ ] Test no-face and unsupported media.
- [ ] Test an empty monitor and a fixture monitor with one planted relationship.
- [ ] Confirm the extension does not expose the developer upload control.
- [ ] Rehearse on this machine. Freeze features and fix only demo blockers.
