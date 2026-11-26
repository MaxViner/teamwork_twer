"""Консолидированная стадия visual_analysis.

Один проход по ключевым кадрам объединяет четыре бывших стадии:

- visual_profile — метрики и словесное описание сцены;
- scene_objects — семантическая разметка SegFormer (или эвристики);
- object_detection — гео-улики Grounding DINO tiny + SAM2;
- faces — лица YuNet и анонимная кластеризация.

Результат сохраняет старые имена полей (frames[*].metrics,
frames[*].descriptors, frames[*].objects, profile, unique_objects,
people), чтобы потребители могли перейти на новый ключ
visual_analysis без потери данных. Новые поля — segments,
geo_clues, frame_summary, detections (старый формат), counts,
detector_error, face_available.

Файловых артефактов стадия не создаёт: кадры уже лежат в
runs/<run_id>/ и переиспользуются по artifact.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PIL import Image

from app.services.mediaService.frames import (
    analysis_frame_count,
    stage_frames,
)
from app.services.visualAnalysisService import detection, faces, segmentation
from app.services.visualAnalysisService.metrics import (
    aggregate_profile,
    analyze_frame,
    describe_metrics,
    observation_text,
)
from app.storage import StorageService
from app.utils.observations import observation


# Доли прогресса подэтапов, как в ТЗ.
METRICS_SHARE = 15.0
DETECTION_SHARE = 50.0
SEGMENTATION_SHARE = 30.0
FACES_SHARE = 5.0

# Детекция гео-улик теперь включает и SAM2, поэтому её доля
# прогресса остаётся самой большой.

MAX_ERROR_EXAMPLES = 20


def extract_visual_analysis(
    storage: StorageService,
    video: Path,
    duration: float,
    stages: dict,
    options: dict,
    progress: Callable[[float, str], None],
) -> dict:
    """Собрать визуальные улики по ключевым кадрам.

    Возвращает единый result стадии: кадры с метриками, сегментами,
    детекциями и лицами, а также сводный профиль, уникальные объекты,
    людей, наблюдения и счётчики.
    """

    count = analysis_frame_count(options)

    frames = stage_frames(
        folder=storage.folder,
        run_folder=storage.run_dir,
        video=video,
        duration=duration,
        stages=stages,
        count=count,
        prefix="visual",
    )

    if not frames:
        raise RuntimeError(
            "Не удалось получить кадры для визуального анализа."
        )

    timings: dict[str, int] = {}
    errors: list[dict] = []

    analyzed: list[dict] = []

    started = time.perf_counter()

    for index, frame in enumerate(frames):
        progress(
            index / len(frames) * METRICS_SHARE,
            f"Визуальные метрики: кадр {index + 1} из {len(frames)}",
        )

        try:
            metrics = analyze_frame(frame["path"])
            descriptors = describe_metrics(metrics)

            with Image.open(frame["path"]) as source:
                width, height = source.size

        except Exception as error:
            if len(errors) < MAX_ERROR_EXAMPLES:
                errors.append({
                    "timestamp": frame.get("timestamp"),
                    "error": str(error)[:1000],
                })

            continue

        analyzed.append({
            "timestamp": round(float(frame["timestamp"]), 3),
            "artifact": frame["artifact"],
            "path": frame["path"],
            "size": [int(width), int(height)],
            "metrics": metrics,
            "descriptors": descriptors,
            "segments": [],
            "objects": [],
            "geo_clues": [],
            "frame_summary": None,
            "detections": [],
            "faces": [],
        })

    if not analyzed:
        detail = errors[0]["error"] if errors else "нет данных"
        raise RuntimeError(
            "Не удалось проанализировать ни одного кадра. "
            + detail
        )

    timings["metrics"] = _elapsed_ms(started)

    started = time.perf_counter()
    clue_results = detection.detect_frames(
        analyzed,
        _scaled(progress, METRICS_SHARE, DETECTION_SHARE),
    )

    for frame, result in zip(analyzed, clue_results):
        frame["geo_clues"] = result.get("geo_clues") or []
        frame["frame_summary"] = result.get("frame_summary")
        frame["detections"] = result.get("detections") or []
        frame["geo_clue_error"] = result.get("error")
        frame["geo_clue_analyzed"] = bool(
            result.get("analyzed")
        )
        frame["geo_clue_image_size"] = result.get(
            "image_size"
        )

    timings["geo_clues"] = _elapsed_ms(started)

    started = time.perf_counter()
    segments_result = segmentation.extract_segments(
        analyzed,
        _scaled(
            progress,
            METRICS_SHARE + DETECTION_SHARE,
            SEGMENTATION_SHARE,
        ),
    )

    segments_by_artifact = _by_artifact(
        segments_result.get("frames") or [],
        "objects",
    )

    for frame in analyzed:
        objects = segments_by_artifact.get(
            _key(frame),
            [],
        )
        frame["objects"] = objects
        frame["segments"] = objects

    timings["segmentation"] = _elapsed_ms(started)

    started = time.perf_counter()
    face_available = faces.model_available()
    analyzed_faces: list[dict] = []
    face_total = 0

    if face_available:
        total = max(len(analyzed), 1)

        for index, frame in enumerate(analyzed):
            progress(
                METRICS_SHARE + DETECTION_SHARE + SEGMENTATION_SHARE
                + index / total * FACES_SHARE,
                f"Поиск лиц: кадр {index + 1} из {len(analyzed)}",
            )

            found = faces.detect_faces(frame["path"])

            if not found:
                continue

            face_total += len(found)
            analyzed_faces.append({
                "timestamp": frame["timestamp"],
                "artifact": frame["artifact"],
                "faces": found,
            })

    people = faces.cluster_faces(analyzed_faces) if analyzed_faces else []

    faces_by_artifact = _by_artifact(analyzed_faces, "faces")

    for frame in analyzed:
        frame["faces"] = faces_by_artifact.get(_key(frame), [])

    timings["faces"] = _elapsed_ms(started)

    for frame in analyzed:
        frame.pop("path", None)

    profile = aggregate_profile(analyzed)
    unique_objects = segmentation.unique_objects_from_frames(analyzed)
    unique_geo_clues = detection.unique_geo_clues_from_frames(analyzed)
    unique_detections = detection.unique_detections_from_frames(analyzed)

    counts = {
        "frames": len(analyzed),
        "geo_clues_total": sum(
            len(frame["geo_clues"]) for frame in analyzed
        ),
        "strong_clues_total": sum(
            sum(
                1
                for item in frame["geo_clues"]
                if item.get("match_priority") == "high"
            )
            for frame in analyzed
        ),
        "frames_with_geo_clues": sum(
            bool(frame["geo_clues"]) for frame in analyzed
        ),
        "detections_total": sum(
            len(frame["detections"]) for frame in analyzed
        ),
        "faces_total": face_total,
        "unique_classes": len(
            {item["label"] for item in unique_objects}
            | {item["label"] for item in unique_geo_clues}
        ),
    }

    observations = _build_observations(
        analyzed,
        profile,
        unique_objects,
        unique_geo_clues,
        people,
        face_available,
        face_total,
    )

    progress(100, "Визуальный анализ завершён")

    return {
        "frames": analyzed,
        "profile": profile,
        "unique_objects": unique_objects,
        "unique_geo_clues": unique_geo_clues,
        "unique_detections": unique_detections,
        "frame_summaries": [
            {
                "timestamp": frame["timestamp"],
                "artifact": frame["artifact"],
                **(frame["frame_summary"] or {}),
            }
            for frame in analyzed
            if frame.get("frame_summary")
        ],
        "people": people,
        "observations": observations,
        "counts": counts,
        "timings_ms": timings,
        "detector_available": detection.detector_available(),
        "detector_error": detection.detector_error(),
        "geo_clue_models": detection.model_status()
        if hasattr(detection, "model_status")
        else None,
        "face_available": face_available,
        "method": segments_result.get("method"),
        "model": segments_result.get("model"),
        "segmentation_error": segments_result.get("model_error"),
        "requested_frames": count,
        "sampled_frames": len(frames),
        "successful_frames": len(analyzed),
        "error_count": len(errors),
        "errors": errors,
        "segment_count": sum(
            len(frame["segments"]) for frame in analyzed
        ),
        "object_count": len(unique_objects),
        "category_count": len({
            item["category"] for item in unique_objects
        }),
        "person_count": len(people),
        "face_count": face_total,
        "frames_with_objects": sum(
            bool(frame["objects"]) for frame in analyzed
        ),
        "frames_with_faces": sum(
            bool(frame["faces"]) for frame in analyzed
        ),
        "note": (
            "Метрики, семантическая разметка, гео-улики "
            "(Grounding DINO + SAM2) и лица собраны в один проход. "
            "Это визуальные улики, а не подтверждённые координаты."
        ),
    }


def _build_observations(
    frames: list[dict],
    profile: dict,
    unique_objects: list[dict],
    unique_geo_clues: list[dict],
    people: list[dict],
    face_available: bool,
    face_total: int,
) -> list[dict]:
    """Сложить визуальные улики в наблюдения стадии."""

    if not frames:
        return []

    start = frames[0]["timestamp"]
    end = frames[-1]["timestamp"]
    observations: list[dict] = []

    if profile:
        observations.append(
            observation(
                source="visual_analysis",
                start=start,
                end=end,
                text=observation_text(profile),
                extractor="pillow-numpy-visual-profile",
                data={
                    "kind": "visual_profile_summary",
                    "profile": profile,
                    "sampled_frames": len(frames),
                    "machine_generated": True,
                    "requires_review": True,
                    "time_is_approximate": True,
                },
            )
        )

    if unique_objects:
        top = ", ".join(
            f"{item['label_ru']} ({item['frame_count']} кадр.)"
            for item in unique_objects[:8]
        )

        observations.append(
            observation(
                source="visual_analysis",
                start=start,
                end=end,
                text=(
                    f"Семантическая разметка: {len(unique_objects)} "
                    f"типов объектов. {top}."
                ),
                extractor="segformer-or-heuristics",
                data={
                    "kind": "scene_objects_summary",
                    "object_count": len(unique_objects),
                    "objects": unique_objects,
                    "machine_generated": True,
                    "requires_review": True,
                },
            )
        )

    if unique_geo_clues:
        strong = [
            item
            for item in unique_geo_clues
            if item.get("match_priority") == "high"
        ]
        top = ", ".join(
            f"{item['label_ru']} ({item['frame_count']} кадр.)"
            for item in unique_geo_clues[:8]
        )
        summaries = [
            frame.get("frame_summary")
            for frame in frames
            if frame.get("frame_summary")
        ]
        terrain = (
            summaries[0].get("dominant_terrain_ru")
            if summaries
            else None
        )

        observations.append(
            observation(
                source="visual_analysis",
                start=start,
                end=end,
                text=(
                    f"Гео-улики: {len(unique_geo_clues)} типов, "
                    f"из них сильных — {len(strong)}. {top}."
                    + (
                        f" Доминирующий ландшафт: {terrain}."
                        if terrain
                        else ""
                    )
                ),
                extractor="grounding-dino-tiny-sam2-hiera-tiny",
                data={
                    "kind": "geo_clue_summary",
                    "clue_count": len(unique_geo_clues),
                    "strong_clue_count": len(strong),
                    "dominant_terrain": terrain,
                    "geo_clues": unique_geo_clues,
                    "frame_summaries": summaries,
                    "machine_generated": True,
                    "requires_review": True,
                },
            )
        )

    if face_available:
        observations.append(
            observation(
                source="visual_analysis",
                start=start,
                end=end,
                text=faces.summary_text(
                    people,
                    face_total,
                    len(frames),
                ),
                extractor="opencv-yunet-faces",
                data={
                    "kind": "faces_summary",
                    "people": people,
                    "face_count": face_total,
                    "anonymous": True,
                },
            )
        )

    return observations


def _scaled(
    progress: Callable[[float, str], None],
    start: float,
    span: float,
) -> Callable[[float, str], None]:
    """Сдвинуть прогресс подэтапа в общий диапазон стадии."""

    def report(percent: float, message: str | None = None) -> None:
        value = max(0.0, min(100.0, float(percent)))
        progress(
            start + span * value / 100.0,
            message or "",
        )

    return report


def _key(frame: dict) -> str:
    """Ключ кадра для сопоставления результатов подэтапов."""

    artifact = frame.get("artifact")

    if artifact:
        return str(artifact)

    return f"t:{round(float(frame.get('timestamp') or 0), 3)}"


def _by_artifact(
    frames: list[dict],
    field: str,
) -> dict[str, list]:
    """Разложить поле кадров по artifact или таймкоду."""

    result: dict[str, list] = {}

    for frame in frames:
        result[_key(frame)] = list(frame.get(field) or [])

    return result


def _elapsed_ms(started: float) -> int:
    """Перевести прошедшее время в целые миллисекунды."""

    return int(round((time.perf_counter() - started) * 1000))
