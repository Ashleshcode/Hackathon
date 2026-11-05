# Dataset provenance

The extraction script does not download videos. Add locally obtained files to `manifests/manifest.csv`.

## Required columns

`video_id`, `file_path`, `label` (`real` or `fake`), `dataset_name`, `source_group_id`, `capture_condition`, `notes`.

`source_group_id` keeps related videos on one side of every split. For FaceForensics++ it is the connected component of every original sequence that appears together in a manipulated filename. A `usage` column is optional. `regression_only` in that column, `usage=regression_only` in the notes, or dataset name `real_world_regression` marks a regression case.

A regression case is scored after the model and thresholds are frozen. It is not used to fit the forest, choose hyperparameters, or choose thresholds, and it is not included in the held-out metric table.

## Me at the zoo

`zoo_jawed_ma_5634abfcde7d` is the known-authentic Jawed Karim recording captured from a browser tab. The file is `backend/data/media/ma_5634abfcde7d.webm`. It is gitignored. Its sha256 is `1c7bdef9bc4e506a614a3f78cdce7d1b29146200030ee33c2012837df605516e`. The committed manifest lists it only as a regression case.

## FaceForensics++

FaceForensics++ is a research dataset. Obtain it under its licence and keep the videos outside this repository. The manifest builder reads a local `original_sequences/youtube/c23/videos` folder and the C23 videos for Deepfakes, Face2Face, FaceSwap, and NeuralTextures. It does not download them.

A manipulated filename is `target_source.mp4`, the same order as the published split pairs. That file involves two original sequences. Deepfakes and FaceSwap show the source identity on the target sequence. Face2Face and NeuralTextures reenact the source onto the target. Grouping only by the target would let the source original fall in another split.

The builder links every original id that appears together, including indirect chains, and stores that connected component in `source_group_id`. A missing original is reported and the manipulated file is left out. An ambiguous filename stops the build. The published train, validation, and test lists are recorded when present, but they are not followed when they would separate connected identities. `dataset_name` is `faceforensics++`. `usage` is `trainable` for these rows. The zoo row stays `regression_only`.

## DFDC

The Deepfake Detection Challenge dataset is distributed by Meta under its own terms of use. Obtain it separately. Do not commit the videos. Suggested `dataset_name`: `dfdc`. Use the dataset's original-video identity as `source_group_id` so an original and its fakes stay in the same split. Record the terms of use in `notes`.

## What this manifest is not

`backend/data/synthetic_demo_data.csv` is fictional campaign text. A `dataset_name` beginning with `synthetic` is rejected. The four DeepGuard demonstration files are filename-labelled samples, not an evaluation set, and they are not included here.
