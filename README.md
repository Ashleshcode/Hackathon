# Veritas AI

Veritas AI is a Chrome extension. An analyst searches recent X posts through the official X API v2 and can explicitly investigate the YouTube video currently open. The local backend retrieves permitted metadata, creates an analysis job only for X media whose variant URL the X API returned, and builds an explainable graph.

The product is not an upload website. The extension does not scrape `x.com` or YouTube, does not use `tabCapture`, and does not analyse YouTube audiovisual content.

## Current state

`POST /api/campaigns/{campaign_id}/sync/x` calls official X recent search when `X_BEARER_TOKEN` is set. Automated tests mock that call. No live X API call has been verified from this repository, and YouTube context is still not implemented. Recent search only covers the preceding seven days. The sync stores post metadata and explicit repost, quote, and reply relationships. It does not download media, score it, or run on a schedule.

The extension is not implemented. `extension/manifest.json` does not exist, so Chrome cannot load the extension yet. `extension/content/` and `extension/services/` are empty placeholders. `extension/shared/` and `extension/icons/` remain from the earlier layout.

The CUDA environment is unchanged:

- `D:\Hackathon\.venv`
- Python 3.11.7
- `torch==2.14.1+cu130`
- `torchvision==0.29.1+cu130`
- CUDA verified on the RTX 4060 Laptop GPU

Do not install into or upgrade global Python 3.13 `torch 2.6.0+cu124`. DeepGuard 1.1.1 remains installed only in `.venv` and was not modified by the media-analysis routes. See `DEVELOPMENT_STATUS.md`.

`POST /api/analyze/image`, `POST /api/analyze/video`, and `GET /api/reports/{report_id}` score bytes with the shared detector and store the job. They are a backend test interface. The dashboard does not upload files.

`POST /api/media/analyze` scores stored X media only when a local file has already been linked. It does not download a variant URL. Until that file exists, the job is `unavailable` and has no score.

A manual smoke test, which does call X and is not part of pytest, is `backend/scripts/x_recent_search_smoke.py`.

## Secrets

Copy `.env.example` to `.env` on the backend machine and fill in the values there. `.env` is gitignored.

- `X_BEARER_TOKEN` is used only by the backend X connector.
- `YOUTUBE_API_KEY` is used only by the backend YouTube connector.

Do not put either value in `extension/`, `frontend/`, a manifest, or a committed source file. The extension calls the local API only.

## Documentation

| Document | Purpose |
|---|---|
| `PROJECT_CONTEXT.md` | Product decision, X and YouTube boundaries |
| `docs/API_CONTRACTS.md` | Backend routes |
| `docs/TEAM_WORK_SPLIT.md` | Three-member ownership |
| `docs/INTEGRATION_CHECKLIST.md` | What has and has not been run |
| `DEVELOPMENT_STATUS.md` | Machine and CUDA record |

`TEAM_WORK_SPLIT.md` at the repository root matches `docs/TEAM_WORK_SPLIT.md`.

`veritas_ai_kickoff_pack/` is the original upload-first starter. Do not implement from it. `frontend/` is an unused leftover.

## Load the extension in Chrome

Use these steps after `extension/manifest.json` exists. They fail today because that file has not been created.

1. Open Google Chrome.
2. Go to `chrome://extensions`.
3. Turn on **Developer mode**.
4. Choose **Load unpacked**.
5. Select `D:\Hackathon\extension`.

When the manifest is added, the YouTube action must be user-initiated, and the manifest must not register a content script on `x.com` or request `tabCapture`.

## Layout

```text
Hackathon/
├── .env.example
├── README.md
├── PROJECT_CONTEXT.md
├── TEAM_WORK_SPLIT.md
├── DEVELOPMENT_STATUS.md
├── docs/
│   ├── API_CONTRACTS.md
│   ├── INTEGRATION_CHECKLIST.md
│   └── TEAM_WORK_SPLIT.md
├── extension/
│   ├── background/
│   ├── content/
│   ├── icons/
│   ├── popup/
│   ├── services/
│   ├── shared/
│   └── sidepanel/
├── backend/app/
│   ├── api/
│   ├── agents/
│   ├── connectors/
│   ├── database/
│   ├── intelligence/
│   ├── media/
│   ├── models/
│   └── schemas/
├── frontend/
└── .venv/
```

`extension/manifest.json` is intentionally absent until extension implementation starts.
