# Random Forest experiment

This is a second-stage classifier. DeepGuard still scores the frames. The production aggregation policy is unchanged, and these commands do not serve predictions from the API.

The V1 baseline is `aggregate_video_scores`: fake when at least two scores are at or above 0.8 and the median is at least 0.5. The forest is experimental model `deepfake_rf_v2`. Its class-vote fraction is not a calibrated probability. A validation-chosen low and high threshold turn that fraction into real, fake, or uncertain.

## Reproduce

Stop the API server first, then run both commands from the repository root with the project virtual environment:

```text
.venv\Scripts\python.exe backend/scripts/rf_extract_features.py --manifest backend/experiments/deepfake_rf/manifests/manifest.csv --output-dir backend/experiments/deepfake_rf/runs/extract

.venv\Scripts\python.exe backend/scripts/rf_train_evaluate.py --manifest backend/experiments/deepfake_rf/manifests/manifest.csv --extraction-dir backend/experiments/deepfake_rf/runs/extract --output-dir backend/experiments/deepfake_rf/runs/deepfake_rf_v2
```

The committed manifest contains only the zoo regression case. Training stops until locally licensed FaceForensics++ or DFDC rows are added. See `DATA_PROVENANCE.md`.

To write a C23 FaceForensics++ manifest from a local copy, without downloading or copying the videos:

```text
.venv\Scripts\python.exe backend/scripts/build_ffpp_manifest.py --dataset-root DIRECTORY --output backend/experiments/deepfake_rf/manifests/faceforensics_c23.csv
```

The command refuses to replace an existing output unless `--force` is given. It keeps the zoo row as `regression_only` and prints the real and fake counts. `manifests/faceforensics_c23.example.csv` shows the columns. It is not a training manifest.

Feature extraction loads the existing DeepGuard service once and refuses to start while port 8000 is open. `--allow-concurrent-gpu` overrides that check.

## Artifacts

A completed training directory contains `model.joblib`, `feature_schema.json`, `training_config.json`, `manifest_reference.json`, `evaluation_report.json`, `evaluation_report.md`, and `model_version.txt`. Run directories are gitignored.

No evaluation metrics are stored in the repository. A held-out figure from a future run describes that manifest only.
