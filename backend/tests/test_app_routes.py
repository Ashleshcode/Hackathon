"""Confirms the one API process exposes the campaign routes."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import analysis, campaigns, media, youtube
from app.main import app, health


def _included_routers():
    return [route.original_router for route in app.routes if getattr(route, "original_router", None) is not None]


def _paths():
    found = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            found.add(path)
        included = getattr(route, "original_router", None)
        if included is not None:
            found.update(getattr(item, "path", None) for item in included.routes)
    return found


def test_campaign_router_is_registered_once():
    included = _included_routers()
    assert included.count(campaigns.router) == 1
    assert included.count(analysis.router) == 1
    assert included.count(media.router) == 1
    assert included.count(youtube.router) == 1
    assert len(included) == 4
    paths = _paths()
    assert "/health" in paths
    assert "/api/analyze/image" in paths
    assert "/api/analyze/video" in paths
    assert "/api/reports/{report_id}" in paths
    assert "/api/media/analyze" in paths
    assert "/api/media/jobs/{job_id}" in paths
    assert "/api/youtube/context" in paths
    assert "/api/campaigns/import" in paths
    assert "/api/campaigns" in paths
    assert "/api/campaigns/{campaign_id}" in paths
    assert "/api/campaigns/{campaign_id}/graph" in paths
    assert "/api/campaigns/{campaign_id}/check-post" in paths
    assert "/api/campaigns/{campaign_id}/sync/x" in paths
    assert "/api/campaigns/{campaign_id}/x" in paths


def test_health_reports_detector_state_and_lifespan_initializes_it_once(monkeypatch):
    if hasattr(app.state, "detector"):
        del app.state.detector
    calls = []
    sentinel = SimpleNamespace(device="cpu", model_name="ms_eff_gcvit_b0")

    def fake_detector():
        calls.append("create")
        return sentinel

    monkeypatch.setattr("app.models.deepfake_detector.get_shared_detector", fake_detector)
    assert health()["detector"] == {"initialized": False, "device": None, "model_name": None}

    with TestClient(app) as client:
        first = client.get("/health").json()
        second = client.get("/health").json()

    assert calls == ["create"]
    assert first["status"] == "ok"
    assert first["service"] == "veritas-ai-api"
    assert first["version"] == "0.3.0"
    assert first["detector"] == {"initialized": True, "device": "cpu", "model_name": "ms_eff_gcvit_b0"}
    assert second["detector"]["initialized"] is True
