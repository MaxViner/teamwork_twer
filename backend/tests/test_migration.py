from __future__ import annotations

from app.services.migrationService.jobs import (
    migrate_all,
    migrate_job,
)


def _stage(status="completed", result=None, observations=None):
    return {
        "status": status,
        "run_id": "r1",
        "result_run_id": "r1",
        "result": result or {},
        "observations": observations or [],
        "history": [],
        "error": None,
        "note": None,
    }


def _legacy_job():
    return {
        "id": "0" * 32,
        "options": {
            "scene_objects": True,
            "visual_profile": True,
            "faces": False,
            "road_geometry": True,
            "landmarks": True,
            "ai_prompt": False,
        },
        "stages": {
            "prepare": _stage(result={"duration": 10.0}),
            "scene_objects": _stage(
                result={
                    "method": "segformer",
                    "frames": [
                        {
                            "timestamp": 0.0,
                            "artifact": "runs/r1/f.jpg",
                            "objects": [{"label": "building"}],
                        }
                    ],
                    "unique_objects": [{"label": "building", "frame_count": 1}],
                    "object_count": 1,
                },
                observations=[
                    {"id": "o1", "source": "scene_objects", "text": "building"}
                ],
            ),
            "visual_profile": _stage(
                result={
                    "profile": {"lighting": "day"},
                    "frames": [
                        {
                            "timestamp": 0.0,
                            "artifact": "runs/r1/f.jpg",
                            "metrics": {"asphalt": 10},
                            "descriptors": {"landscape": []},
                        }
                    ],
                },
                observations=[
                    {"id": "o2", "source": "visual_profile", "text": "day"}
                ],
            ),
            "faces": _stage(
                result={"people": [{"label": "Человек 1"}], "face_count": 1},
                observations=[
                    {"id": "o3", "source": "faces", "text": "person"}
                ],
            ),
            "road_geometry": _stage(
                result={"summary": {"road_detected": True}, "episodes": []},
                observations=[
                    {"id": "o4", "source": "road_geometry", "text": "road"}
                ],
            ),
            "landmarks": _stage(
                result={
                    "landmarks": [{"label": "церковь", "frame_count": 1}],
                    "geometry": {"median_horizon": 0.4},
                    "frames": [{"timestamp": 0.0, "artifact": "runs/r1/f.jpg"}],
                    "frame_count_total": 1,
                    "landmark_count": 1,
                },
                observations=[
                    {"id": "o5", "source": "landmarks", "text": "church"}
                ],
            ),
            "ai_prompt": _stage(
                result={"prompt": "find this place"},
                observations=[
                    {"id": "o6", "source": "ai_prompt", "text": "find this place"}
                ],
            ),
        },
    }


def test_migration_adds_consolidated_stages():
    job = _legacy_job()

    assert migrate_job(job) is True

    stages = job["stages"]
    assert "visual_analysis" in stages
    assert "place_profile" in stages
    assert "location_prompt" in stages

    visual = stages["visual_analysis"]["result"]
    assert visual["method"] == "segformer"
    assert visual["profile"]["lighting"] == "day"
    assert visual["unique_objects"][0]["label"] == "building"
    assert visual["people"][0]["label"] == "Человек 1"
    assert visual["counts"]["frames"] == 1
    assert visual["frames"][0]["metrics"]["asphalt"] == 10
    assert visual["frames"][0]["objects"][0]["label"] == "building"

    place = stages["place_profile"]["result"]
    assert place["road"]["summary"]["road_detected"] is True
    assert place["landmarks"][0]["label"] == "церковь"
    assert place["geometry"]["median_horizon"] == 0.4
    assert place["bev"] is None

    assert stages["location_prompt"]["result"]["prompt"] == "find this place"


def test_migration_rewrites_sources_and_clears_legacy_observations():
    job = _legacy_job()
    migrate_job(job)

    stages = job["stages"]

    assert stages["visual_analysis"]["observations"]
    assert all(
        item["source"] == "visual_analysis"
        for item in stages["visual_analysis"]["observations"]
    )
    assert stages["scene_objects"]["observations"] == []
    assert stages["road_geometry"]["observations"] == []
    assert stages["ai_prompt"]["observations"] == []


def test_migration_maps_options():
    job = _legacy_job()
    migrate_job(job)

    options = job["options"]

    assert options["visual_analysis"] is True
    assert options["place_profile"] is True
    assert options["location_prompt"] is False


def test_migration_is_idempotent():
    job = _legacy_job()

    assert migrate_job(job) is True
    snapshot = repr(job)

    assert migrate_job(job) is False
    assert repr(job) == snapshot


def test_migrate_all_counts(tmp_path):
    for index in range(3):
        folder = tmp_path / str(index)
        folder.mkdir()
        import json

        (folder / "job.json").write_text(
            json.dumps(_legacy_job()),
            encoding="utf-8",
        )

    first = migrate_all(tmp_path)
    second = migrate_all(tmp_path)

    assert first == {"total": 3, "changed": 3}
    assert second == {"total": 3, "changed": 0}
