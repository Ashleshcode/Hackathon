"""X media jobs use the shared detector and never fetch a remote URL."""

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_database_path, get_media_directory, initialize_database
from app.intelligence import campaign_store
from app.intelligence.graph_engine import build_graph
from app.intelligence.post_ingestion import Post
from app.main import app
from app.models.deepfake_detector import SCORE_SEMANTICS, DetectorResult

VARIANT_URL = "https://video.example.test/do-not-fetch.mp4"
LOW_VARIANT_URL = "https://video.example.test/low.mp4"


class FakeDetector:
    model_name = "test-detector"
    checkpoint_dataset = "ff++"
    device = "cpu"

    def __init__(self):
        self.image_result = _result("image", "scored", 0.91, "fake")
        self.video_result = _result(
            "video",
            "scored",
            0.93,
            "fake",
            frames_sampled=2,
            frames_scored=2,
            aggregation_method="median of scored face frames; fake requires at least two frames >= 0.8",
            frame_results=[
                {
                    "frame_index": 0,
                    "timestamp_seconds": 0.0,
                    "status": "scored",
                    "fake_score": 0.9,
                    "prediction": "fake",
                    "error_code": None,
                    "error_message": None,
                }
            ],
        )
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


def _result(media_type, status, score, prediction, **extra):
    return DetectorResult(
        status=status,
        media_type=media_type,
        model_name="test-detector",
        checkpoint_dataset="ff++",
        fake_score=score,
        prediction=prediction,
        device="cpu",
        processing_time=0.01,
        score_semantics=SCORE_SEMANTICS,
        warnings=["fake_score is a raw sigmoid output, not a calibrated probability."],
        **extra,
    )


def _campaign_id():
    post = Post(
        post_id="local-1",
        platform="platform_a",
        account_id="alpha",
        timestamp=datetime(2026, 11, 5, 10, tzinfo=timezone.utc),
    )
    graph = build_graph([post])
    summary = {"total_records": 1, "accepted": 1, "rejected": 0, "errors": [], "platforms": {"platform_a": 1}}
    graph["provenance"] = "synthetic_demo_data"
    graph["import_summary"] = summary
    return campaign_store.save_campaign(
        {
            "status": "completed",
            "provenance": "synthetic_demo_data",
            "source_file": "synthetic_demo_data.csv",
            "import_summary": summary,
            "posts": [post.to_dict()],
        },
        graph,
    )


def _seed(media_type="video", url=None, variants=None, storage_name=None, preview=None, post_id="1234567890", media_key="13_1234567890"):
    campaign_id = _campaign_id()
    connection = sqlite3.connect(get_database_path())
    cursor = connection.execute(
        """
        INSERT INTO posts (campaign_id, post_id, platform, account_id, position)
        VALUES (?, ?, 'x', '42', 50)
        """,
        (campaign_id, post_id),
    )
    connection.execute(
        """
        INSERT INTO x_media (
            campaign_id, post_row_id, media_key, media_type, url, preview_image_url,
            variants_json, storage_name, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '2026-11-05T10:00:00.000000Z')
        """,
        (
            campaign_id,
            cursor.lastrowid,
            media_key,
            media_type,
            url,
            preview,
            None if variants is None else json.dumps(variants),
            storage_name,
        ),
    )
    connection.commit()
    connection.close()
    return campaign_id


def _rows(sql, params=()):
    connection = sqlite3.connect(get_database_path())
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


@pytest.fixture
def api(monkeypatch):
    detector = FakeDetector()
    monkeypatch.setattr("app.models.deepfake_detector.get_shared_detector", lambda: detector)
    with TestClient(app) as client:
        yield client, detector


def _analyze(client, post_id="1234567890", media_key="13_1234567890", **extra):
    body = {"post_id": post_id, "media_key": media_key, **extra}
    return client.post("/api/media/analyze", json=body)


def test_request_accepts_only_post_id_and_media_key(api):
    client, detector = api
    _seed()
    response = _analyze(client, url=VARIANT_URL)
    assert response.status_code == 422
    assert detector.calls == []
    assert _rows("SELECT COUNT(*) FROM analysis_jobs")[0][0] == 0


def test_absent_variant_is_unavailable_and_is_not_fetched(api):
    client, detector = api
    _seed(variants=[])
    response = _analyze(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["status_reason"] == "x_api_did_not_provide_a_permitted_variant"
    assert body["variant_access"] == "absent"
    assert body["result"] is None
    assert body["platform"] == "x"
    assert detector.calls == []
    fetched = client.get(f"/api/media/jobs/{body['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "unavailable"


def test_stored_variant_url_is_not_downloaded_or_returned(api):
    client, _detector = api
    _seed(
        variants=[
            {"content_type": "video/mp4", "bit_rate": 256000, "url": LOW_VARIANT_URL},
            {"content_type": "video/mp4", "bit_rate": 832000, "url": VARIANT_URL},
            {"content_type": "application/x-mpegURL", "url": "https://video.example.test/playlist.m3u8"},
        ]
    )
    response = _analyze(client)
    assert response.status_code == 200
    body = response.json()
    assert body["variant_access"] == "present"
    assert body["status"] == "unavailable"
    assert body["status_reason"] == "permitted_media_not_retrieved"
    assert body["result"] is None
    assert VARIANT_URL not in response.text
    assert LOW_VARIANT_URL not in response.text
    assert "m3u8" not in response.text


def test_youtube_target_is_rejected_without_a_job(api):
    client, detector = api
    _seed(url="https://www.youtube.com/watch?v=abcdefghijk", media_type="video")
    response = _analyze(client)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "youtube_audiovisual_analysis_not_permitted"
    assert detector.calls == []
    assert _rows("SELECT COUNT(*) FROM analysis_jobs")[0][0] == 0


def test_linked_image_uses_the_shared_detector_result(api):
    client, detector = api
    directory = get_media_directory()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ma_photo.png").write_bytes(b"png-bytes")
    _seed(media_type="photo", url="https://pbs.example.test/photo.jpg", storage_name="ma_photo.png")
    response = _analyze(client)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["result"]["prediction"] == "fake"
    assert body["result"]["fake_score"] == 0.91
    assert body["result"]["score_semantics"] == SCORE_SEMANTICS
    assert body["result"]["model"]["version"] is None
    assert "pbs.example.test" not in response.text
    assert detector.calls and detector.calls[0][0] == "image"
    assert _rows("SELECT COUNT(*) FROM graph_edges")[0][0] == 0


def test_linked_video_keeps_the_existing_aggregation(api):
    client, detector = api
    directory = get_media_directory()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ma_clip.mp4").write_bytes(b"mp4-bytes")
    _seed(variants=[{"content_type": "video/mp4", "bit_rate": 1000, "url": VARIANT_URL}], storage_name="ma_clip.mp4")
    body = _analyze(client).json()
    assert body["status"] == "completed"
    assert body["result"]["frames_sampled"] == 2
    assert body["result"]["frame_results"][0]["timestamp_seconds"] == 0.0
    assert "median of scored face frames" in body["result"]["aggregation_method"]
    assert "two_thirds" not in body["result"]["aggregation_method"]
    assert VARIANT_URL not in json.dumps(body)
    assert detector.calls[0][0] == "video"


def test_uncertain_and_no_face_are_not_relabelled_as_fake(api):
    client, detector = api
    directory = get_media_directory()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ma_photo.png").write_bytes(b"png-bytes")
    _seed(media_type="photo", url="https://pbs.example.test/photo.jpg", storage_name="ma_photo.png")
    detector.image_result = _result("image", "scored", 0.5, "uncertain")
    uncertain = _analyze(client).json()["result"]
    assert uncertain["prediction"] == "uncertain"
    assert uncertain["fake_score"] == 0.5
    detector.image_result = _result("image", "no_face", None, None, error_code="no_face")
    no_face = _analyze(client).json()
    assert no_face["status"] == "completed"
    assert no_face["result"]["prediction"] == "unsupported"
    assert no_face["result"]["fake_score"] is None
    assert no_face["result"]["detector_status"] == "no_face"


def test_detector_exception_is_not_exposed(api):
    client, detector = api
    directory = get_media_directory()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ma_photo.png").write_bytes(b"png-bytes")
    _seed(media_type="photo", url="https://pbs.example.test/photo.jpg", storage_name="ma_photo.png")
    detector.image_error = RuntimeError("SECRET_STACK Traceback")
    response = _analyze(client)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["result"] is None
    assert "SECRET_STACK" not in response.text
    assert "Traceback" not in response.text


def test_database_failure_does_not_leave_a_completed_job(api, monkeypatch):
    client, _detector = api
    directory = get_media_directory()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ma_photo.png").write_bytes(b"png-bytes")
    _seed(media_type="photo", url="https://pbs.example.test/photo.jpg", storage_name="ma_photo.png")

    def fail(_job):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr("app.media.x_media_jobs.save_x_media_job", fail)
    response = _analyze(client)
    assert response.status_code == 500
    assert response.json()["detail"] == "The media job could not be saved."
    assert "disk I/O" not in response.text
    assert _rows("SELECT COUNT(*) FROM analysis_jobs")[0][0] == 0
    assert (directory / "ma_photo.png").is_file()


def test_unknown_media_and_unknown_job(api):
    client, _detector = api
    missing = _analyze(client)
    assert missing.status_code == 404
    assert client.get("/api/media/jobs/job_missing").status_code == 404


def test_job_survives_restart(api):
    client, _detector = api
    _seed(variants=[])
    created = _analyze(client).json()
    initialize_database()
    with TestClient(app) as restarted:
        fetched = restarted.get(f"/api/media/jobs/{created['job_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["job_id"] == created["job_id"]
    assert fetched.json()["result"] is None
