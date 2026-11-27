from __future__ import annotations

import threading
import time

import pytest

from app.services.ghostMapService import core


SAMPLE = """
1. Большая Подусово д. при речке 12 34
2. Лощемля с. при пруде 5 20
3. Ивановская сц. сельцо при овраге 3 10
"""


def test_parse_snm_accepts_numbered_rows():
    rows = core.parse_snm(SAMPLE)

    assert [row["name"] for row in rows] == [
        "Большая Подусово",
        "Лощемля",
        "Ивановская",
    ]
    assert rows[0]["kind"] == "д."
    assert rows[0]["position"] == "речке"
    assert rows[0]["numbers"] == [12.0, 34.0]
    assert rows[1]["kind"] == "с."
    assert rows[2]["kind"] == "сц."


def test_normalize_name_handles_yo_and_old_endings():
    assert core.normalize_name("Берёзовка") == "березовка"
    assert core.normalize_name("Старый") == core.normalize_name("Старий")


def test_to_geojson_skips_points_without_coordinates():
    collection = core.to_geojson([
        {"name": "есть", "lat": 57.0, "lon": 35.0},
        {"name": "нет"},
    ])

    assert len(collection["features"]) == 1
    assert collection["features"][0]["geometry"]["coordinates"] == [35.0, 57.0]
    assert collection["features"][0]["properties"] == {"name": "есть"}


def test_parse_bbox_roundtrip():
    assert core._parse_bbox("31.0,56.2,38.6,58.9") == (
        31.0,
        56.2,
        38.6,
        58.9,
    )


@pytest.mark.parametrize(
    "value",
    [
        "31.0,56.2,38.6",
        "a,b,c,d",
        "38.6,56.2,31.0,58.9",
        "31.0,58.9,38.6,56.2",
    ],
)
def test_parse_bbox_rejects_bad_values(value):
    with pytest.raises(ValueError):
        core._parse_bbox(value)


def test_second_generation_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "ROOT", tmp_path)
    monkeypatch.setattr(core, "CACHE_DIR", tmp_path / "raw_html")
    monkeypatch.setattr(core, "STATUS_FILE", tmp_path / "status.json")
    monkeypatch.setattr(core, "LOG_FILE", tmp_path / "last_run.log")

    release = threading.Event()
    started = threading.Event()

    def fake(options):
        started.set()
        assert release.wait(5)
        return {"counts": {"matched": 0, "ghosts": 0, "unresolved": 0}}

    monkeypatch.setattr(core, "run_generation", fake)

    try:
        core.start_generation({"uyezd": "новоторжский"})
        assert started.wait(5)

        with pytest.raises(core.GenerationBusy):
            core.start_generation({})
    finally:
        release.set()

    for _ in range(100):
        if not core.status()["running"]:
            break

        time.sleep(0.05)

    assert core.status()["running"] is False
    assert core.status()["state"] == "completed"


def test_generate_rejects_unknown_uyezd():
    from fastapi.testclient import TestClient

    from app.APIGateway.server import appServer

    with TestClient(appServer) as client:
        response = client.post(
            "/api/ghost-map/generate",
            json={"uyezd": "несуществующий"},
        )

    assert response.status_code == 400
    assert "Неизвестный уезд" in response.json()["detail"]


def test_roads_reports_overpass_failure(monkeypatch):
    from fastapi.testclient import TestClient

    from app.APIGateway.endpoints import ghost_map as endpoint
    from app.APIGateway.server import appServer

    def unavailable(bbox):
        raise core.GhostMapError("Overpass недоступен: нет ответа")

    monkeypatch.setattr(endpoint, "roads", unavailable)

    with TestClient(appServer) as client:
        response = client.get(
            "/api/ghost-map/roads?bbox=31.0,56.2,38.6,58.9",
        )

    assert response.status_code == 502
    assert "Overpass" in response.json()["detail"]
