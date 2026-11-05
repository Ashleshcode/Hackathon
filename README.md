# Veritas AI

Veritas AI is a Chrome extension for monitoring selected social platforms. An analyst chooses platforms and topics in the extension. The local backend retrieves matching posts through authorized platform APIs, analyses attached images and videos, builds an explainable dissemination graph, and returns alerts and investigation reports.

The product is not a website where people upload media. File upload exists only as a future developer test under `/api/v1/dev/`. The extension must not use it.

## Current state

The extension is not implemented. `extension/` contains empty folders and no `manifest.json`, so Chrome cannot load it yet.

Bluesky and Mastodon are the planned first connectors. They have not been called from this repository. X, Reddit, Instagram, and Facebook are limited to official authorized APIs and are not implemented. Nothing here should be described as a live integration.

The local CUDA environment is already set up and should be left in place:

- `D:\Hackathon\.venv`
- Python 3.11.7
- `torch==2.14.1+cu130`
- `torchvision==0.29.1+cu130`
- CUDA verified on the RTX 4060 Laptop GPU

Do not install into, upgrade, or remove the global Python 3.13 PyTorch install. DeepGuard and model checkpoints are not installed. See `DEVELOPMENT_STATUS.md`.

## Documentation

| Document | Purpose |
|---|---|
| `PROJECT_CONTEXT.md` | Product decision, workflow, and scope |
| `docs/API_CONTRACTS.md` | Backend contracts |
| `docs/TEAM_WORK_SPLIT.md` | Three-member ownership |
| `docs/INTEGRATION_CHECKLIST.md` | Integration gates |
| `DEVELOPMENT_STATUS.md` | What has actually been run on this machine |

`TEAM_WORK_SPLIT.md` at the repository root is the same split as `docs/TEAM_WORK_SPLIT.md`.

`veritas_ai_kickoff_pack/` is the original upload-first starter. It is not the current specification.

`frontend/` is an empty leftover from that starter. Do not build the product there.

## Load the extension in Chrome

Use these steps after `extension/manifest.json` exists. They will fail today because that file has not been created.

1. Open Google Chrome.
2. Go to `chrome://extensions`.
3. Turn on **Developer mode**.
4. Choose **Load unpacked**.
5. Select the `D:\Hackathon\extension` directory, which is the directory that will contain `manifest.json`.

The extension is Manifest V3. The planned screens are the popup, for choosing platforms and topics, and the side panel, for alerts, posts, graph evidence, and reports. The backend is local FastAPI. The extension must not scrape social-media sites.

## Layout

```text
Hackathon/
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
│   ├── icons/
│   ├── popup/
│   ├── shared/
│   └── sidepanel/
├── backend/
├── frontend/
└── .venv/
```
