> **Superseded.** This file is the original kickoff snapshot. Use `docs/INTEGRATION_CHECKLIST.md` at the repository root.

# Veritas AI — Integration Checklist

## Before coding

- [ ] Create the shared Git repository.
- [ ] Add `PROJECT_CONTEXT.md`, `docs/TEAM_WORK_SPLIT.md`, and this API contract.
- [ ] Agree file ownership and branch names.
- [ ] Read the API contract before asking Cursor to implement a module.
- [ ] Create a dedicated Python 3.11 environment on each GPU machine.

## First 60–90 minutes

### GPU member 1 — detector smoke test

- [ ] Run `nvidia-smi` and record GPU/driver details.
- [ ] Check whether the environment already has PyTorch and whether CUDA is visible.
- [ ] Install/test the selected detector in a dedicated environment only.
- [ ] Run one image inference and save its raw output.
- [ ] Confirm how the predictor behaves when no face is found.
- [ ] Record package versions and model/checkpoint identifier.

### GPU member 2 — video pipeline

- [ ] Verify FFmpeg is installed (`ffmpeg -version`).
- [ ] Build a video-to-sampled-frames utility without waiting for the detector.
- [ ] Preserve timestamps and cap sampling at 20 frames.
- [ ] Test on one short MP4.
- [ ] Agree the detector invocation interface with member 1.

### CPU member — graph and frontend

- [ ] Build the React/Vite shell and dashboard navigation.
- [ ] Implement CSV/JSON parsing and field validation.
- [ ] Create a 30–50 row synthetic demo dataset with explicit provenance labels.
- [ ] Implement graph construction with explainable edge signals.
- [ ] Render nodes/edges in Cytoscape.js using mock API responses.

## Integration gates

### Gate 1 — after 2 hours

- [ ] Detector smoke test is successful, or a fallback model decision is recorded.
- [ ] Video extraction produces timestamped frames.
- [ ] Frontend starts and displays mock investigation data.
- [ ] Graph engine imports and validates sample records.

### Gate 2 — after 6–8 hours

- [ ] Image analysis endpoint returns the agreed schema.
- [ ] Video analysis returns frame-level findings or explicit unsupported results.
- [ ] Campaign import and graph endpoints return the agreed schemas.
- [ ] Frontend is connected to at least one live backend route.

### Gate 3 — after 12–14 hours

- [ ] One complete investigation can be run from the UI.
- [ ] Report is generated only from stored analysis and graph results.
- [ ] No mock prediction remains in the live demo path.

### Final freeze

- [ ] Test one known real sample and one known manipulated sample where possible.
- [ ] Test no-face and unsupported media.
- [ ] Test malformed CSV and missing fields.
- [ ] Test empty/isolated graph and a seeded coordination pattern.
- [ ] Confirm demo data is labelled accurately.
- [ ] Rehearse with the actual machine and network conditions.
- [ ] Freeze feature work; accept only critical bug fixes.
