from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.APIGateway.jobs import stage_enabled
from app.APIGateway.pipeline import STAGES
from app.APIGateway.server import appServer
from app.models.models import AnalyzeOptions, Observation


@pytest.fixture()
def client():
    with TestClient(appServer) as test_client:
        yield test_client


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_ai_status_contract(client):
    response = client.get("/api/ai/status")

    assert response.status_code == 200
    payload = response.json()

    assert "configured" in payload


def test_unknown_job_returns_404(client):
    response = client.get("/api/jobs/00000000000000000000000000000000")

    assert response.status_code == 404


def test_retry_unknown_stage_returns_404(client):
    response = client.post(
        "/api/jobs/00000000000000000000000000000000/retry/unknown"
    )

    assert response.status_code == 404


def test_test_endpoints_hidden_by_default(client, monkeypatch):
    monkeypatch.delenv("ENABLE_TEST_ENDPOINTS", raising=False)

    response = client.post(
        "/api/test/vision",
        files={"file": ("x.jpg", b"not-an-image", "image/jpeg")},
    )

    assert response.status_code == 404


def test_analyze_options_accept_new_and_legacy_names():
    options = AnalyzeOptions(
        visual_analysis=False,
        place_profile=True,
        location_prompt=False,
        scene_objects=False,
        ai_prompt=False,
    )

    assert options.visual_analysis is False
    assert options.place_profile is True
    assert options.location_prompt is False
    assert options.scene_objects is False


def test_stage_enabled_legacy_fallback():
    assert stage_enabled("visual_analysis", {"scene_objects": False, "visual_profile": True})
    assert not stage_enabled(
        "visual_analysis",
        {"scene_objects": False, "visual_profile": False, "faces": False},
    )
    assert stage_enabled("place_profile", {"road_geometry": True, "landmarks": False})
    assert not stage_enabled("place_profile", {"road_geometry": False, "landmarks": False})
    assert stage_enabled("location_prompt", {"ai_prompt": True})
    assert not stage_enabled("location_prompt", {"ai_prompt": False})


def test_observation_accepts_consolidated_sources():
    for source in ("visual_analysis", "place_profile", "location_prompt", "odometry", "bev"):
        item = Observation(source=source, text="x", extractor="test")

        assert item.source == source


def test_stage_names_are_unique():
    assert len(STAGES) == len(set(STAGES))
