"""Детекция объектов YOLOv8n для стадии visual_analysis.

Модуль — тонкая обёртка над objectDetectionService.YoloDetector:
держит одну ONNX-сессию на процесс, гоняет кадры по одному (модель
экспортирована с фиксированным batch=1) и собирает уникальные
классы по всем кадрам.

Если onnxruntime или файл модели недоступны, детекция не валит
стадию: detections остаются пустыми, а причина попадает в
detector_error.
"""

from __future__ import annotations

from typing import Callable

from app.services.objectDetectionService.detector import YoloDetector


DETECTION_CATEGORY_ORDER = (
    "people",
    "transport",
    "animals",
    "street",
    "other",
)


DETECTION_CATEGORY = {
    "person": "people",
    "bicycle": "transport",
    "car": "transport",
    "motorcycle": "transport",
    "airplane": "transport",
    "bus": "transport",
    "train": "transport",
    "truck": "transport",
    "boat": "transport",
    "traffic light": "street",
    "fire hydrant": "street",
    "stop sign": "street",
    "parking meter": "street",
    "bench": "street",
    "bird": "animals",
    "cat": "animals",
    "dog": "animals",
    "horse": "animals",
    "sheep": "animals",
    "cow": "animals",
    "elephant": "animals",
    "bear": "animals",
    "zebra": "animals",
    "giraffe": "animals",
}


_DETECTOR: YoloDetector | None = None
_DETECTOR_ERROR: str | None = None


def detector_available() -> bool:
    """Проверить, удалось ли открыть ONNX-модель YOLO."""

    return _detector() is not None


def detector_error() -> str | None:
    """Вернуть причину, по которой детектор недоступен."""

    return _DETECTOR_ERROR


def reset_detector() -> None:
    """Сбросить кэш сессии — нужно тестам и повторным запускам."""

    global _DETECTOR, _DETECTOR_ERROR
    _DETECTOR = None
    _DETECTOR_ERROR = None


def detect_frames(
    frames: list[dict],
    progress: Callable[[float, str], None] | None = None,
) -> list[list[dict]]:
    """Найти объекты на каждом кадре.

    Возвращает список, выровненный по входным кадрам: при ошибке
    конкретного кадра на его месте пустой список.
    """

    detector = _detector()

    if detector is None:
        return [[] for _ in frames]

    results: list[list[dict]] = []
    total = max(len(frames), 1)

    for index, frame in enumerate(frames):
        if progress is not None:
            progress(
                index / total * 100,
                f"Детекция объектов: кадр {index + 1}/{len(frames)}",
            )

        path = frame.get("path")

        if not path:
            results.append([])
            continue

        try:
            results.append(detector.detect(path))

        except Exception:
            results.append([])

    if progress is not None:
        progress(100, "Детекция объектов завершена")

    return results


def unique_detections_from_frames(
    frames: list[dict],
) -> list[dict]:
    """Собрать уникальные классы YOLO по всем кадрам.

    Для каждого класса сохраняются число кадров, лучшая уверенность,
    средняя уверенность, лучший кадр и таймкоды.
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
                "label_ru": label,
                "category": DETECTION_CATEGORY.get(
                    label,
                    "other",
                ),
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
        DETECTION_CATEGORY_ORDER.index(item["category"])
        if item["category"] in DETECTION_CATEGORY_ORDER
        else len(DETECTION_CATEGORY_ORDER),
        -item["frame_count"],
        -item["max_confidence"],
        item["label"],
    ))

    return result


def _detector() -> YoloDetector | None:
    """Лениво открыть общий детектор YOLO."""

    global _DETECTOR, _DETECTOR_ERROR

    if _DETECTOR is not None:
        return _DETECTOR

    if _DETECTOR_ERROR is not None:
        return None

    try:
        _DETECTOR = YoloDetector()

    except Exception as error:
        _DETECTOR_ERROR = str(error)[:500]
        return None

    return _DETECTOR
