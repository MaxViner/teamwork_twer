"""Одометрия для стадии place_profile.

Обёртка над odometryService: берёт последовательные кадры
visual_analysis, строит матрицу камеры по размеру кадра, вырезает
динамические объекты по YOLO-детекциям и накапливает относительную
траекторию.

Метрика приблизительная: t из recoverPose нормирован, поэтому
trajectory хранится в условных единицах, а scale — отдельная
осторожная оценка перевода в метры.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from app.services.odometryService.scale import estimate_scale
from app.services.odometryService.trajectory import TrajectoryAccumulator
from app.services.odometryService.visual_odometry import VisualOdometry
from app.utils.observations import observation


# Ограничение на число пар: 500 кадров × ~0.3 с — верхняя граница
# разумного времени для одной стадии на CPU.
MAX_PAIRS = 240


def extract_odometry(
    frames: list[dict],
    visual_result: dict,
    stages: dict,
    road_summary: dict | None,
    progress: Callable[[float, str], None],
) -> dict:
    """Оценить движение камеры между последовательными кадрами.

    Возвращает trajectory, pairs, scale и skipped с причинами.
    Недостаток кадров — не ошибка: результат будет пустым.
    """

    items = _frame_items(frames, visual_result)

    if len(items) < 2:
        return {
            "trajectory": {
                "points": [],
                "frame_indices": [],
                "units": "relative",
            },
            "pairs": [],
            "scale": estimate_scale(_device(stages), road_summary),
            "skipped": [],
            "pair_count": 0,
            "successful_pairs": 0,
            "skipped_pairs": 0,
            "observations": [],
            "note": (
                "Для одометрии нужно минимум два кадра; "
                "движение камеры не оценено."
            ),
        }

    step = max(1, (len(items) - 1) // MAX_PAIRS)
    indices = list(range(0, len(items) - 1, step))

    pairs: list[dict] = []
    skipped: list[dict] = []
    poses: list[dict] = []

    for order, index in enumerate(indices):
        first = items[index]
        second = items[min(index + step, len(items) - 1)]

        progress(
            order / max(len(indices), 1) * 99,
            f"Одометрия: пара {order + 1}/{len(indices)}",
        )

        odometry = VisualOdometry(
            _camera_matrix(first["size"]),
            _pair_mask(first, second),
        )

        result, reason = odometry.estimate_with_reason(
            first["path"],
            second["path"],
        )

        if result is None:
            skipped.append({
                "from": first["index"],
                "to": second["index"],
                "from_timestamp": first["timestamp"],
                "to_timestamp": second["timestamp"],
                "reason": reason or "degenerate",
            })
            continue

        pose = {
            "from": first["index"],
            "to": second["index"],
            "from_timestamp": first["timestamp"],
            "to_timestamp": second["timestamp"],
            "R": result["R"],
            "t": result["t"],
            "inliers": result["inliers"],
            "quality": result["quality"],
            "blur_a": result["blur_a"],
            "blur_b": result["blur_b"],
            "timings": dict(odometry.timings),
        }

        pairs.append(pose)
        poses.append(result)

    trajectory = _trajectory(poses, pairs, items)

    scale = estimate_scale(_device(stages), road_summary)

    progress(100, "Одометрия завершена")

    return {
        "trajectory": trajectory,
        "pairs": pairs,
        "scale": scale,
        "skipped": skipped,
        "pair_count": len(pairs) + len(skipped),
        "successful_pairs": len(pairs),
        "skipped_pairs": len(skipped),
        "observations": _build_observations(
            trajectory,
            pairs,
            skipped,
            scale,
        ),
        "note": (
            "Относительная траектория камеры без loop closure и "
            "точной метрики. t нормирован; scale — грубая оценка "
            "по устройству или ширине полосы."
        ),
    }


def _frame_items(
    frames: list[dict],
    visual_result: dict,
) -> list[dict]:
    """Собрать кадры с путями, размерами и детекциями."""

    detections = {
        str(frame.get("artifact")): frame.get("detections") or []
        for frame in visual_result.get("frames") or []
        if frame.get("artifact")
    }

    items = []

    for index, frame in enumerate(frames):
        path = frame.get("path")

        if not path:
            continue

        path = Path(path)

        if not path.is_file():
            continue

        try:
            with Image.open(path) as image:
                width, height = image.size

        except Exception:
            continue

        items.append({
            "index": index,
            "timestamp": round(float(frame["timestamp"]), 3),
            "artifact": frame.get("artifact"),
            "path": path,
            "size": (width, height),
            "detections": detections.get(str(frame.get("artifact")), []),
        })

    return items


def _camera_matrix(size: tuple[int, int]) -> np.ndarray:
    """Собрать правдоподобную K по размеру кадра."""

    width, height = size
    focal = 0.9 * max(width, height)

    return np.array(
        [
            [focal, 0.0, width / 2],
            [0.0, focal, height / 2],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _pair_mask(first: dict, second: dict):
    """Функция масок для VisualOdometry.

    VisualOdometry вызывает маску сначала для первого кадра, затем
    для второго. Замыкание отдаёт заранее подготовленные маски в
    этом же порядке и подгоняет их под рабочее разрешение.
    """

    masks = [
        _dynamic_mask(first),
        _dynamic_mask(second),
    ]
    state = {"index": 0}

    def provide(image: np.ndarray) -> np.ndarray:
        position = min(state["index"], len(masks) - 1)
        state["index"] += 1
        mask = masks[position]
        height, width = image.shape[:2]

        if mask.shape[:2] != (height, width):
            import cv2

            mask = cv2.resize(
                mask,
                (width, height),
                interpolation=cv2.INTER_NEAREST,
            )

        return mask

    return provide


def _dynamic_mask(item: dict) -> np.ndarray:
    """Маска 255/0 по детекциям динамических объектов."""

    width, height = item["size"]
    mask = np.full((height, width), 255, dtype=np.uint8)

    for detection in item.get("detections") or []:
        if not detection.get("is_dynamic"):
            continue

        bbox = detection.get("bbox")

        if not bbox or len(bbox) != 4:
            continue

        try:
            x1, y1, x2, y2 = (
                int(round(float(value)))
                for value in bbox
            )
        except (TypeError, ValueError):
            continue

        x1 = max(0, min(width, x1))
        y1 = max(0, min(height, y1))
        x2 = max(0, min(width, x2))
        y2 = max(0, min(height, y2))

        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 0

    return mask


def _trajectory(
    poses: list[dict],
    pairs: list[dict],
    items: list[dict],
) -> dict:
    """Накопить относительные смещения в ломаную."""

    accumulator = TrajectoryAccumulator()

    for pose in poses:
        accumulator.add(pose)

    built = accumulator.build()

    frame_indices = [items[0]["index"]] + [
        pair["to"] for pair in pairs
    ]

    built["frame_indices"] = frame_indices[: len(built["points"])]
    built["timestamps"] = (
        [items[0]["timestamp"]]
        + [pair["to_timestamp"] for pair in pairs]
    )[: len(built["points"])]
    built["units"] = "relative"
    built["pair_count"] = len(pairs)

    return built


def _device(stages: dict) -> str | None:
    """Достать модель устройства из metadata."""

    result = (stages.get("metadata") or {}).get("result") or {}
    device = result.get("device")

    return str(device) if device else None


def _build_observations(
    trajectory: dict,
    pairs: list[dict],
    skipped: list[dict],
    scale: dict,
) -> list[dict]:
    """Сложить одометрию в одно наблюдение place_profile."""

    if not pairs:
        return []

    quality = float(np.mean([
        pair["quality"] for pair in pairs
    ]))

    text = (
        f"Одометрия: успешных пар {len(pairs)}, "
        f"пропущено {len(skipped)}; "
        f"средняя доля инлайеров {quality:.2f}. "
        f"Масштаб: {scale.get('source')} "
        f"(×{scale.get('m_per_unit')})."
    )

    return [
        observation(
            source="place_profile",
            start=pairs[0]["from_timestamp"],
            end=pairs[-1]["to_timestamp"],
            text=text,
            extractor="orb-essential-matrix",
            data={
                "kind": "odometry_summary",
                "successful_pairs": len(pairs),
                "skipped_pairs": len(skipped),
                "mean_quality": round(quality, 3),
                "scale": scale,
                "trajectory_points": len(trajectory.get("points") or []),
                "requires_review": True,
                "map_match_ready": False,
            },
        )
    ]
