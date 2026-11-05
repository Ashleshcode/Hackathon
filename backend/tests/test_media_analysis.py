"""Media analysis routes. The detector is a fake; these tests do not load DeepGuard weights."""

import hashlib
import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_database_path, get_media_directory, initialize_database
from app.main import app
from app.media import analysis_service
from app.models.deepfake_detector import SCORE_SEMANTICS, DetectorResult


class FakeDetector:
    model_name = "test-detector"
    checkpoint_dataset = "ff++"
    device = "cpu"

    def __init__(self):
        self.image_result = _image_result("scored", 0.91, "fake")
        self.video_result = _video_result()
        self.image_error = None
        self.calls = []

    def analyze_image(self, path):
        self.calls.append(("image", str(path)))
        if self.image_error:
            raise self.image_error
        return self.image_result

    def analyze_video(self, path):
        self.calls.append(("video", str(path)))
        return self.video_result


def _image_result(status, score, prediction, error_code=None, error_message=None):
    return DetectorResult(
        status=status,
        media_type="image",
        model_name="test-detector",
        checkpoint_dataset="ff++",
        fake_score=score,
        prediction=prediction,
        device="cpu",
        processing_time=0.01,
        error_code=error_code,
        error_message=error_message,
        warnings=["fake_score is a raw sigmoid output, not a calibrated probability."],
    )


def _video_result():
    frame = {
        "frame_index": 0,
        "timestamp_seconds": 0.0,
        "status": "scored",
        "fake_score": 0.93,
        "prediction": "fake",
        "error_code": None,
        "error_message": None,
    }
    return DetectorResult(
        status="scored",
        media_type="video",
        model_name="test-detector",
        checkpoint_dataset="ff++",
        fake_score=0.93,
        prediction="fake",
        device="cpu",
        processing_time=0.02,
        score_semantics=SCORE_SEMANTICS,
        frames_sampled=1,
        frames_scored=1,
        aggregation_method="median of scored face frames",
        frame_results=[frame],
        warnings=["A single high frame cannot mark the video as fake."],
    )


def _png() -> bytes:
    ok, encoded = cv2.imencode(".png", np.zeros((8, 8, 3), dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def _video(tmp_path) -> bytes:
    path = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 8, (16, 16))
    assert writer.isOpened()
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    for _ in range(4):
        assert writer.write(frame)
    writer.release()
    return path.read_bytes()


def _job_count() -> int:
    connection = sqlite3.connect(get_database_path())
    try:
        return connection.execute("SELECT COUNT(*) FROM analysis_jobs").fetchone()[0]
    finally:
        connection.close()


@pytest.fixture
def client(monkeypatch):
    detector = FakeDetector()
    monkeypatch.setattr("app.models.deepfake_detector.get_shared_detector", lambda: detector)
    with TestClient(app) as test_client:
        yield test_client, detector


def _post_image(test_client, data, name="face.png"):
    return test_client.post("/api/analyze/image", files={"file": (name, data, "application/octet-stream")})


def test_successful_image_analysis_persists_without_a_filesystem_path(client):
    test_client, detector = client
    data = _png()
    response = _post_image(test_client, data, name="../../secret.png")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"]["prediction"] == "fake"
    assert body["result"]["fake_score"] == 0.91
    assert body["result"]["score_semantics"] == SCORE_SEMANTICS
    assert body["result"]["model"] == {"name": "test-detector", "checkpoint_dataset": "ff++"}
    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    assert "secret" not in response.text
    assert "\\" not in response.text
    assert detector.calls and detector.calls[0][0] == "image"
    stored = list(get_media_directory().iterdir())
    assert len(stored) == 1
    assert stored[0].name.startswith("ma_")
    assert "secret" not in stored[0].name

    connection = sqlite3.connect(get_database_path())
    try:
        media_hash, digest = connection.execute("SELECT media_hash, sha256 FROM media_assets").fetchone()
    finally:
        connection.close()
    assert media_hash is None
    assert digest == body["sha256"]


def test_successful_video_analysis_keeps_frame_evidence(client, tmp_path):
    test_client, _detector = client
    response = test_client.post(
        "/api/analyze/video",
        files={"file": ("clip.mp4", _video(tmp_path), "application/octet-stream")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"]["frames_sampled"] == 1
    assert body["result"]["frame_results"] == [
        {
            "timestamp_seconds": 0.0,
            "face_detected": True,
            "status": "scored",
            "prediction": "fake",
            "fake_score": 0.93,
        }
    ]
    assert "aggregation_method" in body["result"]


def test_uncertain_score_is_not_turned_into_a_label(client):
    test_client, detector = client
    detector.image_result = _image_result("scored", 0.5, "uncertain")
    body = _post_image(test_client, _png()).json()
    assert body["status"] == "completed"
    assert body["result"]["prediction"] == "uncertain"
    assert body["result"]["fake_score"] == 0.5


def test_no_face_has_no_score(client):
    test_client, detector = client
    detector.image_result = _image_result("no_face", None, None, "no_face", "No face met the detector size and confidence checks.")
    response = _post_image(test_client, _png())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"]["status"] == "no_face"
    assert body["result"]["prediction"] is None
    assert body["result"]["fake_score"] is None


def test_corrupt_image_is_not_a_completed_report(client):
    test_client, detector = client
    detector.image_error = AssertionError("detector should not run")
    response = _post_image(test_client, b"\xff\xd8\xffnot-a-jpeg")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["status"] == "failed"
    assert detail["result"]["fake_score"] is None
    assert detail["result"]["prediction"] is None
    assert list(get_media_directory().glob("*")) == []
    follow = test_client.get(f"/api/reports/{detail['report_id']}")
    assert follow.status_code == 409
    assert follow.json()["detail"]["status"] == "failed"


def test_unsupported_and_empty_files_do_not_complete(client):
    test_client, detector = client
    detector.image_error = AssertionError("detector should not run")
    unsupported = _post_image(test_client, b"this is plain text")
    assert unsupported.status_code == 415
    assert unsupported.json()["detail"]["status"] == "failed"
    empty = _post_image(test_client, b"")
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "empty_file"
    assert _job_count() == 0


def test_oversized_media_is_rejected_before_inference(client, monkeypatch):
    test_client, detector = client
    detector.image_error = AssertionError("detector should not run")
    monkeypatch.setattr(analysis_service, "IMAGE_MAX_BYTES", 8)
    response = _post_image(test_client, _png())
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"
    assert _job_count() == 0
    assert detector.calls == []


def test_detector_exception_does_not_leak_and_is_not_completed(client):
    test_client, detector = client
    detector.image_error = RuntimeError("SECRET_STACK Traceback internal")
    response = _post_image(test_client, _png())
    assert response.status_code == 422
    assert "SECRET_STACK" not in response.text
    assert "Traceback" not in response.text
    detail = response.json()["detail"]
    assert detail["status"] == "failed"
    assert detail["result"]["error_code"] == "model_exception"
    assert detail["result"]["fake_score"] is None
    assert detail["result"]["prediction"] is None


def test_database_failure_removes_the_file_and_does_not_complete(client, monkeypatch):
    test_client, _detector = client

    def fail(**_kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(analysis_service, "persist_analysis", fail)
    response = _post_image(test_client, _png())
    assert response.status_code == 500
    assert response.json()["detail"] == "The analysis could not be saved."
    assert "disk I/O" not in response.text
    assert _job_count() == 0
    assert list(get_media_directory().glob("*")) == []


def test_report_retrieval_and_unknown_id(client):
    test_client, _detector = client
    created = _post_image(test_client, _png()).json()
    fetched = test_client.get(f"/api/reports/{created['report_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["result"]["fake_score"] == 0.91
    assert fetched.json()["sha256"] == created["sha256"]
    missing = test_client.get("/api/reports/rpt_missing")
    assert missing.status_code == 404


def test_report_survives_restart(client, monkeypatch):
    test_client, _detector = client
    created = _post_image(test_client, _png()).json()
    report_id = created["report_id"]
    initialize_database()
    with TestClient(app) as restarted:
        fetched = restarted.get(f"/api/reports/{report_id}")
    assert fetched.status_code == 200
    assert fetched.json()["report_id"] == report_id
    assert fetched.json()["result"]["prediction"] == "fake"


def test_previous_media_asset_rows_survive_schema_migration(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE campaigns (
            campaign_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            provenance TEXT NOT NULL,
            source_file TEXT,
            parent_campaign_id TEXT,
            extension_post_json TEXT,
            import_summary_json TEXT NOT NULL,
            algorithm_json TEXT,
            limitations_json TEXT,
            clusters_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            post_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            account_id TEXT NOT NULL,
            timestamp TEXT,
            text TEXT,
            url TEXT,
            media_hash TEXT,
            media_reference TEXT,
            position INTEGER NOT NULL
        );
        CREATE TABLE media_assets (
            id INTEGER PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            post_row_id INTEGER NOT NULL,
            media_hash TEXT,
            media_reference TEXT,
            UNIQUE (post_row_id)
        );
        CREATE TABLE analysis_jobs (
            id INTEGER PRIMARY KEY,
            job_id TEXT NOT NULL UNIQUE,
            campaign_id TEXT,
            post_id TEXT,
            platform TEXT,
            media_asset_id INTEGER,
            status TEXT NOT NULL,
            status_reason TEXT,
            result_json TEXT,
            created_at TEXT NOT NULL
        );
        INSERT INTO campaigns VALUES ('C1','completed','synthetic_demo_data',NULL,NULL,NULL,'{}',NULL,'[]','[]','2026-11-05T00:00:00.000000Z');
        INSERT INTO posts VALUES (1,'C1','p1','platform_a','a',NULL,NULL,NULL,'supplied-hash',NULL,0);
        INSERT INTO media_assets VALUES (1,'C1',1,'supplied-hash',NULL);
        """
    )
    connection.commit()
    connection.close()

    initialize_database(path)
    connection = sqlite3.connect(path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(media_assets)")}
        stored = connection.execute("SELECT media_hash, sha256 FROM media_assets").fetchone()
        job_columns = {row[1] for row in connection.execute("PRAGMA table_info(analysis_jobs)")}
    finally:
        connection.close()
    assert "sha256" in columns
    assert "storage_name" in columns
    assert stored == ("supplied-hash", None)
    assert "completed_at" in job_columns


FIXTURES = Path(__file__).resolve().parent / "fixtures"
VP8 = (FIXTURES / "vp8.webm").read_bytes()
VP9 = (FIXTURES / "vp9.webm").read_bytes()


def _post_video(test_client, data, name="tab-capture.webm", content_type="video/webm"):
    return test_client.post("/api/analyze/video", files={"file": (name, data, content_type)})


def test_browser_webm_reaches_the_detector(client):
    test_client, detector = client
    response = _post_video(test_client, VP8, content_type="video/webm;codecs=vp8")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["media_type"] == "video"
    assert body["result"]["prediction"] == "fake"
    assert detector.calls and detector.calls[0][0] == "video"
    stored = list(get_media_directory().iterdir())
    assert len(stored) == 1
    assert stored[0].suffix == ".webm"
    assert stored[0].read_bytes().startswith(b"\x1a\x45\xdf\xa3")

    vp9 = _post_video(test_client, VP9, name="tab-capture.webm", content_type="video/webm;codecs=vp9")
    assert vp9.status_code == 200
    assert vp9.json()["status"] == "completed"


def test_corrupt_truncated_and_unsupported_webm_are_not_scored(client):
    test_client, detector = client
    detector.video_result = None
    detector.calls = []

    def reject_if_called(_path):
        raise AssertionError("detector should not run")

    detector.analyze_video = reject_if_called
    cases = {
        "corrupt": b"\x1a\x45\xdf\xa3" + b"\x00" * 32,
        "truncated": VP8[:400],
        "unsupported": VP8.replace(b"V_VP8", b"V_THEORA"),
    }
    for name, data in cases.items():
        response = _post_video(test_client, data, name=f"{name}.webm")
        assert response.status_code == 422, name
        detail = response.json()["detail"]
        assert detail["status"] == "failed", name
        assert detail["result"]["status"] == "invalid_media", name
        assert detail["result"]["prediction"] is None, name
        assert detail["result"]["fake_score"] is None, name
        assert detail["result"]["error_code"] == "unreadable_video", name
        assert "Traceback" not in response.text
        follow = test_client.get(f"/api/reports/{detail['report_id']}")
        assert follow.status_code == 409
    assert list(get_media_directory().glob("*")) == []


def test_empty_video_is_rejected_before_storage(client):
    test_client, detector = client
    response = _post_video(test_client, b"")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "empty_file"
    assert _job_count() == 0
    assert detector.calls == []
    assert list(get_media_directory().glob("*")) == []
