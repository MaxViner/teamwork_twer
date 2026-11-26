"""Гео-улики для стадии visual_analysis.

Тонкая обёртка над geoCluesService: держит единый формат для стадии
и сохраняет старые имена функций, которые использовали odometry и
BEV. YOLO здесь больше нет: детекция заменена на Grounding DINO tiny
с тайлингом SAHI-стиля, сегментация — на SAM2.1 hiera tiny.

Если модели недоступны, кадры получают пустые geo_clues, а причина
попадает в detector_error. Стадия из-за этого не падает.
"""

from __future__ import annotations

from typing import Callable

from app.services.geoCluesService import (
    analyze_frames as _analyze_frames,
    detector_available as _detector_available,
    detector_error as _detector_error,
    reset as _reset,
    status as _status,
    unique_geo_clues as _unique_geo_clues,
)


def detector_available() -> bool:
    """Загружен ли детектор гео-улик."""

    return _detector_available()


def detector_error() -> str | None:
    """Причина, по которой детектор недоступен."""

    return _detector_error()


def reset_detector() -> None:
    """Сбросить кэш моделей — нужно тестам и повторным запускам."""

    _reset()


def model_status() -> dict:
    """Состояние Grounding DINO и SAM2 для отчёта и тестов."""

    return _status()


def detect_frames(
    frames: list[dict],
    progress: Callable[[float, str], None] | None = None,
) -> list[dict]:
    """Найти гео-улики на кадрах.

    Возвращает список, выровненный по входным кадрам. Для каждого
    кадра: geo_clues, frame_summary, detections (старый формат),
    analyzed и error.
    """

    return _analyze_frames(
        frames,
        progress=progress,
    )


def unique_geo_clues_from_frames(
    frames: list[dict],
) -> list[dict]:
    """Собрать уникальные гео-улики по всем кадрам."""

    return _unique_geo_clues(frames)


def unique_detections_from_frames(
    frames: list[dict],
) -> list[dict]:
    """Старый формат сводки детекций для совместимости.

    Новый фронтенд читает unique_geo_clues; старые потребители
    (и старые job.json) продолжают получать label/confidence/bbox.
    """

    collected: dict[str, dict] = {}

    for frame in frames:
        timestamp = frame.get("timestamp")

        if timestamp is None:
            continue

        timestamp = round(float(timestamp), 6)
        artifact = frame.get("artifact")

        for item in frame.get("detections") or []:
            label = item.get("label")

            if not label:
                continue

            entry = collected.setdefault(label, {
                "label": label,
                "label_ru": item.get("label_ru", label),
                "category": "geo_clue",
                "is_dynamic": bool(item.get("is_dynamic")),
                "frame_count": 0,
                "max_confidence": 0.0,
                "mean_confidence": 0.0,
                "best_frame": None,
                "best_timestamp": None,
                "timestamps": [],
                "_confidence_sum": 0.0,
            })

            confidence = float(item.get("confidence") or 0)

            entry["frame_count"] += 1
            entry["_confidence_sum"] += confidence
            entry["timestamps"].append(timestamp)

            if confidence > entry["max_confidence"]:
                entry["max_confidence"] = confidence
                entry["best_frame"] = artifact
                entry["best_timestamp"] = timestamp

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
        entry.pop("_confidence_sum", None)
        result.append(entry)

    result.sort(key=lambda item: (
        -item["frame_count"],
        -item["max_confidence"],
        item["label"],
    ))

    return result
