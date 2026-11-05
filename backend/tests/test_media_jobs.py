"""Aggregation, job lifecycle, API routes, upload rules, and mock isolation."""

import ast
import inspect
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.media_jobs as media_jobs_api
from app.api.media_jobs import (
    configure_media_jobs,
    dev_router,
    get_media_job_service,
    router,
)
from app.media.aggregation import aggregate_frame_results
from app.media.interfaces import SCORE_SEMANTICS, DetectionResult, ModelInfo
from app.media.media_jobs import (
    TEST_ONLY_MOCK_WARNING,
    InMemoryJobRepository,
    MediaJob,
    MediaJobService,
    MockDetectorRejectedError,
)
from mock_detector import (
    FACE_FAKE,
    FACE_REAL,
    FACE_UNCERTAIN,
    NO_FACE,
    FakeMediaStore,
    RaisingMockDetector,
    ScriptedMockDetector,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def make_service(store=None, script=None, detector=None) -> MediaJobService:
    if detector is None and script is not None:
        detector = ScriptedMockDetector(script)
    return MediaJobService(
        InMemoryJobRepository(), store, detector, allow_test_only_detector=True
    )


def make_client(service: MediaJobService) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.include_router(dev_router)
    app.dependency_overrides[get_media_job_service] = lambda: service
    return TestClient(app)


def run_job(store: FakeMediaStore, media_id: str, script=None, detector=None):
    """Create and process a product job, then return it as an API response."""
    service = make_service(store, script, detector)
    job = service.create_job(media_id)
    service.process_job(job.job_id)
    return service.get_job(job.job_id).to_response()


def frame(prediction: str, score: float | None, face: bool = True) -> dict:
    return {
        "timestamp_seconds": 0.0,
        "face_detected": face,
        "prediction": prediction,
        "fake_score": score,
    }


FAKE_FRAME = frame("fake", 2.0)
REAL_FRAME = frame("real", -2.0)
NO_FACE_FRAME = frame("unsupported", None, face=False)
UNCERTAIN_FRAME = frame("uncertain", None)


# ---------- aggregation ----------


def test_no_face_in_any_frame_gives_unsupported_and_null_score():
    aggregate = aggregate_frame_results([NO_FACE_FRAME] * 20)
    assert aggregate.frames_with_faces == 0
    assert aggregate.aggregate_prediction == "unsupported"
    assert aggregate.aggregate_fake_score is None
    assert "No usable face" in aggregate.warnings[0]
    assert "usable_frames=0" in aggregate.aggregation_method


def test_one_fake_frame_does_not_make_the_video_fake():
    aggregate = aggregate_frame_results([FAKE_FRAME] + [REAL_FRAME] * 19)
    assert aggregate.aggregate_prediction == "real"

    aggregate = aggregate_frame_results([FAKE_FRAME] + [NO_FACE_FRAME] * 19)
    assert aggregate.aggregate_prediction == "uncertain"
    assert aggregate.aggregate_fake_score is None


def test_conflicting_frames_give_uncertain_with_a_warning():
    aggregate = aggregate_frame_results([FAKE_FRAME] * 5 + [REAL_FRAME] * 5)
    assert aggregate.aggregate_prediction == "uncertain"
    assert aggregate.aggregate_fake_score == 0.0
    assert any("do not agree" in warning for warning in aggregate.warnings)


def test_two_thirds_supermajority_sets_the_label():
    assert aggregate_frame_results(
        [FAKE_FRAME] * 8 + [REAL_FRAME] * 4
    ).aggregate_prediction == "fake"
    assert aggregate_frame_results(
        [REAL_FRAME] * 8 + [FAKE_FRAME] * 4
    ).aggregate_prediction == "real"
    assert aggregate_frame_results(
        [FAKE_FRAME] * 7 + [REAL_FRAME] * 4
    ).aggregate_prediction == "uncertain"


def test_uncertain_face_frames_weaken_the_label():
    aggregate = aggregate_frame_results([FAKE_FRAME] * 4 + [UNCERTAIN_FRAME] * 8)
    assert aggregate.aggregate_prediction == "uncertain"
    assert aggregate.aggregate_fake_score == 2.0


def test_no_face_frames_do_not_affect_the_score_or_share():
    aggregate = aggregate_frame_results(
        [frame("fake", 1.0), frame("fake", 3.0), frame("fake", 9.0)]
        + [NO_FACE_FRAME] * 17
    )
    assert aggregate.aggregate_prediction == "fake"
    assert aggregate.aggregate_fake_score == 3.0
    assert any("limited part" in warning for warning in aggregate.warnings)


def test_faces_without_scores_give_uncertain_and_null_score():
    aggregate = aggregate_frame_results([UNCERTAIN_FRAME] * 10)
    assert aggregate.frames_with_faces == 10
    assert aggregate.aggregate_prediction == "uncertain"
    assert aggregate.aggregate_fake_score is None
    assert aggregate.warnings


# ---------- completed jobs ----------


def test_video_job_completes_with_contract_fields(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(100), "video/mp4")

    job = run_job(store, "med_0001", [FACE_FAKE])

    assert job["status"] == "completed"
    assert job["finished_at"]
    assert "error" not in job
    result = job["result"]
    assert set(result) == {
        "frames_sampled",
        "frames_with_faces",
        "frame_results",
        "aggregate_prediction",
        "aggregate_fake_score",
        "aggregation_method",
        "score_semantics",
        "warnings",
    }
    assert result["frames_sampled"] == 20
    assert result["frames_with_faces"] == 20
    assert result["aggregate_prediction"] == "fake"
    assert result["aggregate_fake_score"] == 2.5
    assert result["score_semantics"] == SCORE_SEMANTICS
    assert "usable_frames=20" in result["aggregation_method"]
    assert set(result["frame_results"][0]) == {
        "timestamp_seconds",
        "face_detected",
        "prediction",
        "fake_score",
    }
    last_timestamp = result["frame_results"][-1]["timestamp_seconds"]
    assert last_timestamp == pytest.approx(99 / 30)


def test_video_with_no_faces_completes_as_unsupported(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(10))

    job = run_job(store, "med_0001", [NO_FACE])

    assert job["status"] == "completed"
    assert job["result"]["aggregate_prediction"] == "unsupported"
    assert job["result"]["aggregate_fake_score"] is None
    assert job["result"]["frames_with_faces"] == 0
    assert any("No usable face" in w for w in job["result"]["warnings"])
    assert all(f["fake_score"] is None for f in job["result"]["frame_results"])


def test_conflicting_video_is_uncertain(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(10))
    script = [FACE_FAKE, FACE_REAL] * 5

    job = run_job(store, "med_0001", script)

    assert job["status"] == "completed"
    assert job["result"]["aggregate_prediction"] == "uncertain"


def test_unsupported_frames_are_excluded_from_the_score(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(10))
    script = [FACE_FAKE] * 5 + [NO_FACE] * 3 + [FACE_UNCERTAIN] * 2

    result = run_job(store, "med_0001", script)["result"]

    assert result["frames_with_faces"] == 7
    assert result["aggregate_prediction"] == "fake"
    assert result["aggregate_fake_score"] == 2.5


@pytest.mark.parametrize("prediction", ["real", "fake"])
def test_no_face_can_never_be_real_or_fake(make_video, prediction):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    bad_output = DetectionResult(0, prediction, 0.9)

    result = run_job(store, "med_0001", [bad_output])["result"]

    for frame_result in result["frame_results"]:
        assert frame_result["prediction"] == "unsupported"
        assert frame_result["fake_score"] is None
    assert result["aggregate_prediction"] == "unsupported"


def test_image_job_matches_contract(image_file):
    store = FakeMediaStore()
    store.add("med_0001", "image", image_file, "image/png")

    job = run_job(store, "med_0001", [FACE_REAL])

    assert job["status"] == "completed"
    assert set(job["result"]) == {
        "model",
        "face_count",
        "prediction",
        "fake_score",
        "score_semantics",
        "warnings",
    }
    assert job["result"]["prediction"] == "real"
    assert job["result"]["fake_score"] == -1.5
    assert job["result"]["score_semantics"] == SCORE_SEMANTICS


def test_image_without_face_has_null_score(image_file):
    store = FakeMediaStore()
    store.add("med_0001", "image", image_file)

    result = run_job(store, "med_0001", [NO_FACE])["result"]

    assert result["face_count"] == 0
    assert result["prediction"] == "unsupported"
    assert result["fake_score"] is None
    assert result["warnings"]


def test_undecodable_frames_appear_in_warnings(make_video, monkeypatch):
    from app.media import media_jobs
    from app.media.video_processor import VideoExtraction, VideoFrame

    image = np.zeros((4, 4, 3), dtype=np.uint8)
    extraction = VideoExtraction(
        [VideoFrame(i, i / 10, image) for i in range(3)], failed_frame_indices=[3, 4]
    )
    monkeypatch.setattr(media_jobs, "extract_video_frames", lambda _: extraction)
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(1))

    result = run_job(store, "med_0001", [FACE_FAKE])["result"]

    assert result["frames_sampled"] == 3
    assert any("[3, 4]" in warning for warning in result["warnings"])


# ---------- failed and unsupported jobs ----------


def assert_failed(job: dict, message: str) -> None:
    assert job["status"] == "failed"
    assert job["result"] is None
    assert message in job["error"]
    assert job["finished_at"]


def test_corrupt_video_fails_without_calling_detector(corrupt_file):
    store = FakeMediaStore()
    store.add("med_0001", "video", corrupt_file)
    detector = ScriptedMockDetector([FACE_FAKE])

    job = run_job(store, "med_0001", detector=detector)

    assert_failed(job, "video")
    assert detector.calls == 0


def test_corrupt_image_fails(corrupt_file):
    store = FakeMediaStore()
    store.add("med_0001", "image", corrupt_file)
    assert_failed(run_job(store, "med_0001", [FACE_FAKE]), "Image file")


def test_missing_stored_file_fails(tmp_path):
    store = FakeMediaStore()
    store.add("med_0001", "video", tmp_path / "gone.mp4")
    assert_failed(run_job(store, "med_0001", [FACE_FAKE]), "not found")


def test_store_fetch_failure_fails_the_job():
    store = FakeMediaStore()
    store.add("med_0001", "video", None)
    assert_failed(run_job(store, "med_0001", [FACE_FAKE]), "Could not download")


def test_detector_exception_fails_the_job(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    job = run_job(store, "med_0001", detector=RaisingMockDetector())
    assert_failed(job, "CUDA out of memory")


def test_missing_detector_fails_honestly(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    assert_failed(run_job(store, "med_0001"), "No production detector")


@pytest.mark.parametrize(
    ("detection", "message"),
    [
        (DetectionResult(1, "probably_fake", 1.0), "invalid prediction"),
        (DetectionResult(1, "fake", None), "without a score"),
        (DetectionResult(1, "fake", float("nan")), "non-finite"),
        (DetectionResult(1, "fake", "high"), "non-numeric"),
        (DetectionResult("1", "fake", 1.0), "invalid face_count"),
    ],
)
def test_invalid_detector_output_fails_the_job(make_video, detection, message):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    assert_failed(run_job(store, "med_0001", [detection]), message)


def test_unexpected_error_fails_without_leaking_details(make_video, monkeypatch):
    from app.media import media_jobs

    def explode(_):
        raise RuntimeError("secret internal path C:\\private")

    monkeypatch.setattr(media_jobs, "extract_video_frames", explode)
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(1))

    job = run_job(store, "med_0001", [FACE_FAKE])

    assert_failed(job, "RuntimeError")
    assert "private" not in job["error"]


@pytest.mark.parametrize(
    ("media_type", "mime_type"),
    [("audio", "audio/mpeg"), ("video", "application/x-mpegurl"), ("image", "image/svg+xml")],
)
def test_unsupported_media_gets_unsupported_status(make_video, media_type, mime_type):
    store = FakeMediaStore()
    store.add("med_0001", media_type, make_video(1), mime_type)
    detector = ScriptedMockDetector([FACE_FAKE])

    job = run_job(store, "med_0001", detector=detector)

    assert job["status"] == "unsupported"
    assert job["result"] is None
    assert "Unsupported" in job["error"]
    assert detector.calls == 0


def test_job_is_not_processed_twice(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    detector = ScriptedMockDetector([FACE_FAKE])
    service = make_service(store, detector=detector)
    job = service.create_job("med_0001")

    service.process_job(job.job_id)
    calls_after_first_run = detector.calls
    service.process_job(job.job_id)

    assert detector.calls == calls_after_first_run


# ---------- product routes ----------


def test_post_returns_queued_job_matching_contract(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    client = make_client(make_service(store, [FACE_FAKE]))

    response = client.post("/api/v1/media-jobs", json={"media_id": "med_0001"})

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {
        "job_id",
        "media_id",
        "post_id",
        "monitor_id",
        "media_type",
        "status",
        "result",
        "created_at",
    }
    assert body["job_id"].startswith("job_")
    assert body["media_id"] == "med_0001"
    assert body["post_id"] == "post_0001"
    assert body["monitor_id"] == "mon_0001"
    assert body["media_type"] == "video"
    assert body["status"] == "queued"
    assert body["result"] is None


def test_get_returns_completed_job(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    client = make_client(make_service(store, [FACE_FAKE]))

    # TestClient runs background tasks before returning.
    job_id = client.post("/api/v1/media-jobs", json={"media_id": "med_0001"}).json()[
        "job_id"
    ]
    response = client.get(f"/api/v1/media-jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["result"]["frames_sampled"] == 5


def test_get_returns_queued_job_with_null_result():
    store = FakeMediaStore()
    store.add("med_0001", "video", None)
    service = make_service(store, [FACE_FAKE])
    job = service.create_job("med_0001")

    body = make_client(service).get(f"/api/v1/media-jobs/{job.job_id}").json()

    assert body["status"] == "queued"
    assert body["result"] is None


def test_get_returns_failed_job_with_error(corrupt_file):
    store = FakeMediaStore()
    store.add("med_0001", "video", corrupt_file)
    client = make_client(make_service(store, [FACE_FAKE]))

    job_id = client.post("/api/v1/media-jobs", json={"media_id": "med_0001"}).json()[
        "job_id"
    ]
    assert_failed(client.get(f"/api/v1/media-jobs/{job_id}").json(), "video")


def test_job_ids_are_unique(make_video):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(1))
    service = make_service(store, [FACE_FAKE])
    assert len({service.create_job("med_0001").job_id for _ in range(50)}) == 50


def test_unknown_media_id_returns_404():
    client = make_client(make_service(FakeMediaStore(), [FACE_FAKE]))
    response = client.post("/api/v1/media-jobs", json={"media_id": "med_9999"})
    assert response.status_code == 404
    assert "media_id" in response.json()["detail"]


def test_unknown_job_id_returns_404():
    client = make_client(make_service(FakeMediaStore(), [FACE_FAKE]))
    assert client.get("/api/v1/media-jobs/job_missing").status_code == 404


def test_storage_not_connected_returns_503():
    client = make_client(make_service(None, [FACE_FAKE]))
    response = client.post("/api/v1/media-jobs", json={"media_id": "med_0001"})
    assert response.status_code == 503


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"media_id": "https://example.invalid/video.mp4"},
        {"media_id": "../../etc/passwd"},
        {"media_id": "med_0001", "source_url": "https://example.invalid/video.mp4"},
    ],
)
def test_product_route_rejects_anything_but_a_media_id(payload):
    store = FakeMediaStore()
    store.add("med_0001", "video", None)
    client = make_client(make_service(store, [FACE_FAKE]))
    assert client.post("/api/v1/media-jobs", json=payload).status_code == 422


def test_product_route_rejects_file_upload():
    client = make_client(make_service(FakeMediaStore(), [FACE_FAKE]))
    response = client.post(
        "/api/v1/media-jobs", files={"file": ("video.mp4", b"data", "video/mp4")}
    )
    assert response.status_code == 422


# ---------- developer upload route ----------

UPLOAD_URL = "/api/v1/dev/media-jobs/upload"
SYNTHETIC = {"media_type": "video", "provenance_label": "synthetic_demo"}


@pytest.fixture
def dev_routes_enabled(monkeypatch):
    monkeypatch.setenv("VERITAS_ENABLE_DEV_ROUTES", "1")


@pytest.fixture
def isolated_temp(monkeypatch, tmp_path):
    """Send upload temp files to an empty folder, so leftovers can be checked."""
    folder = tmp_path / "uploads_temp"
    folder.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(folder))
    return folder


def post_upload(client, filename, content, data=SYNTHETIC):
    return client.post(UPLOAD_URL, files={"file": (filename, content)}, data=data)


def test_dev_route_is_hidden_unless_enabled(monkeypatch, make_video):
    monkeypatch.delenv("VERITAS_ENABLE_DEV_ROUTES", raising=False)
    client = make_client(make_service(None, [FACE_FAKE]))
    response = post_upload(client, "a.mp4", make_video(5).read_bytes())
    assert response.status_code == 404


def test_upload_processes_video_and_deletes_temp_file(
    dev_routes_enabled, isolated_temp, make_video
):
    client = make_client(make_service(None, [FACE_FAKE]))

    response = post_upload(client, "clip.mp4", make_video(5).read_bytes())

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["post_id"] is None
    assert body["monitor_id"] is None
    assert body["media_id"].startswith("med_dev_")
    assert list(isolated_temp.iterdir()) == []

    job = client.get(f"/api/v1/media-jobs/{body['job_id']}").json()
    assert job["status"] == "completed"
    assert job["result"]["frames_sampled"] == 5
    assert any("synthetic_demo" in w for w in job["result"]["warnings"])


def test_upload_processes_image(dev_routes_enabled, isolated_temp, image_file):
    client = make_client(make_service(None, [FACE_REAL]))
    data = {"media_type": "image", "provenance_label": "curated_public_sample"}

    body = post_upload(client, "a.png", image_file.read_bytes(), data).json()

    job = client.get(f"/api/v1/media-jobs/{body['job_id']}").json()
    assert job["result"]["prediction"] == "real"


def test_upload_temp_file_deleted_when_processing_fails(
    dev_routes_enabled, isolated_temp
):
    client = make_client(make_service(None, [FACE_FAKE]))
    # Valid MP4 signature, but the rest of the file is garbage.
    content = b"\x00\x00\x00\x18ftypmp42" + b"garbage" * 100

    body = post_upload(client, "broken.mp4", content).json()

    assert_failed(client.get(f"/api/v1/media-jobs/{body['job_id']}").json(), "video")
    assert list(isolated_temp.iterdir()) == []


@pytest.mark.parametrize(
    ("filename", "content", "media_type"),
    [
        ("notes.txt", b"plain text", "video"),
        ("clip.mov", b"\x00\x00\x00\x18ftypqt  ", "video"),  # Contract: image or MP4.
        ("fake.mp4", b"this is not a video at all", "video"),
        ("photo.png", b"\x89PNG\r\n\x1a\n0000", "video"),
        ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "image"),
        ("fake.png", b"\xff\xd8\xff\xe0 jpeg bytes", "image"),
        ("run.exe", b"MZ\x90\x00", "image"),
        ("no_extension", b"\xff\xd8\xff\xe0", "image"),
    ],
)
def test_upload_type_validation(
    dev_routes_enabled, isolated_temp, filename, content, media_type
):
    client = make_client(make_service(None, [FACE_FAKE]))
    data = {"media_type": media_type, "provenance_label": "synthetic_demo"}

    response = post_upload(client, filename, content, data)

    assert response.status_code == 415
    assert response.json()["detail"].startswith("file:")
    assert list(isolated_temp.iterdir()) == []


def test_upload_size_validation(dev_routes_enabled, isolated_temp, monkeypatch):
    monkeypatch.setattr(media_jobs_api, "MAX_VIDEO_UPLOAD_BYTES", 1024)
    detector = ScriptedMockDetector([FACE_FAKE])
    client = make_client(make_service(None, detector=detector))
    content = b"\x00\x00\x00\x18ftypmp42" + b"0" * 2048

    response = post_upload(client, "big.mp4", content)

    assert response.status_code == 413
    assert list(isolated_temp.iterdir()) == []
    assert detector.calls == 0


def test_empty_upload_is_rejected(dev_routes_enabled):
    client = make_client(make_service(None, [FACE_FAKE]))
    assert post_upload(client, "empty.mp4", b"").status_code == 422


@pytest.mark.parametrize(
    "data",
    [
        {"media_type": "video"},
        {"media_type": "video", "provenance_label": "platform_api"},
        {"media_type": "audio", "provenance_label": "synthetic_demo"},
    ],
)
def test_upload_form_field_validation(dev_routes_enabled, make_video, data):
    client = make_client(make_service(None, [FACE_FAKE]))
    response = post_upload(client, "clip.mp4", make_video(1).read_bytes(), data)
    assert response.status_code == 422


# ---------- mock isolation ----------


def test_service_rejects_mock_detector_by_default():
    with pytest.raises(MockDetectorRejectedError):
        MediaJobService(InMemoryJobRepository(), None, ScriptedMockDetector([FACE_FAKE]))


def test_production_wiring_rejects_mock_detector():
    with pytest.raises(MockDetectorRejectedError):
        configure_media_jobs(detector=ScriptedMockDetector([FACE_FAKE]))


def test_mock_output_is_labelled(make_video, image_file):
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    store.add("med_0002", "image", image_file)

    video = run_job(store, "med_0001", [FACE_FAKE])
    image = run_job(store, "med_0002", [FACE_FAKE])

    assert TEST_ONLY_MOCK_WARNING in video["result"]["warnings"]
    assert TEST_ONLY_MOCK_WARNING in image["result"]["warnings"]
    assert image["result"]["model"]["name"] == "TEST_ONLY_MOCK"


def test_application_code_never_imports_the_mock():
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                # Also catches "from tests import mock_detector".
                names = [node.module or ""] + [alias.name for alias in node.names]
            for name in names:
                assert "mock" not in name.lower(), path
                assert name.split(".")[0] != "tests", path


def test_application_code_never_enables_the_mock():
    for path in (BACKEND_ROOT / "app").rglob("*.py"):
        assert "allow_test_only_detector=True" not in path.read_text(encoding="utf-8")
    parameters = inspect.signature(configure_media_jobs).parameters
    assert "allow_test_only_detector" not in parameters


# ---------- Member 1 wiring and detector values seen in real use ----------


class JsonRoundTripRepository:
    """Stores jobs as JSON, as a database would. It is falsy while empty."""

    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self.rows)

    def save(self, job: MediaJob) -> None:
        self.rows[job.job_id] = json.dumps(asdict(job))

    def get(self, job_id: str) -> MediaJob | None:
        row = self.rows.get(job_id)
        return MediaJob(**json.loads(row)) if row else None


class WiringStubDetector:
    """Not flagged as a mock, because it proves the unflagged wiring path.

    It exists only to test ``configure_media_jobs``, and returns NumPy values
    because real inference code commonly does.
    """

    model_info = ModelInfo("wiring-stub", "wiring-stub", "wiring-stub")

    def analyze_image(self, image: object) -> DetectionResult:
        return DetectionResult(np.int64(1), "fake", np.float32(1.5))


def test_configure_connects_all_three_dependencies(monkeypatch, make_video):
    # Restores the module's real service when the test ends.
    monkeypatch.setattr(media_jobs_api, "_service", media_jobs_api._service)
    store = FakeMediaStore()
    store.add("med_0001", "video", make_video(5))
    repository = JsonRoundTripRepository()

    configure_media_jobs(
        media_store=store,
        detector=WiringStubDetector(),
        job_repository=repository,
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    job_id = client.post("/api/v1/media-jobs", json={"media_id": "med_0001"}).json()[
        "job_id"
    ]
    response = client.get(f"/api/v1/media-jobs/{job_id}")

    assert job_id in repository.rows
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["post_id"] == "post_0001"
    assert body["result"]["aggregate_fake_score"] == 1.5
    assert repository.get(job_id).model["name"] == "wiring-stub"


@pytest.mark.parametrize("media_type", ["image", "video"])
def test_numpy_detector_values_reach_the_api_as_json(
    make_video, image_file, media_type
):
    store = FakeMediaStore()
    path = image_file if media_type == "image" else make_video(5)
    store.add("med_0001", media_type, path)
    service = MediaJobService(InMemoryJobRepository(), store, WiringStubDetector())
    client = make_client(service)

    job_id = client.post("/api/v1/media-jobs", json={"media_id": "med_0001"}).json()[
        "job_id"
    ]
    response = client.get(f"/api/v1/media-jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.parametrize("media_type", ["image", "video"])
def test_detector_without_model_info_fails_instead_of_sticking(
    make_video, image_file, media_type
):
    class NoModelInfoDetector:
        def analyze_image(self, image: object) -> DetectionResult:
            return FACE_FAKE

    store = FakeMediaStore()
    path = image_file if media_type == "image" else make_video(5)
    store.add("med_0001", media_type, path)

    job = run_job(store, "med_0001", detector=NoModelInfoDetector())

    assert_failed(job, "AttributeError")

