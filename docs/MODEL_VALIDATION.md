# DeepGuard validation

Run on 2026-11-05 with `D:\Hackathon\.venv\Scripts\python.exe`. No FastAPI app, extension code, or X integration code was changed. Global Python was not modified. After this run, global Python 3.13 still reports `torch 2.6.0+cu124` and CUDA available.

This is one machine check on four upstream demonstration files. It is not a measured accuracy for Veritas AI.

## Environment

| Item | Recorded value |
|---|---|
| Python | 3.11.7 |
| torch before and after install | `2.14.1+cu130` |
| torchvision before and after install | `0.29.1+cu130` |
| CUDA before install | Available on NVIDIA GeForce RTX 4060 Laptop GPU |
| CUDA after install and during inference | Available, device `cuda:0`, same GPU |
| deepguard | `1.1.1` |
| pip check | Exit 0, `No broken requirements found.` |
| GPU memory reported by PyTorch | 8187.5 MiB |

The install command was `python -m pip install deepguard==1.1.1` with no `--upgrade`. A dry run immediately before it kept the CUDA builds as already satisfied. The completed install did not list `torch` or `torchvision` among the packages it installed.

## OpenCV collision

`deepguard` depends on `opencv-python>=5.0.0.93`. `albumentations==2.0.8` depends on `opencv-python-headless>=4.9.0.80`. Both were installed:

- `opencv-python==5.0.0.93`
- `opencv-python-headless==5.0.0.93`

Pip did not report a conflict. `import cv2` succeeds and reports `5.0.0` from `D:\Hackathon\.venv\Lib\site-packages\cv2\__init__.py`. In the install transaction, `opencv-python-headless` was listed before `opencv-python`, so the full `opencv-python` files are the later copy in that transaction. Both distributions still own the `cv2` namespace. This collision is not resolved.

`cv2` opened the official MP4 files through the bundled `opencv_videoio_ffmpeg500_64.dll`. The system `ffmpeg` command is still absent from `PATH`.

## Model

| Item | Value |
|---|---|
| Package | `deepguard==1.1.1` |
| Architecture name passed to the predictor | `ms_eff_gcvit_b0` |
| Dataset argument | `ff++` |
| Checkpoint URL used by the installed code | `https://github.com/HanMoonSub/DeepGuard/releases/download/v0.1.0/ms_eff_gcvit_b0_ff++.bin` |
| Checkpoint file | `C:\Users\ashle\.cache\torch\hub\checkpoints\ms_eff_gcvit_b0_ff++.bin` |
| Checkpoint size | 36,642,117 bytes |
| Face detector weights | `https://github.com/HanMoonSub/DeepGuard/releases/download/v0.1.0/yolov8n-face.pt` |
| Face detector file | `C:\Users\ashle\.cache\torch\hub\checkpoints\yolov8n-face.pt`, 6,389,512 bytes |
| Input size selected for `b0` | 224 by 224 |
| Output | `torch.sigmoid` of the model output. The upstream tutorials call this a deepfake probability. It is not a calibrated probability. |

The installed `ImagePredictor.__init__` signature matches the requested call: `margin_ratio`, `conf_thres`, `min_face_ratio`, `model_name`, `dataset`. Inference is `predict_img(img_path, tta_hflip=0.0) -> float`.

`VideoPredictor` uses the same constructor. Inference is `predict_video(video_path, num_frames=20, agg_mode="conf", tta_hflip=0.0)`. The default `conf` aggregation uses internal thresholds 0.8 and 0.2. The installed annotation says the return type is `np.ndarray`; these two calls returned a NumPy `float32`.

`predict_img` returns `0.5` when the image cannot be read, no face is found, the crop fails, or another exception is caught. That `0.5` is not marked as an error. The same fallback exists in `predict_video` when no scored frames are produced.

## Initialization and CUDA

The image predictor was created first. Its repr was:

```text
ImagePredictor(model_name='ms_eff_gcvit_b0', device='cuda:0', img_size=[224, 224])
```

Initialization took 39.352 seconds, including the checkpoint download. After load, PyTorch reported 34.81 MiB allocated and 54.0 MiB reserved.

The image predictor was deleted and the cache was emptied before the video predictor was created. They were not initialized together. After the delete, 43.70 MiB remained allocated and 70.0 MiB reserved, so the release was not complete. The video predictor then initialized in 0.761 seconds because the checkpoint was already cached. Its repr reported `device='cuda:0'`.

## Inference samples

The files are the western demonstration samples committed in `HanMoonSub/DeepGuard` under `docs/samples`. The real or fake distinction below is the filename label in that repository. It was not re-labelled by this team, and these four files are not an evaluation set.

| File | Filename label | Faces found | Public score | Time |
|---|---|---|---|---|
| `western_real_1.JPG` | authentic | yes | 0.0015687713166698813 | 0.719 s |
| `western_fake_1.JPG` | manipulated | yes | 0.8050177693367004 | 0.042 s |
| `western_real.mp4` | authentic | 20 face crops from the sampled frames | 0.07057248800992966 | 0.444 s |
| `western_fake.mp4` | manipulated | 20 face crops from the sampled frames | 0.9838078618049622 | 0.499 s |

`western_real.mp4` has 335 container frames at 30 fps. `western_fake.mp4` has 422 container frames at 30 fps. Both calls requested 20 sample frames. A separate preprocess pass, using the same loaded video predictor, kept 20 face crops for each file. `predict_video` then ran its own preprocess again. No call hit the `0.5` failure fallback.

On these four filename-labelled files, the authentic samples scored lower than the manipulated samples. That is the observed output. It is not an accuracy claim.

## VRAM

PyTorch figures during this process:

| Point | Allocated MiB | Reserved MiB | Peak allocated MiB | Free MiB |
|---|---|---|---|---|
| Before the image model | 0.00 | 0.00 | 0.00 | 7106.0 |
| After image initialization | 34.81 | 54.0 | 34.81 | 7052.0 |
| After both images | 78.66 | 124.0 | 97.99 | 6956.0 |
| After deleting the image predictor | 43.70 | 70.0 | 43.70 | 7010.0 |
| After video initialization | 73.54 | 92.0 | 73.54 | 6988.0 |
| After both videos | 85.37 | 712.0 | 331.2 | 6368.0 |

Total memory reported by PyTorch was 8187.5 MiB. The highest peak allocation in this run was 331.2 MiB, during video inference. Reserved memory rose to 712.0 MiB after the videos.

## Known limitations

- The detector is face-focused. A missing face becomes a silent `0.5` from the public predictor, not an explicit unsupported status.
- The sigmoid score is not a calibrated probability.
- The FaceForensics++ checkpoint URL packaged for `ms_eff_gcvit_b0` points at the `v0.1.0` GitHub release, not a `v1.1.1` asset.
- Hugging Face emitted an unauthenticated-download warning while timm fetched the EfficientNet backbone. No `HF_TOKEN` was set.
- Both OpenCV distributions remain installed.
- Image and video predictors each construct their own model and their own YOLO face detector. Running them at the same time would load a second copy. This run did not do that.
- Deleting the image predictor did not return allocated memory to zero.
- System FFmpeg is still not on `PATH`.
- No FastAPI route or extension calls this model yet.

## Shared wrapper

`backend/app/models/deepfake_detector.py` is the production-facing service. It does not call `ImagePredictor.predict_img` or construct `VideoPredictor`.

Inspection of the installed package showed that those public methods are the source of the ambiguous `0.5`. The reusable pieces are safe to call directly:

- `FaceDetector.detect_batch` returns an empty box when no face passes the confidence and minimum-size checks.
- `ImagePredictor._crop_face` returns `None` when the crop is empty or fails, instead of hiding that failure inside `0.5`.
- `deepguard.data.get_test_transforms` builds the same 224-pixel test tensor used by the predictor.
- `ImagePredictor.model` is the single loaded `ms_eff_gcvit_b0` network.

One `ImagePredictor` is created in `get_shared_detector()` and reused for images and for sampled video frames. A lock surrounds face detection, cropping, and the forward pass so concurrent calls do not use that model at the same time. Weights load when the service is created. CUDA is used when `torch.cuda.is_available()` is true; the installed predictor selects `cpu` otherwise. This machine's shared service reports `cuda:0`.

OpenCV extracts up to 20 frames with the same even spacing as the upstream sampler. Each frame keeps `frame_index / fps` as its timestamp. Only frames with status `scored` enter the aggregate. The aggregate is the median of those raw sigmoid scores. It is not a calibrated probability. New analyses use `video_aggregation_v2`. A video is `fake` only when that median is at least 0.8, the high scores supply two pieces of temporal evidence, at least three scored frames clear the documented quality floors, and those high scores are not only low-quality detections. Two bursts more than one second apart supply that evidence. One burst supplies it only when the high scores last more than two seconds. It is `real` only when every scored frame is at or below 0.2. Anything else is `uncertain`. Fewer than three scored frames stays `indeterminate` with prediction `uncertain`, and the aggregate score is null. Reports saved under the older rule are returned unchanged.

A genuine model output of 0.5 is `scored` with prediction `uncertain`, because the service saw the sigmoid itself. The public fallback `0.5` is never copied into `fake_score`.

Wrapper results on the same official files, measured after the service was added:

| File | Status | Prediction | Aggregate raw score | Frame evidence |
|---|---|---|---|---|
| `western_real_1.JPG` | scored | real | below 0.2 | face found |
| `western_fake_1.JPG` | scored | fake or uncertain, not real | above 0.5 | face found |
| `western_real.mp4` | scored | uncertain | median 0.022642801515758038 | 20 of 20 sampled frames scored; maximum frame score 0.5041796565055847; 3 frames above 0.2; none at or above 0.8 |
| `western_fake.mp4` | scored | fake | median 0.9948382675647736 | 20 of 20 sampled frames scored; every frame at or above 0.858 |

The authentic video is not labelled `real` by the wrapper. Its median is low, but three frames sit above 0.2 and one reaches about 0.50. The upstream `VideoPredictor` aggregate of 0.0706 did not show that spread.

`D:\Hackathon\.venv\Scripts\python.exe -m pytest backend/tests -q --tb=line` completed with `17 passed in 9.81s`. The run covered both official images, both official videos, a corrupt image, a corrupt video, a generated no-face image, a generated no-face video, a mixed face and blank video, a forced model exception, a failed crop, an exact model output of 0.5, one shared predictor across calls, and four overlapping calls that never entered the model together.

## Outstanding problems

- Both OpenCV distributions are still installed. `cv2` imports, and the packages were not changed.
- The four upstream files still are not an accuracy evaluation.
- No FastAPI route calls the wrapper yet. YouTube audiovisual analysis remains forbidden by `docs/API_CONTRACTS.md`.
- System FFmpeg is still not on `PATH`. OpenCV's bundled DLL read the videos used here.
