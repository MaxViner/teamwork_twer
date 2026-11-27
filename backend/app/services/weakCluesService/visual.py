"""Слабые визуальные улики: фенология и стек повторяющихся объектов.

Один и тот же знак, столб или ограждение попадает в десятки кадров.
Модуль группирует такие детекции по метке и времени, складывает
кадры (ECC/фазовая корреляция + медиана) и распознаёт текст уже на
стеке. Дополнительно по метрикам кадров считается фенологическая
фаза.

Модуль ничего не решает о координатах: он отдаёт наблюдения,
которые затем агрегируются в location_evidence.
"""

from __future__ import annotations

from collections import defaultdict

from app.services.weakCluesService import (
    infrastructure,
    phenology,
    stacking,
)


# Метки geoCluesService, для которых имеет смысл стек и OCR.
STACK_LABELS: tuple[str, ...] = (
    "road sign or post",
    "kilometer post",
    "utility pole",
    "metal utility pole",
    "culvert",
    "guardrail",
)

# Пауза между кадрами, после которой начинается новая группа.
GROUP_GAP_SECONDS = 4.0

MIN_STACK_FRAMES = 3
MAX_GROUPS = 5

SLUGS = {
    "road sign or post": "sign",
    "kilometer post": "km_post",
    "utility pole": "pole",
    "metal utility pole": "pole_metal",
    "culvert": "culvert",
    "guardrail": "guardrail",
}


def analyze(
    frames: list[dict],
    storage=None,
    *,
    created_at=None,
    latitude: float | None = None,
) -> dict:
    """Собрать фенологию, стеки и километровые столбы.

    frames — кадры visual_analysis с полями path, timestamp,
    geo_clues и artifact. storage нужен только для сохранения
    артефактов стека; без него текст всё равно распознаётся.
    """

    result = {
        "phenology": None,
        "stacked_readings": [],
        "km_post_clues": [],
        "stack_groups": 0,
        "stack_errors": [],
    }

    try:
        result["phenology"] = phenology.analyze_frames(
            frames,
            created_at=created_at,
            latitude=latitude,
        )
    except Exception as error:  # noqa: BLE001
        result["stack_errors"].append(
            f"phenology: {str(error)[:200]}"
        )

    groups = _groups(frames)

    for index, group in enumerate(groups[:MAX_GROUPS]):
        if len(group["frames"]) < MIN_STACK_FRAMES:
            continue

        result["stack_groups"] += 1

        try:
            readings, clues = _process_group(
                group,
                index,
                storage,
            )
        except Exception as error:  # noqa: BLE001
            result["stack_errors"].append(
                f"{group['label']}: {str(error)[:200]}"
            )
            continue

        result["stacked_readings"].extend(readings)
        result["km_post_clues"].extend(clues)

    return result


def _groups(frames: list[dict]) -> list[dict]:
    """Сгруппировать детекции по метке и разрыву во времени."""

    by_label: dict[str, list[dict]] = defaultdict(list)

    for frame in frames:
        path = frame.get("path")
        timestamp = float(frame.get("timestamp") or 0.0)

        if not path:
            continue

        best: dict[str, dict] = {}

        for clue in frame.get("geo_clues") or []:
            label = clue.get("label")
            bbox = clue.get("bbox")

            if label not in STACK_LABELS or not bbox:
                continue

            confidence = float(clue.get("confidence") or 0.0)
            current = best.get(label)

            if current is None or confidence > current["confidence"]:
                best[label] = {
                    "label": label,
                    "timestamp": timestamp,
                    "path": path,
                    "bbox": [float(value) for value in bbox],
                    "confidence": confidence,
                    "artifact": frame.get("artifact"),
                }

        for entry in best.values():
            by_label[entry["label"]].append(entry)

    groups = []

    for label, items in by_label.items():
        items.sort(key=lambda item: item["timestamp"])
        current = [items[0]]

        for item in items[1:]:
            gap = item["timestamp"] - current[-1]["timestamp"]

            if gap > GROUP_GAP_SECONDS:
                groups.append({"label": label, "frames": current})
                current = [item]
            else:
                current.append(item)

        groups.append({"label": label, "frames": current})

    groups.sort(
        key=lambda group: (
            -len(group["frames"]),
            group["frames"][0]["timestamp"],
        ),
    )

    return groups


def _process_group(
    group: dict,
    index: int,
    storage,
) -> tuple[list[dict], list[dict]]:
    """Сложить кадры группы и распознать текст на стеке."""

    paths = [item["path"] for item in group["frames"]]
    boxes = [item["bbox"] for item in group["frames"]]
    stacked = stacking.stack_and_ocr(
        paths,
        boxes,
        min_frames=MIN_STACK_FRAMES,
    )

    if stacked.get("image") is None:
        return [], []

    artifact = None

    if storage is not None:
        try:
            path = storage.run_path(
                f"stack_{SLUGS.get(group['label'], 'object')}_{index}.png"
            )
            stacking.save_stack(stacked["image"], path)
            artifact = storage.relative(path)
        except Exception:  # noqa: BLE001
            artifact = None

    timestamp = group["frames"][0]["timestamp"]
    frame_artifact = group["frames"][0].get("artifact")
    readings = []
    clues = []

    for item in stacked.get("text") or []:
        score = float(item.get("score") or 0.0)
        confidence = round(min(0.9, max(0.35, score + 0.15)), 3)

        reading = {
            "label": group["label"],
            "text": item["text"],
            "score": round(score, 3),
            "confidence": confidence,
            "timestamp": timestamp,
            "artifact": artifact,
            "frame_artifact": frame_artifact,
            "stack_frames": stacked.get("used"),
            "sharpness": stacked.get("sharpness"),
        }
        readings.append(reading)

        clue = infrastructure.km_post_clue(
            item["text"],
            confidence=confidence,
            timestamp=timestamp,
            artifact=artifact,
            frame_artifact=frame_artifact,
        )

        if clue:
            clues.append(clue)

    return readings, clues


__all__ = [
    "GROUP_GAP_SECONDS",
    "MAX_GROUPS",
    "MIN_STACK_FRAMES",
    "STACK_LABELS",
    "analyze",
]
