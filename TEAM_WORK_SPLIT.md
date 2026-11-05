# Veritas AI — Team Work Split

**Project:** AI-Driven Detection & Countermeasures Against Fake Social Media Content  
**Team size:** 3 members  
**Hackathon build window:** 22 hours  
**Working model:** One shared Git repository, separate feature branches, independently testable modules, and scheduled integration checkpoints.

---

## 1. Project objective

Build a working prototype that supports a human investigator through one end-to-end workflow:

1. Upload an image or video and analyse it for potential synthetic/manipulated media.
2. Import social-media post records from multiple platform-labelled sources using CSV or JSON.
3. identify related posts and suspicious coordination patterns using explainable signals.
4. Visualise the relationships between accounts, posts and media in an interactive graph.
5. Generate an investigation summary from the actual media-analysis and graph-analysis outputs.

### Scope boundary

This is a **hackathon prototype**, not a production-grade social-media monitoring service. The initial version will use uploaded media and permitted/demo post datasets. It will not claim unrestricted live access to X, Instagram, Facebook or TikTok. Demo records must be labelled as synthetic or curated, as applicable.

The application must distinguish between:

- **Media detector output:** a model's prediction or score for the media it analysed.
- **Coordination signal:** an observable relationship such as similar content or closely timed posting.
- **Investigator conclusion:** a human-reviewed assessment. The system must not automatically declare an account malicious or a claim false merely because a detector or graph signal is elevated.

---

## 2. Team allocation at a glance

| Member | Machine | Primary ownership | Secondary ownership |
|---|---|---|---|
| **Member 1 — ML & backend lead** | GPU machine 1 | Pretrained image deepfake inference; model adapter; media-analysis API; backend integration | Evidence aggregation, investigation report service, integration/testing |
| **Member 2 — Video & media processing lead** | GPU machine 2 | Video validation, frame extraction, frame-level inference pipeline and video aggregation | Optional audio analysis; media-processing tests |
| **Member 3 — Frontend & graph intelligence lead** | CPU-only machine | React dashboard; CSV/JSON ingestion; graph construction and coordination analysis | Demo dataset, graph visualisation, report presentation and UI testing |

### Hardware and runtime arrangement

- The two GPU machines are development and testing resources. They do **not** need to operate as a distributed GPU cluster.
- Member 1 owns the shared model-loading interface. In the integrated application, load the selected detector once and reuse it for image requests and sampled video frames. Avoid loading duplicate model copies into VRAM.
- Member 2 can develop and test the video pipeline on GPU machine 2 using a mock detector interface until the shared model adapter is ready.
- The final demo should run on one machine first. Choose the machine with the most reliable working environment and sufficient VRAM. A second machine is not a deployment requirement.
- The CPU-only member should use lightweight CPU-friendly methods for graph analysis (for example, hashing, TF-IDF/cosine similarity and NetworkX). No GPU model training is assigned to this member.

---

# 3. Member 1 — ML & Backend Lead (GPU machine 1)

## Primary objective

Deliver reliable **image deepfake inference** and own the backend integration point that connects media analysis, campaign analysis and the investigation report.

## Responsibilities

### A. Verify and integrate the pretrained detector — P0

1. Inspect the selected pretrained detector's current repository, installation instructions, licence and checkpoint availability.
2. Verify that the model can be installed in the team's Python environment and performs inference on at least one sample image.
3. Confirm the model's supported input type and scope. If it is face-focused, document that limitation; do not present it as a universal detector for all synthetic images.
4. Record the model name, checkpoint/source, version or commit where possible, input preprocessing, output interpretation and inference device.
5. Do not train a model from scratch during the hackathon.
6. Do not copy a paper's benchmark accuracy and present it as the team's result.

**Fallback:** If the preferred detector cannot be installed or its checkpoint cannot be obtained within the first 90 minutes, switch to a verified, readily available pretrained baseline. Do not spend the event debugging an unavailable checkpoint.

### B. Implement the shared detector adapter — P0

Create a stable interface that both image and video analysis can call.

Suggested file ownership:

```text
backend/app/models/deepfake_detector.py
backend/app/models/model_manager.py
backend/app/schemas/media.py
backend/app/api/media.py
backend/tests/test_image_analysis.py
```

Required behaviour:

- Accept a validated image or preprocessed face/frame input.
- Return the model's actual output, prediction label and score, with model metadata.
- Support `real`, `fake` or `uncertain` where the model/output policy permits it.
- Handle images with no detectable face as `inconclusive` or `unsupported`; never invent a score.
- Load model weights once per application process, not once per request or frame.
- Use GPU when available and a tested CPU fallback where practical.
- Handle invalid files, oversized files, corrupt images and inference errors cleanly.
- Preserve enough metadata to reproduce what model and settings produced a result.

### C. Own the media-analysis API — P0

Implement and maintain the image endpoint. Coordinate the request/response contract with Member 2 before either person finalises their module.

Suggested endpoint:

```http
POST /api/analyze/image
```

Illustrative response shape:

```json
{
  "analysis_id": "A001",
  "media_type": "image",
  "model": "model_identifier",
  "prediction": "uncertain",
  "score": null,
  "score_type": "model_output",
  "status": "completed",
  "limitations": []
}
```

The field names may be adjusted once, during the initial contract agreement. Do not let each module invent a different response format.

### D. Backend integration and investigation report service — P0/P1

- Own the FastAPI application entry point and final router registration in `main.py`.
- Integrate the image endpoint, Member 2's video-analysis function and Member 3's campaign/graph router.
- Create a deterministic investigation service that combines stored media-analysis results and graph-analysis results into one report object.
- Keep report generation evidence-grounded. An LLM explanation is optional and must not invent facts.
- Provide a basic report endpoint if time permits:

```http
GET /api/reports/{report_id}
```

### E. Testing and documentation — P0

- Add tests for valid image, invalid image, no-face image, model-loading failure and CPU/GPU device selection.
- Run at least a small real/fake sample check and save the results and caveats.
- Document setup, checkpoint retrieval, model licence/source, hardware and known limitations.

## Member 1 deliverables

- [ ] Selected pretrained detector verified with a successful local inference.
- [ ] Shared detector adapter and one-time model loader implemented.
- [ ] Working image-analysis API.
- [ ] Backend application starts and registers all team routers.
- [ ] Investigation report service combines real analysis outputs.
- [ ] Tests and model/source/limitations documentation committed.

## Member 1 must NOT take ownership of

- Video sampling and timestamp management (Member 2).
- CSV/JSON campaign import and graph UI (Member 3).
- Frontend page implementation (Member 3).

Member 1 owns integration contracts and `main.py`, but should not rewrite other members' modules without first coordinating with them.

---

# 4. Member 2 — Video & Media Processing Lead (GPU machine 2)

## Primary objective

Deliver a working **video-to-frame-analysis pipeline** that reuses the shared detector interface and produces traceable frame-level evidence.

## Responsibilities

### A. Video upload validation and preprocessing — P0

1. Accept common video formats supported by the installed FFmpeg/OpenCV environment (for example MP4).
2. Validate file type, file size, duration and readability.
3. Extract representative frames using a configurable sampling strategy.
4. Start with a maximum of 10–20 sampled frames per video to protect runtime and GPU memory.
5. Preserve each sampled frame's original timestamp.
6. Detect whether usable faces are present in each frame, where required by the selected detector.
7. Handle videos with no detectable faces or unreadable frames without crashing.

Suggested file ownership:

```text
backend/app/media/video_processor.py
backend/app/media/video_analyzer.py
backend/app/media/frame_sampling.py
backend/tests/test_video_processing.py
backend/tests/test_video_analysis.py
```

### B. Frame-level detector integration — P0

- Use the shared detector interface defined by Member 1.
- Do not create a separate, incompatible deepfake model implementation.
- While Member 1 is still integrating the detector, use a mock predictor with the same interface so video processing can proceed independently.
- In the integrated app, reuse the one loaded detector instance. Do not load another copy for every video or frame.
- Collect the per-frame model output, face-detection status, timestamp and any supported evidence.

### C. Video-level aggregation — P0

- Aggregate frame-level results into a video-level summary using a transparent, documented rule.
- Preserve the distribution of frame scores and the timestamps of notable frames.
- Do not declare a whole video fake based on one isolated high-scoring frame.
- Return `inconclusive` when too few usable frames/faces are available.
- Make clear that sampled-frame analysis is not a guarantee that every part of the video has been examined.

Suggested endpoint (Member 1 registers it in the main app; Member 2 supplies the processing service and router implementation if agreed):

```http
POST /api/analyze/video
```

Illustrative response shape:

```json
{
  "analysis_id": "V001",
  "media_type": "video",
  "frames_sampled": 20,
  "frames_with_faces": 14,
  "frame_results": [],
  "video_assessment": "inconclusive",
  "aggregation_method": "documented_method_name",
  "status": "completed",
  "limitations": []
}
```

### D. Optional audio analysis — P2 only

Only begin this after the complete video pipeline works end to end.

- Check whether an existing pretrained synthetic-speech detector is installable and usable within the available time.
- If successful, implement audio analysis as a separate component with its own result and limitations.
- Do not claim audio authenticity from transcription alone.
- Do not delay video integration to add audio analysis.

### E. Testing and documentation — P0

Test:

- Valid short video.
- Unsupported/corrupt video.
- Video with no detectable face.
- Video with fewer usable frames than expected.
- Correct frame timestamps.
- Successful inference reuse through the shared adapter.
- Reasonable processing time and memory use.

## Member 2 deliverables

- [ ] Working video validation and frame extraction.
- [ ] Configurable sampling capped initially at 10–20 frames.
- [ ] Timestamped frame-level inference using the shared detector interface.
- [ ] Transparent video-level aggregation and inconclusive handling.
- [ ] Tests and short usage documentation.
- [ ] Optional audio module only if all P0 work is complete.

## Member 2 must NOT take ownership of

- Selecting/loading a second production copy of the deepfake model (Member 1 owns the shared model adapter).
- Campaign graph construction or account-cluster scoring (Member 3).
- Frontend pages (Member 3).

---

# 5. Member 3 — Frontend & Graph Intelligence Lead (CPU-only machine)

## Primary objective

Deliver the **investigator-facing application** and the social-post ingestion/coordination-analysis pipeline. All assigned work must run on CPU.

## Responsibilities

### A. Social-post ingestion — P0

1. Support CSV and JSON imports.
2. Normalise platform-labelled post records into one internal schema.
3. Validate required and optional fields.
4. Reject malformed records with clear row-level error messages rather than failing the entire import.
5. Preserve source platform, post ID, account ID, timestamp, caption/text, URL and media reference/hash when supplied.
6. Make the import source clear: uploaded dataset, curated sample or synthetic demo data.

Suggested minimum post schema:

```json
{
  "post_id": "p001",
  "platform": "platform_a",
  "account_id": "account_01",
  "timestamp": "2026-11-05T10:00:00Z",
  "text": "Example post text",
  "url": "https://example.invalid/post/p001",
  "media_hash": "optional_hash",
  "media_reference": "optional_file_reference"
}
```

Use fictional account identifiers and safe example URLs in synthetic data. Do not imply that synthetic records came from actual social platforms.

### B. Explainable graph intelligence — P0

Suggested file ownership:

```text
backend/app/intelligence/post_ingestion.py
backend/app/intelligence/similarity.py
backend/app/intelligence/graph_engine.py
backend/app/api/campaigns.py
backend/tests/test_campaign_import.py
backend/tests/test_graph_engine.py
```

Implement a lightweight CPU-based analysis using available methods, such as:

- Exact or perceptual media-hash matches when hashes are present.
- TF-IDF/cosine similarity or another lightweight method for similar captions.
- Time-window comparisons for unusually close posting times.
- Shared URL/repost relationships when supplied.
- NetworkX graph construction and cluster/community analysis.

Every edge must include its reason/evidence (for example, `same_media_hash`, `similar_caption`, `close_posting_time` or `shared_url`). Keep individual signals visible. A combined score may be added, but its formula must be documented and must not be described as proof of malicious coordination.

### C. Campaign APIs — P0

Suggested endpoints:

```http
POST /api/campaigns/import
GET  /api/campaigns/{campaign_id}
GET  /api/campaigns/{campaign_id}/graph
```

Graph response should contain:

- Nodes representing accounts and/or posts (the chosen node model must be consistent).
- Edges representing observed relationships.
- Cluster identifiers where clusters are found.
- Coordination signals and their evidence.
- Import summary and data provenance.

Coordinate the final response format with Member 1 before implementation. Member 1 registers the router in the main FastAPI application.

### D. Frontend dashboard — P0

Suggested frontend file ownership:

```text
frontend/src/pages/OverviewPage.jsx
frontend/src/pages/MediaInvestigationPage.jsx
frontend/src/pages/CampaignAnalysisPage.jsx
frontend/src/pages/ReportPage.jsx
frontend/src/components/UploadPanel.jsx
frontend/src/components/DetectionResult.jsx
frontend/src/components/NetworkGraph.jsx
frontend/src/components/ReportSummary.jsx
frontend/src/services/api.js
```

Build these views:

1. **Overview:** counts of analysed media, imported posts, campaigns and investigations. Use actual backend data once integrated; use clearly labelled mock data during parallel development.
2. **Media investigation:** image/video upload, progress, detector result, confidence/score context, frame timestamps and limitations.
3. **Campaign analysis:** CSV/JSON import, source summary, post list and graph visualisation.
4. **Investigation report:** combined media and graph evidence, findings, limitations and recommended human-review actions.

Use Cytoscape.js or another lightweight graph visualisation library. The graph must be interactive enough to inspect nodes and edges. Clicking an edge or node should show the evidence supporting that relationship.

### E. Demo dataset — P0

Create a small dataset of approximately 30–50 fictional posts across at least two platform labels. Include:

- One deliberately coordinated-looking group with repeated media/captions and close timestamps.
- One group with similar subject matter but independent wording/timing, to test false positives.
- Ordinary unrelated posts.

Document exactly which patterns were planted. The dataset must be labelled `synthetic_demo_data`; it must never be presented as a real observed campaign.

### F. Testing and documentation — P0

- Test valid and malformed CSV/JSON imports.
- Test exact media-hash matches, similar captions and timestamp-based links.
- Test a non-coordinated group to ensure the engine does not connect every similar post.
- Test graph rendering with empty, small and larger graphs.
- Document the coordination signals and their limitations.

## Member 3 deliverables

- [ ] Working CSV/JSON social-post importer.
- [ ] Normalised post schema and import validation.
- [ ] CPU-based graph engine with evidence-backed edges.
- [ ] Synthetic demonstration dataset with documented planted patterns.
- [ ] Interactive campaign graph.
- [ ] Four usable application views: overview, media investigation, campaign analysis and report.
- [ ] Tests and documentation.

## Member 3 must NOT take ownership of

- Deepfake model inference or GPU model downloads.
- Video frame extraction or model aggregation.
- FastAPI application entry-point integration (`main.py` is owned by Member 1).

---

# 6. Shared API and integration contracts

Agree on these contracts before parallel implementation. The exact JSON field names may be adjusted once, at the first integration checkpoint, and then treated as stable.

| Function | Owner | Interface |
|---|---|---|
| Image analysis | Member 1 | `POST /api/analyze/image` |
| Video analysis | Member 2 service; integrated by Member 1 | `POST /api/analyze/video` |
| Campaign import | Member 3 | `POST /api/campaigns/import` |
| Campaign graph | Member 3 | `GET /api/campaigns/{id}/graph` |
| Investigation report | Member 1 service; Member 3 UI | `GET /api/reports/{id}` or equivalent agreed flow |

### Common response conventions

- Include a stable analysis/campaign/report ID.
- Include `status` and a useful error message where applicable.
- Include model or algorithm identifiers for derived outputs.
- Include data provenance: uploaded file, imported dataset, curated sample or synthetic demo.
- Use `null` or an explicit `inconclusive` status when there is insufficient evidence. Never fabricate a score to fill a field.
- Include limitations and supporting signals wherever a result might otherwise be misinterpreted.

### Shared data ownership

- Member 1 owns the top-level FastAPI app, configuration and router registration.
- Member 1 owns the detector interface and model lifecycle.
- Member 2 owns video-processing services and their tests.
- Member 3 owns campaign ingestion, graph services, campaign routes and frontend.
- Report data is assembled by Member 1 from outputs produced by the other modules; Member 3 owns how the report is displayed.
- Do not have two members edit the same file at the same time.

---

# 7. Git and Cursor working rules

## Branches

Use separate branches:

```text
main
feature/image-detector-api       # Member 1
feature/video-media-pipeline     # Member 2
feature/graph-and-frontend       # Member 3
```

If the team prefers separate branches for backend graph work and frontend work, Member 3 can use two branches, but only one person should own each file.

## Rules for Cursor Agent

Every member should:

1. Open the shared repository in Cursor and check out their assigned branch.
2. Ask Cursor to read `README.md`, `PROJECT_CONTEXT.md` and this work-split file before editing.
3. Give Cursor only the tasks and file paths assigned to that member.
4. Ask Cursor to inspect existing code before creating or changing files.
5. Require tests or a reproducible manual test for each feature.
6. Review generated code and run it; do not accept code just because Cursor says it is complete.
7. Commit small working changes frequently.
8. Open a pull request or coordinate a merge before changing shared interfaces.

Suggested commit style:

```text
feat: add image deepfake inference API
feat: add sampled video analysis
feat: add campaign graph engine
feat: add investigation dashboard
fix: handle videos without detectable faces
test: add campaign import validation
```

---

# 8. 22-hour execution checkpoints

| Elapsed time | Required checkpoint | If missed |
|---|---|---|
| **0–1.5 hours** | Repository, environments, API contracts; preferred detector successfully initialised on one GPU | Switch to a verified fallback detector. Do not keep debugging an unavailable checkpoint. |
| **1.5–5 hours** | Image inference proof; video-to-frames proof; graph engine proof; frontend skeleton | Use mock interfaces for modules waiting on another member. |
| **5–9 hours** | Image/video endpoints and campaign graph connected to the frontend | Stop optional features. Make the core workflow run end to end. |
| **9–13 hours** | Evidence-backed report and investigation workflow | Use a deterministic report template; LLM integration is not required. |
| **13–17 hours** | Tests, realistic sample inputs, error handling and graph false-positive checks | Fix broken P0 workflows before adding features. |
| **17–20 hours** | UI polish, documentation and optional deployment | Prefer reliable local execution over risky deployment changes. |
| **20–22 hours** | Feature freeze, demo rehearsal and backup recording | No new features. Only fix demo-blocking defects. |

---

# 9. Definition of done — team acceptance checklist

The project is ready to demonstrate when all P0 items below pass:

- [ ] The application starts using documented commands.
- [ ] An investigator can upload an image and obtain actual pretrained-model inference.
- [ ] An investigator can upload a video and obtain timestamped sampled-frame analysis.
- [ ] Videos/images without usable faces produce an honest inconclusive/unsupported result.
- [ ] Social-media post records can be imported from CSV or JSON.
- [ ] Imported records retain their platform labels and source information.
- [ ] The graph is built from imported records, not hard-coded graph output.
- [ ] At least one planted coordination pattern is detected and its supporting signals are visible.
- [ ] A non-coordinated example is included to demonstrate that similarity does not automatically mean coordination.
- [ ] The report combines actual detector and graph outputs.
- [ ] The complete workflow can be demonstrated without manually editing database records or results.
- [ ] Synthetic/curated data and model limitations are clearly disclosed.

## Explicitly out of scope unless all P0 work is complete

- Live scraping or unrestricted real-time monitoring of social-media platforms.
- Training a deepfake model from scratch.
- Training or hosting a large language model.
- A full multi-agent autonomous system; a controlled tool-calling investigation workflow is sufficient.
- Full audio deepfake detection.
- Automated content removal, account suspension or takedown actions.
- Production-scale cloud infrastructure.
- Claims that the prototype can determine truth or malicious intent with certainty.

---

# 10. Final ownership summary

| Member | Must personally hand over |
|---|---|
| **Member 1 — GPU 1** | Verified image detector, shared model adapter, image API, integrated FastAPI app, investigation report service and model documentation. |
| **Member 2 — GPU 2** | Video validation, sampled-frame extraction, timestamped frame inference, video aggregation, tests and limitations. |
| **Member 3 — CPU** | CSV/JSON ingestion, explainable graph engine, synthetic demo dataset, interactive React dashboard, campaign views and UI documentation. |

**Team principle:** Build the smallest complete investigation workflow first. Every additional feature is optional until the end-to-end P0 workflow works reliably.
