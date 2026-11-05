# Veritas AI frontend

React dashboard with four views: overview, media investigation, campaign analysis and investigation report.

## Run it

```bash
npm install
npm run dev
```

The app opens at http://localhost:5173. Run the tests with `npm test`.

## Browser extension

The Chrome/Chromium extension is in `extension/`. See [its README](extension/README.md) for setup and API contracts. Build it with `npm run build:extension`.

## Mock mode and the real backend

Mock mode is on by default for campaign screens, and a yellow banner shows while it's on. In that mode a campaign file isn't read and the graph is a labeled sample. Media analysis and investigation reports are disabled in every mode. They do not show a sample score or a sample report.

To use the real backend, create `.env.local` containing the line below and restart the dev server. API calls go to the FastAPI app on `localhost:8000`.

```text
VITE_USE_MOCKS=false
```

All API calls are in `src/services/api.js`.

## Response formats to confirm with the team

These are assumptions until the first integration checkpoint. The field names come from `TEAM_WORK_SPLIT.md` where it gives them.

| Endpoint | Owner | Fields the UI adds or assumes |
|---|---|---|
| `POST /api/analyze/image` | Backend test route | The media page stays disabled and does not call this route. |
| `POST /api/analyze/video` | Backend test route | The media page stays disabled and does not call this route. |
| `POST /api/campaigns/import` | Member 3 (built) | Multipart fields `file`, `source_type`; returns the campaign, including `campaign_id` |
| `GET /api/campaigns/{id}` | Member 3 (built) | `provenance`, `source_file`, `import_summary` (`total_records`, `accepted`, `rejected`, `errors[{row, message}]`, `platforms`), `posts` |
| `GET /api/campaigns/{id}/graph` | Member 3 (built) | Account nodes (`id`, `label`, `account_id`, `platform`, `cluster_id`, `post_count`); edges (`id`, `source`, `target`, `signals[{type, evidence, post_ids, post_pair_count}]`); `clusters[{cluster_id, account_ids, signals, summary}]`; `algorithm`, `limitations`, `provenance`, `import_summary` |
| `GET /api/reports/{id}` | Backend test route | The reports page stays disabled and does not call this route. |
| `GET /api/overview` | Not registered | The overview reads `GET /api/campaigns` only. Media and investigation counts stay "Not connected". |

Errors should return a non-2xx status with a JSON `detail` or `error` string.
