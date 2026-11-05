"""V2 video decisions and stored V1 reports."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_database_path
from app.main import app
from app.models.deepfake_detector import aggregate_video_scores
from app.models.video_aggregation import POLICY_V1, POLICY_V2, aggregate_video_v2, compare_v1_and_v2

ZOO_FRAMES = [
    (0.0, 0.833976, 0.819, 0.0283),
    (0.4096, 0.828668, 0.819, 0.0284),
    (0.8192, 0.603908, 0.801, 0.0278),
    (1.2288, 0.547542, 0.806, 0.0260),
    (1.6384, 0.693222, 0.823, 0.0265),
    (2.048, 0.709535, 0.827, 0.0263),
    (2.4576, 0.755469, 0.827, 0.0264),
    (2.8672, 0.977813, 0.667, 0.0116),
    (3.2768, 0.969143, 0.543, 0.0101),
    (3.6864, 0.954325, 0.820, 0.0282),
    (4.1643, 0.600386, 0.826, 0.0296),
    (4.5739, 0.662302, 0.827, 0.0311),
    (4.9835, 0.636526, 0.821, 0.0306),
    (5.3931, 0.659385, 0.827, 0.0296),
    (5.8027, 0.61857, 0.820, 0.0309),
    (6.2123, 0.651022, 0.817, 0.0314),
    (6.6219, 0.596709, 0.836, 0.0308),
    (7.0315, 0.640607, 0.839, 0.0311),
    (7.4411, 0.637807, 0.816, 0.0313),
    (7.919, 0.635926, 0.838, 0.0308),
]


def _frames(rows):
    frames = []
    for index, row in enumerate(rows):
        timestamp, score, confidence, area = row
        frames.append(
            {
                "frame_index": index,
                "timestamp_seconds": timestamp,
                "status": "scored",
                "prediction": "fake" if score >= 0.8 else "uncertain" if score > 0.2 else "real",
                "fake_score": score,
                "detector_confidence": confidence,
                "face_area_ratio": area,
            }
        )
    return frames


def _high(timestamp, score=0.95, confidence=0.9, area=0.05):
    return {
        "timestamp_seconds": timestamp,
        "status": "scored",
        "prediction": "fake",
        "fake_score": score,
        "detector_confidence": confidence,
        "face_area_ratio": area,
    }


def test_zoo_sequence_is_uncertain_under_v2_and_fake_under_the_old_counts():
    _status, old_prediction, old_median, _code, _message = aggregate_video_scores(
        [row[1] for row in ZOO_FRAMES],
        min_valid_frames=3,
    )
    assert old_prediction == "fake"
    assert old_median == pytest.approx(0.6552037298679352)
    decision = aggregate_video_v2(_frames(ZOO_FRAMES), min_valid_frames=3)
    assert decision.policy == POLICY_V2
    assert decision.prediction == "uncertain"
    assert decision.median == pytest.approx(0.6552037298679352)
    assert decision.evidence["high_frame_count"] == 5
    assert decision.evidence["high_burst_count"] == 2
    assert decision.evidence["eligible_burst_count"] == 2
    assert "median_below_fake_minimum" in decision.evidence["rejected_reasons"]
    low_quality = [frame for frame in decision.frames if frame["timestamp_seconds"] in {2.8672, 3.2768}]
    assert [frame["quality_eligible"] for frame in low_quality] == [False, False]
    assert low_quality[0]["burst_id"] == low_quality[1]["burst_id"]
    assert low_quality[0]["exclusion_reasons"]
    assert low_quality[0]["aggregation_eligible"] is False
    assert decision.evidence["excluded_frame_count"] == 2
    assert decision.evidence["eligible_median"] < 0.8
    assert decision.evidence["eligible_median"] != pytest.approx(decision.median)
    assert decision.evidence["profile_pose_measured"] is False
    assert decision.evidence["crop_blur_used_for_decision"] is False
    assert decision.evidence["decision_explanation"].startswith("Uncertain:")
    smallest = sorted(decision.frames, key=lambda frame: frame["face_area_ratio"])[:2]
    assert {frame["timestamp_seconds"] for frame in smallest} == {2.8672, 3.2768}
    assert all(frame["fake_score"] > 0.95 for frame in smallest)
    assert any(frame["quality_eligible"] and frame["fake_score"] >= 0.9 for frame in decision.frames)
    source = _frames(ZOO_FRAMES)
    aggregate_video_v2(source, min_valid_frames=3)
    assert [frame["fake_score"] for frame in source] == [row[1] for row in ZOO_FRAMES]
    assert all(frame["fake_score"] == original[1] for frame, original in zip(decision.frames, ZOO_FRAMES))
    compared = compare_v1_and_v2(_frames(ZOO_FRAMES), min_valid_frames=3)
    assert compared["v1"]["prediction"] == "fake"
    assert compared["v2"]["prediction"] == "uncertain"


def test_consistently_high_scores_are_fake_when_two_quality_bursts_exist():
    frames = [
        _high(0.0),
        _high(0.4),
        _high(3.0),
        _high(3.4),
    ]
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    assert decision.prediction == "fake"
    assert decision.evidence["eligible_burst_count"] == 2
    assert decision.median == pytest.approx(0.95)


def test_a_sustained_high_run_can_be_fake():
    frames = [_high(index * 0.4) for index in range(8)]
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    assert decision.evidence["high_burst_count"] == 1
    assert decision.evidence["sustained_burst_count"] == 1
    assert decision.evidence["temporal_evidence_count"] == 2
    assert decision.prediction == "fake"


def test_adjacent_high_frames_count_as_one_burst():
    frames = [_high(0.0), _high(0.4), _high(0.8), _high(1.2, score=0.91)]
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    assert decision.evidence["high_burst_count"] == 1
    assert decision.prediction == "uncertain"
    assert {frame["burst_id"] for frame in decision.frames} == {0}


def test_separated_high_scores_are_two_bursts():
    frames = [_high(0.0), _high(0.4, score=0.4, confidence=0.9, area=0.05), _high(2.5)]
    frames[1]["prediction"] = "uncertain"
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    highs = [frame for frame in decision.frames if frame["fake_score"] >= 0.8]
    assert [frame["burst_id"] for frame in highs] == [0, 1]
    assert decision.evidence["high_burst_count"] == 2


def test_every_low_score_remains_real():
    frames = [_high(index * 0.5, score=0.1, confidence=0.9, area=0.04) for index in range(4)]
    for frame in frames:
        frame["prediction"] = "real"
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    assert decision.prediction == "real"
    assert decision.median == pytest.approx(0.1)


def test_mixed_scores_are_uncertain():
    frames = [_high(0.0, score=0.91), _high(1.5, score=0.5), _high(3.0, score=0.1)]
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    assert decision.prediction == "uncertain"


def test_too_few_scored_frames_are_uncertain():
    decision = aggregate_video_v2([_high(0.0), _high(2.0)], min_valid_frames=3)
    assert decision.status == "indeterminate"
    assert decision.prediction == "uncertain"
    assert decision.median is None
    assert decision.error_code == "insufficient_valid_frames"


def test_low_quality_detections_cannot_establish_fake():
    frames = [
        _high(0.0, confidence=0.55, area=0.011),
        _high(0.4, confidence=0.55, area=0.011),
        _high(3.0, confidence=0.52, area=0.012),
        _high(3.4, confidence=0.52, area=0.012),
    ]
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    assert decision.prediction == "uncertain"
    assert decision.evidence["low_quality_only_high_scores"] is True
    assert decision.evidence["eligible_burst_count"] == 0
    assert all(frame["fake_score"] == 0.95 for frame in decision.frames)
    assert all(frame["quality_warnings"] for frame in decision.frames)
    assert "eligible_median_below_fake_minimum" in decision.evidence["rejected_reasons"]


def test_eligible_median_alone_cannot_overturn_a_low_overall_median():
    frames = [
        _high(0.0, score=0.91),
        _high(0.4, score=0.9),
        _high(3.0, score=0.92),
        _high(3.5, score=0.2, confidence=0.4, area=0.005),
        _high(4.2, score=0.15, confidence=0.4, area=0.005),
        _high(5.0, score=0.1, confidence=0.4, area=0.005),
        _high(5.6, score=0.12, confidence=0.4, area=0.005),
    ]
    for frame in frames[3:]:
        frame["prediction"] = "real"
    decision = aggregate_video_v2(frames, min_valid_frames=3)
    assert decision.evidence["eligible_median"] >= 0.8
    assert decision.median < 0.8
    assert decision.prediction == "uncertain"
    assert "median_below_fake_minimum" in decision.evidence["rejected_reasons"]


class _IdleDetector:
    def analyze_image(self, _path):
        raise AssertionError("historical retrieval must not score media")

    def analyze_video(self, _path):
        raise AssertionError("historical retrieval must not score media")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.models.deepfake_detector.get_shared_detector", lambda: _IdleDetector())
    with TestClient(app) as test_client:
        yield test_client


def test_historical_v1_report_keeps_its_stored_prediction(client):
    stored = {
        "status": "scored",
        "media_type": "video",
        "prediction": "fake",
        "fake_score": 0.6552037298679352,
        "score_semantics": "raw_model_score_not_calibrated_probability",
        "aggregation_policy": POLICY_V1,
        "aggregation_method": "median of scored face frames; fake requires at least two frames >= 0.8 and a median >= 0.5",
        "warnings": [],
    }
    connection = sqlite3.connect(get_database_path())
    try:
        asset_id = connection.execute(
            """
            INSERT INTO media_assets (asset_id, media_type, storage_name, byte_size, sha256, created_at)
            VALUES ('ma_v1', 'video', 'ma_v1.webm', 10, 'abc', '2026-11-05T00:00:00.000000Z')
            """
        ).lastrowid
        connection.execute(
            """
            INSERT INTO analysis_jobs (
                job_id, media_asset_id, status, status_reason, result_json, created_at, completed_at
            ) VALUES (?, ?, 'completed', NULL, ?, '2026-11-05T00:00:00.000000Z', '2026-11-05T00:00:00.000000Z')
            """,
            ("rpt_v1_historical", asset_id, json.dumps(stored)),
        )
        connection.commit()
    finally:
        connection.close()

    response = client.get("/api/reports/rpt_v1_historical")
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["prediction"] == "fake"
    assert body["result"]["fake_score"] == pytest.approx(0.6552037298679352)
    assert body["result"]["aggregation_policy"] == POLICY_V1
    assert body["result"]["aggregation_policy"] != POLICY_V2


def test_v2_policy_is_stored_and_retrieved_without_rescoring(client):
    stored = {
        "status": "scored",
        "media_type": "video",
        "prediction": "uncertain",
        "fake_score": 0.6552037298679352,
        "aggregation_policy": POLICY_V2,
        "aggregation_evidence": {"high_burst_count": 2, "eligible_burst_count": 2, "median": 0.6552037298679352},
        "warnings": [],
    }
    connection = sqlite3.connect(get_database_path())
    try:
        asset_id = connection.execute(
            """
            INSERT INTO media_assets (asset_id, media_type, storage_name, byte_size, sha256, created_at)
            VALUES ('ma_v2', 'video', 'ma_v2.webm', 10, 'def', '2026-11-05T00:00:00.000000Z')
            """
        ).lastrowid
        connection.execute(
            """
            INSERT INTO analysis_jobs (
                job_id, media_asset_id, status, status_reason, result_json, created_at, completed_at
            ) VALUES (?, ?, 'completed', NULL, ?, '2026-11-05T00:00:00.000000Z', '2026-11-05T00:00:00.000000Z')
            """,
            ("rpt_v2_stored", asset_id, json.dumps(stored)),
        )
        connection.commit()
    finally:
        connection.close()

    body = client.get("/api/reports/rpt_v2_stored").json()
    assert body["result"]["aggregation_policy"] == POLICY_V2
    assert body["result"]["prediction"] == "uncertain"
    assert body["result"]["aggregation_evidence"]["high_burst_count"] == 2
