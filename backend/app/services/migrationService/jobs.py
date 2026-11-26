"""Идемпотентная миграция job.json на консолидированные этапы.

Старые задания хранят результаты в scene_objects, visual_profile,
faces, road_geometry, landmarks и ai_prompt. Новый интерфейс и
отчёты читают visual_analysis, place_profile и location_prompt.

Миграция не удаляет старые результаты: она добавляет новые этапы,
переносит в них объединённые данные и очищает старые observations,
чтобы одни и те же улики не дублировались в списке наблюдений.
Повторный запуск ничего не меняет.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.config import DATA_DIR, JOB_FILENAME


VISUAL_SOURCES = ("scene_objects", "visual_profile", "faces")
PLACE_SOURCES = ("road_geometry", "landmarks")
PROMPT_SOURCES = ("ai_prompt",)


def _stage_state() -> dict:
    return {
        "status": "pending",
        "run_id": None,
        "result_run_id": None,
        "result": {},
        "observations": [],
        "history": [],
        "error": None,
        "note": None,
    }


def _completed(job: dict, name: str) -> dict:
    stage = (job.get("stages") or {}).get(name) or {}

    if stage.get("status") not in ("completed", "partial"):
        return {}

    result = stage.get("result")

    return result if isinstance(result, dict) else {}


def _observations(job: dict, names) -> list[dict]:
    collected = []

    for name in names:
        stage = (job.get("stages") or {}).get(name) or {}

        for item in stage.get("observations") or []:
            if isinstance(item, dict):
                collected.append(dict(item))

    return collected


def _rewrite_observations(items: list[dict], source: str) -> list[dict]:
    return [
        {**item, "source": source}
        for item in items
    ]


def _time_key(value) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _merge_visual_frames(
    visual: dict,
    scene: dict,
    faces: dict,
) -> list[dict]:
    collected: dict[float, dict] = {}

    def ensure(timestamp) -> dict | None:
        key = _time_key(timestamp)

        if key is None:
            return None

        return collected.setdefault(key, {
            "timestamp": key,
            "artifact": None,
            "metrics": {},
            "descriptors": {},
            "segments": [],
            "objects": [],
            "geo_clues": [],
            "frame_summary": None,
            "detections": [],
            "faces": [],
        })

    for frame in visual.get("frames") or []:
        if not isinstance(frame, dict):
            continue

        entry = ensure(frame.get("timestamp"))

        if entry is None:
            continue

        if frame.get("artifact"):
            entry["artifact"] = frame["artifact"]

        if isinstance(frame.get("metrics"), dict):
            entry["metrics"] = frame["metrics"]

        if isinstance(frame.get("descriptors"), dict):
            entry["descriptors"] = frame["descriptors"]

    for frame in scene.get("frames") or []:
        if not isinstance(frame, dict):
            continue

        entry = ensure(frame.get("timestamp"))

        if entry is None:
            continue

        if frame.get("artifact"):
            entry["artifact"] = frame["artifact"]

        if isinstance(frame.get("objects"), list):
            entry["objects"] = frame["objects"]
            entry["segments"] = frame["objects"]

    for frame in faces.get("frames") or []:
        if not isinstance(frame, dict):
            continue

        entry = ensure(frame.get("timestamp"))

        if entry is None:
            continue

        if frame.get("artifact"):
            entry["artifact"] = frame["artifact"]

        if isinstance(frame.get("faces"), list):
            entry["faces"] = frame["faces"]

    return [collected[key] for key in sorted(collected)]


def build_visual_analysis(job: dict) -> dict:
    """Собрать visual_analysis из трёх старых этапов."""
    scene = _completed(job, "scene_objects")
    visual = _completed(job, "visual_profile")
    faces = _completed(job, "faces")

    frames = _merge_visual_frames(visual, scene, faces)
    unique_objects = scene.get("unique_objects") or []
    people = faces.get("people") or []
    profile = visual.get("profile") or {}

    counts = {
        "frames": len(frames),
        "geo_clues_total": 0,
        "strong_clues_total": 0,
        "frames_with_geo_clues": 0,
        "detections_total": 0,
        "faces_total": faces.get("face_count") or 0,
        "unique_classes": len({
            item.get("label")
            for item in unique_objects
            if isinstance(item, dict) and item.get("label")
        }),
    }

    return {
        "frames": frames,
        "profile": profile,
        "unique_objects": unique_objects,
        "unique_geo_clues": [],
        "unique_detections": [],
        "frame_summaries": [],
        "people": people,
        "observations": _rewrite_observations(
            _observations(job, VISUAL_SOURCES),
            "visual_analysis",
        ),
        "counts": counts,
        "timings_ms": {},
        "detector_available": False,
        "detector_error": None,
        "face_available": bool(faces),
        "method": scene.get("method") or visual.get("method"),
        "model": scene.get("model") or visual.get("model"),
        "segmentation_error": scene.get("model_error"),
        "requested_frames": scene.get("requested_frames") or visual.get("requested_frames"),
        "sampled_frames": scene.get("sampled_frames") or visual.get("sampled_frames") or len(frames),
        "successful_frames": scene.get("successful_frames") or len(frames),
        "error_count": scene.get("error_count") or 0,
        "errors": scene.get("errors") or [],
        "segment_count": scene.get("segment_count") or 0,
        "object_count": scene.get("object_count") or len(unique_objects),
        "category_count": scene.get("category_count") or 0,
        "person_count": len(people),
        "face_count": faces.get("face_count") or 0,
        "frames_with_objects": scene.get("frames_with_objects") or 0,
        "frames_with_faces": faces.get("frames_with_faces") or 0,
        "note": (
            "Данные перенесены из scene_objects, visual_profile и faces "
            "идемпотентной миграцией."
        ),
    }


def build_place_profile(job: dict) -> dict:
    """Собрать place_profile из road_geometry и landmarks."""
    road = _completed(job, "road_geometry")
    landmarks = _completed(job, "landmarks")

    geometry = landmarks.get("geometry") or {}

    return {
        "road": {
            key: value
            for key, value in road.items()
            if key != "observations"
        },
        "geometry": geometry,
        "geometry_frames": landmarks.get("frames") or [],
        "geometry_frame_count": (
            landmarks.get("frame_count_total")
            or landmarks.get("frame_count")
            or 0
        ),
        "landmarks": landmarks.get("landmarks") or [],
        "landmark_count": landmarks.get("landmark_count")
        or len(landmarks.get("landmarks") or []),
        "odometry": {
            "trajectory": {
                "points": [],
                "frame_indices": [],
                "units": "relative",
            },
            "pairs": [],
            "scale": {},
            "skipped": [],
            "pair_count": 0,
            "successful_pairs": 0,
            "skipped_pairs": 0,
            "note": "Одометрия появилась после миграции; перезапустите этап.",
        },
        "bev": None,
        "observations": _rewrite_observations(
            _observations(job, PLACE_SOURCES),
            "place_profile",
        ),
        "note": (
            "Данные перенесены из road_geometry и landmarks "
            "идемпотентной миграцией."
        ),
    }


def build_location_prompt(job: dict) -> dict:
    """Собрать location_prompt из ai_prompt."""
    prompt = _completed(job, "ai_prompt")

    return {
        **prompt,
        "observations": _rewrite_observations(
            _observations(job, PROMPT_SOURCES),
            "location_prompt",
        ),
        "note": prompt.get("note") or (
            "Промпт перенесён из ai_prompt идемпотентной миграцией."
        ),
    }


def _set_new_stage(job: dict, name: str, result: dict, sources) -> bool:
    stages = job.setdefault("stages", {})

    if name in stages:
        return False

    observations = result.get("observations") or []
    stored = {
        key: value
        for key, value in result.items()
        if key != "observations"
    }

    state = _stage_state()
    state.update(
        status="completed",
        result=stored,
        observations=observations,
        note=result.get("note"),
    )
    stages[name] = state

    # Старые observations уже перенесены в новый этап; очищаем их,
    # чтобы список наблюдений не дублировался. Результаты остаются.
    for source in sources:
        old = stages.get(source)

        if isinstance(old, dict):
            old["observations"] = []

    return True


def _migrate_options(job: dict) -> bool:
    options = job.get("options")

    if not isinstance(options, dict):
        return False

    changed = False

    if "visual_analysis" not in options:
        options["visual_analysis"] = any(
            bool(options.get(name, True))
            for name in VISUAL_SOURCES
        )
        changed = True

    if "place_profile" not in options:
        options["place_profile"] = any(
            bool(options.get(name, True))
            for name in PLACE_SOURCES
        )
        changed = True

    if "location_prompt" not in options:
        options["location_prompt"] = bool(options.get("ai_prompt", True))
        changed = True

    return changed


def migrate_job(job: dict) -> bool:
    """Привести одно задание к новой схеме. True — если что-то изменено."""
    changed = False

    stages = job.get("stages")

    if not isinstance(stages, dict):
        return False

    if "visual_analysis" not in stages and any(
        name in stages for name in VISUAL_SOURCES
    ):
        result = build_visual_analysis(job)
        changed = _set_new_stage(
            job,
            "visual_analysis",
            result,
            VISUAL_SOURCES,
        ) or changed

    if "place_profile" not in stages and any(
        name in stages for name in PLACE_SOURCES
    ):
        result = build_place_profile(job)
        changed = _set_new_stage(
            job,
            "place_profile",
            result,
            PLACE_SOURCES,
        ) or changed

    if "location_prompt" not in stages and any(
        name in stages for name in PROMPT_SOURCES
    ):
        result = build_location_prompt(job)
        changed = _set_new_stage(
            job,
            "location_prompt",
            result,
            PROMPT_SOURCES,
        ) or changed

    changed = _migrate_options(job) or changed

    return changed


def migrate_folder(folder: Path, dry_run: bool = False) -> bool:
    """Мигрировать один job.json. True — если файл изменён."""
    path = Path(folder) / JOB_FILENAME

    if not path.is_file():
        return False

    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = migrate_job(payload)

    if changed and not dry_run:
        backup = path.with_suffix(".json.bak")
        shutil.copy2(path, backup)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return changed


def migrate_all(
    data_dir: Path | None = None,
    dry_run: bool = False,
) -> dict:
    """Обойти все задания. Возвращает счётчики для CLI и тестов."""
    root = Path(data_dir or DATA_DIR)
    total = 0
    changed = 0

    if not root.is_dir():
        return {"total": 0, "changed": 0}

    for folder in sorted(root.iterdir()):
        if not folder.is_dir():
            continue

        total += 1

        if migrate_folder(folder, dry_run=dry_run):
            changed += 1

    return {"total": total, "changed": changed}
