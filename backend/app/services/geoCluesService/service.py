"""Сборка JSON с географическими уликами по кадру.

Пайплайн: тайлинг → Grounding DINO → дедупликация → SAM2 →
конвертер масок → описание и frame_summary.

Модуль можно использовать отдельно от видео: тестовый эндпоинт
принимает одно изображение и возвращает тот же формат.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from app.services.geoCluesService import (
    converter,
    detector as detector_module,
    dictionary,
    runtime,
    segmenter as segmenter_module,
    summary as summary_module,
)


MAX_FRAMES = int(os.getenv("GEO_CLUES_MAX_FRAMES", "24"))


def load_image(path: Path) -> tuple[np.ndarray, tuple[int, int]]:
    """Прочитать изображение как RGB и вернуть размер (w, h)."""

    with Image.open(path) as source:
        image = source.convert("RGB")
        width, height = image.size
        array = np.asarray(image)

    return array, (int(width), int(height))


def format_time(seconds) -> str:
    """Превратить секунды в mm:ss или h:mm:ss."""

    try:
        value = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return ""

    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


def detector_available() -> bool:
    """Загружена ли модель детектора (без принудительной загрузки)."""

    return runtime.detector_loaded()


def detector_error() -> str | None:
    return runtime.detector_error()


def status() -> dict:
    return runtime.status()


def reset() -> None:
    runtime.reset()


def analyze_frame(
    path: Path | None = None,
    *,
    image: np.ndarray | None = None,
    frame: int | None = None,
    time_value: str | None = None,
    progress: Callable[[float, str], None] | None = None,
    detector_fn: Callable[[np.ndarray], list[dict]] | None = None,
    segmenter_fn: Callable[
        [np.ndarray, list[list[float]]],
        list[np.ndarray] | None,
    ] | None = None,
) -> dict:
    """Найти улики на одном кадре и собрать JSON.

    detector_fn и segmenter_fn нужны для тестов: они позволяют
    проверить конвертер и сводку без скачивания моделей.
    """

    timings: dict[str, int] = {}
    error: str | None = None

    if image is None:
        if path is None:
            raise ValueError("Нужен path или image.")

        started = time.perf_counter()
        image, size = load_image(Path(path))
        timings["load"] = _elapsed_ms(started)

    else:
        image = np.asarray(image)

        if image.ndim == 2:
            image = np.stack([image] * 3, axis=-1)

        size = (int(image.shape[1]), int(image.shape[0]))

    started = time.perf_counter()

    try:
        if detector_fn is not None:
            raw = detector_fn(image)
        else:
            raw = detector_module.detect(image)

    except Exception as exc:
        raw = []
        error = f"Детектор гео-улик: {str(exc)[:500]}"

    timings["detector"] = _elapsed_ms(started)

    boxes = [
        item["bbox"]
        for item in raw
        if item.get("bbox")
    ]

    masks = None

    if boxes:
        started = time.perf_counter()

        try:
            if segmenter_fn is not None:
                masks = segmenter_fn(image, boxes)
            else:
                masks = segmenter_module.segment_boxes(
                    image,
                    boxes,
                )

        except Exception as exc:
            masks = None
            error = (
                error
                or f"Сегментатор гео-улик: {str(exc)[:500]}"
            )

        timings["segmenter"] = _elapsed_ms(started)

    clues: list[dict] = []

    for index, item in enumerate(raw):
        label = dictionary.canonical_label(
            item.get("label", "")
        )

        if label is None:
            continue

        bbox = [
            float(value)
            for value in item["bbox"]
        ]

        mask = None

        if masks is not None and index < len(masks):
            mask = masks[index]

        features = converter.mask_to_features(
            mask,
            bbox,
            image_size=size,
        )

        confidence = round(
            float(item.get("confidence") or 0.0),
            3,
        )
        visibility = float(
            features["visibility_fraction"]
        )
        complexity = float(
            features["shape_complexity"]
        )
        segmented = bool(features["segmented"])

        priority = summary_module.priority_for(
            label,
            confidence,
            visibility,
        )

        clues.append({
            "label": label,
            "label_ru": dictionary.label_ru(label),
            "confidence": confidence,
            "bbox": [
                round(value, 1)
                for value in bbox
            ],
            "polygon": features["polygon"],
            "visibility_fraction": visibility,
            "shape_complexity": complexity,
            "description": summary_module.describe_clue(
                label,
                confidence,
                visibility,
                complexity,
                segmented,
            ),
            "type": dictionary.clue_type(label),
            "match_priority": priority,
            "is_strong": priority == "high",
            "segmented": segmented,
            "mask_area": features["mask_area"],
            "bbox_area": features["bbox_area"],
        })

    clues.sort(key=lambda item: (
        dictionary.priority_rank(item["match_priority"]),
        -item["confidence"],
        -item["visibility_fraction"],
    ))

    if not raw and error is None:
        error = runtime.detector_error()

    frame_summary = (
        summary_module.frame_summary(clues)
        if clues
        else None
    )

    return {
        "frame": frame,
        "time": time_value,
        "image_size": [int(size[0]), int(size[1])],
        "geo_clues": clues,
        "frame_summary": frame_summary,
        "error": error,
        "timings_ms": timings,
        "models": {
            "detector": runtime.DETECTOR_MODEL_ID,
            "segmenter": runtime.SEGMENTER_MODEL_ID,
            "box_threshold": runtime.BOX_THRESHOLD,
            "text_threshold": runtime.TEXT_THRESHOLD,
        },
    }


def analyze_frames(
    frames: list[dict],
    progress: Callable[[float, str], None] | None = None,
    max_frames: int | None = None,
) -> list[dict]:
    """Прогнать несколько кадров и выровнять результат по входу.

    На CPU полный проход по сотням кадров слишком долгий, поэтому
    анализируется не больше max_frames равномерно выбранных кадров.
    Остальные получают пустые geo_clues и analyzed=False.
    """

    limit = max_frames if max_frames is not None else MAX_FRAMES
    total = len(frames)

    if total == 0:
        return []

    selected = _sample_indices(total, limit)
    results: list[dict] = [
        _empty_result(frame)
        for frame in frames
    ]

    for position, index in enumerate(selected):
        frame = frames[index]
        path = frame.get("path")

        if progress is not None:
            progress(
                position / max(len(selected), 1) * 100.0,
                f"Гео-улики: кадр {position + 1}/{len(selected)}",
            )

        if not path:
            continue

        try:
            analyzed = analyze_frame(
                Path(path),
                frame=index,
                time_value=format_time(
                    frame.get("timestamp")
                ),
            )

        except Exception as exc:
            results[index] = {
                **_empty_result(frame),
                "error": str(exc)[:500],
            }
            continue

        results[index] = {
            "timestamp": frame.get("timestamp"),
            "artifact": frame.get("artifact"),
            "analyzed": True,
            "geo_clues": analyzed["geo_clues"],
            "frame_summary": analyzed["frame_summary"],
            "detections": _legacy_detections(
                analyzed["geo_clues"]
            ),
            "error": analyzed.get("error"),
            "timings_ms": analyzed.get("timings_ms"),
            "image_size": analyzed.get("image_size"),
        }

    if progress is not None:
        progress(100.0, "Гео-улики: анализ кадров завершён")

    return results


def _sample_indices(total: int, limit: int) -> list[int]:
    if limit <= 0 or total <= limit:
        return list(range(total))

    indices = np.linspace(
        0,
        total - 1,
        num=limit,
    )

    return sorted({
        int(round(value))
        for value in indices
    })


def _empty_result(frame: dict) -> dict:
    return {
        "timestamp": frame.get("timestamp"),
        "artifact": frame.get("artifact"),
        "analyzed": False,
        "geo_clues": [],
        "frame_summary": None,
        "detections": [],
        "error": None,
        "timings_ms": None,
        "image_size": None,
    }


def _legacy_detections(clues: list[dict]) -> list[dict]:
    """Старый формат detections для odometry/BEV и старых job.json."""

    return [
        {
            "label": item["label"],
            "label_ru": item["label_ru"],
            "category": "geo_clue",
            "confidence": item["confidence"],
            "bbox": item["bbox"],
            "is_dynamic": False,
            "type": item["type"],
            "match_priority": item["match_priority"],
        }
        for item in clues
    ]


def unique_geo_clues(frames: list[dict]) -> list[dict]:
    """Собрать уникальные улики по всем кадрам."""

    collected: dict[str, dict] = {}

    for frame in frames:
        timestamp = frame.get("timestamp")

        if timestamp is None:
            continue

        timestamp = round(float(timestamp), 6)
        artifact = frame.get("artifact")

        for item in frame.get("geo_clues") or []:
            label = item.get("label")

            if not label:
                continue

            entry = collected.setdefault(label, {
                "label": label,
                "label_ru": item.get("label_ru", label),
                "type": item.get("type"),
                "match_priority": item.get("match_priority"),
                "frame_count": 0,
                "max_confidence": 0.0,
                "mean_confidence": 0.0,
                "max_visibility_fraction": 0.0,
                "mean_shape_complexity": 0.0,
                "best_frame": None,
                "best_timestamp": None,
                "best_polygon": None,
                "best_visibility_fraction": None,
                "best_shape_complexity": None,
                "best_image_size": None,
                "timestamps": [],
                "descriptions": [],
                "_confidence_sum": 0.0,
                "_complexity_sum": 0.0,
            })

            confidence = float(item.get("confidence") or 0)
            visibility = float(
                item.get("visibility_fraction") or 0
            )
            complexity = float(
                item.get("shape_complexity") or 0
            )

            entry["frame_count"] += 1
            entry["_confidence_sum"] += confidence
            entry["_complexity_sum"] += complexity
            entry["max_visibility_fraction"] = max(
                entry["max_visibility_fraction"],
                visibility,
            )
            entry["timestamps"].append(timestamp)

            description = item.get("description")

            if (
                description
                and description not in entry["descriptions"]
                and len(entry["descriptions"]) < 3
            ):
                entry["descriptions"].append(description)

            if confidence > entry["max_confidence"]:
                entry["max_confidence"] = confidence
                entry["best_frame"] = artifact
                entry["best_timestamp"] = timestamp
                entry["best_polygon"] = item.get("polygon")
                entry["best_visibility_fraction"] = visibility
                entry["best_shape_complexity"] = complexity
                entry["best_image_size"] = frame.get(
                    "geo_clue_image_size"
                )

            # Более сильная улика задаёт итоговый приоритет.
            if dictionary.priority_rank(
                item.get("match_priority", "low")
            ) < dictionary.priority_rank(
                entry.get("match_priority", "low")
            ):
                entry["match_priority"] = item.get(
                    "match_priority"
                )

    result = []

    for entry in collected.values():
        count = entry["frame_count"]

        entry["timestamps"] = sorted(set(
            entry["timestamps"]
        ))
        entry["frame_count"] = len(entry["timestamps"])
        entry["max_confidence"] = round(
            entry["max_confidence"],
            3,
        )
        entry["mean_confidence"] = round(
            entry["_confidence_sum"] / max(count, 1),
            3,
        )
        entry["mean_shape_complexity"] = round(
            entry["_complexity_sum"] / max(count, 1),
            2,
        )
        entry["max_visibility_fraction"] = round(
            entry["max_visibility_fraction"],
            3,
        )
        entry["is_strong"] = (
            entry.get("match_priority") == "high"
        )
        entry.pop("_confidence_sum", None)
        entry.pop("_complexity_sum", None)
        result.append(entry)

    result.sort(key=lambda item: (
        dictionary.priority_rank(
            item.get("match_priority", "low")
        ),
        -item["frame_count"],
        -item["max_confidence"],
        item["label"],
    ))

    return result


def _elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))
