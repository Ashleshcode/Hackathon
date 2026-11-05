> **Superseded.** This file is the original kickoff snapshot. Use the repository-root `README.md`, `PROJECT_CONTEXT.md`, and `docs/`. Veritas AI is a Chrome extension, not an upload website.

# Veritas AI — Start Here

## 0. Add the kickoff files

Copy this starter pack into the root of the shared repository. The repository should contain:

```text
veritas-ai/
├── .gitignore
├── PROJECT_CONTEXT.md
└── docs/
    ├── API_CONTRACTS.md
    ├── INTEGRATION_CHECKLIST.md
    └── TEAM_WORK_SPLIT.md
```

Commit this baseline before parallel implementation begins.

## 1. Branches

Each member clones the same repository and creates their assigned branch:

- Member 1: `feature/ml-image-api`
- Member 2: `feature/video-media`
- Member 3: `feature/graph-frontend`

Do not work directly on `main`. Merge through pull requests or reviewed merges.

## 2. Common Cursor instruction

Paste this into Cursor Agent at the beginning of each member's session, replacing the role:

> Read `PROJECT_CONTEXT.md`, `docs/TEAM_WORK_SPLIT.md`, and `docs/API_CONTRACTS.md` completely. You are responsible only for: [INSERT ASSIGNED ROLE]. First inspect the repository and list the files you plan to create or modify. Do not change shared API contracts or another member's owned files. Implement the smallest working version first, add tests, and report exactly which commands you ran and which parts remain incomplete. Do not invent model results or use mock outputs in the final live-demo path.

## 3. First parallel tasks

### Member 1 — GPU 1

1. Create a dedicated Python 3.11 virtual environment.
2. Run `nvidia-smi`.
3. Check whether PyTorch is installed and whether `torch.cuda.is_available()` is true.
4. Install and smoke-test the selected pretrained detector in this isolated environment.
5. Return one successful image inference result or the full installation/runtime error.

### Member 2 — GPU 2

1. Verify `ffmpeg -version`.
2. Build video validation and timestamped frame extraction (maximum 20 frames).
3. Test on a short local MP4.
4. Do not load another copy of the detector until Member 1 confirms the model interface and resource cost.

### Member 3 — CPU

1. Scaffold React + Vite dashboard.
2. Implement CSV/JSON parsing and validation against `API_CONTRACTS.md`.
3. Implement NetworkX graph construction and transparent edge signals.
4. Render the graph using Cytoscape.js with mock data while backend routes are being built.

## 4. Integration rule

API contracts are the source of truth. If a code implementation needs a different field or endpoint, propose the change in the team chat and update `docs/API_CONTRACTS.md` before changing both sides.
