"""Топологическая BEV-проекция (v2): маршрут и ключевые якоря.

Версия v1 рисовала все детекции всех кадров: на длинном видео это
давало «кашу» из точек, по которой нельзя было понять место. Версия
v2 оставляет на карте только то, что действительно помогает
геопривязке:

- маршрут камеры (тонкий коридор дороги);
- небольшое число сильных якорей — домов, фундаментов, мостов,
  промышленных труб и природных ориентиров.

Слабые улики (столбы, знаки, кусты) на карту не попадают: они
перегружают её и не помогают сузить район. Каждый якорь
привязывается к ближайшей точке маршрута по времени кадра, а его
боковое смещение и «глубина» оцениваются по положению рамки в кадре.
Это по-прежнему топология, а не метрика: масштаб условный.
"""

from __future__ import annotations

import math

import numpy as np

GRID_SIZE = 100
DEFAULT_CELL_M = 0.5
MARGIN_CELLS = 6

# Максимум якорей на карте. Больше — снова каша.
MAX_ANCHORS = 12

# Боковое смещение якоря от маршрута в ячейках.
LATERAL_CELLS = 7.0

# Якоря одного типа ближе этого расстояния считаются одним объектом.
MERGE_CELLS = 7.0

# Сильные типы улик. Приоритет high важнее типа, но этот набор
# используется, когда у старой детекции нет match_priority.
STRONG_TYPES = {
    "building_ruin",
    "natural_landmark",
    "industrial",
    "bridge",
}

TYPE_COLORS = {
    "building_ruin": (60, 90, 210),
    "natural_landmark": (50, 150, 60),
    "industrial": (180, 90, 40),
    "bridge": (160, 60, 160),
    "water": (200, 150, 40),
    "other": (90, 90, 90),
}


def build_bev(
    trajectory: dict,
    detections_per_frame: list[dict],
    road_segments: list[dict],
    camera_height_m: float = 1.2,
    cell_size_m: float = 0.5,
    max_anchors: int = MAX_ANCHORS,
) -> dict | None:
    """Построить карту «маршрут + ключевые якоря».

    Возвращает None, если в траектории меньше трёх точек или все
    точки совпали. Иначе — сетку, 2D-маршрут, якоря, тонкий коридор
    дороги и пометку «без метрики».
    """

    points = trajectory.get("points") or []

    if len(points) < 3:
        return None

    projected = _project(points)

    if len(projected) < 3:
        return None

    rows = GRID_SIZE
    cols = GRID_SIZE

    normalized, units_per_cell = _normalize(projected, rows, cols)

    if units_per_cell is None:
        return None

    timestamps = trajectory.get("timestamps") or []
    frame_indices = trajectory.get("frame_indices") or []

    anchors, ignored = _anchors(
        normalized,
        detections_per_frame,
        timestamps,
        frame_indices,
        rows,
        cols,
        max_anchors=max_anchors,
    )

    road_mask = _road_mask(
        normalized,
        road_segments,
        timestamps,
        rows,
        cols,
    )

    return {
        "schema_version": 2,
        "mode": "anchors",
        "grid": {
            "cell_size_m": float(cell_size_m or DEFAULT_CELL_M),
            "rows": rows,
            "cols": cols,
            "units_per_cell": round(units_per_cell, 5),
        },
        "trajectory": normalized,
        "trajectory_stats": {
            "points": len(normalized),
            "path_length": trajectory.get("path_length"),
            "displacement": trajectory.get("displacement"),
            "total_turn_deg": trajectory.get("total_turn_deg"),
            "net_turn_deg": trajectory.get("net_turn_deg"),
            "headings_deg": trajectory.get("headings_deg") or [],
            "units": "relative",
        },
        "anchors": anchors,
        "anchor_count": len(anchors),
        "ignored_clue_count": ignored,
        # Совместимость со старым фронтендом: objects теперь — якоря,
        # а не все детекции.
        "objects": [
            {
                "label": item["label"],
                "label_ru": item.get("label_ru"),
                "cells": [item["cell"]],
                "frame_count": item.get("frame_count", 1),
                "confidence": item.get("confidence"),
                "match_priority": item.get("match_priority"),
                "type": item.get("type"),
            }
            for item in anchors
        ],
        "road_mask": road_mask,
        "scale_source": "relative_units",
        "camera_height_m": float(camera_height_m),
        "note": (
            "Топологическая карта: маршрут и только сильные якоря. "
            "Масштаб условный, координаты не метрические."
        ),
    }


def _project(points: list) -> list[list[float]]:
    """Спроецировать 3D-точки на плоскость с наибольшим разбросом."""

    array = np.asarray(points, dtype=float)

    if array.ndim != 2 or array.shape[1] < 2:
        return []

    if array.shape[1] == 2:
        return array.tolist()

    axes = [0, 2]

    variance_y = float(np.var(array[:, 1])) if array.shape[1] > 1 else 0.0
    variance_z = float(np.var(array[:, 2])) if array.shape[1] > 2 else 0.0

    # Для бокового движения z почти не меняется: тогда берём y.
    if variance_z < max(variance_y, 1e-9) * 0.05:
        axes = [0, 1]

    return array[:, axes].tolist()


def _normalize(
    points: list[list[float]],
    rows: int,
    cols: int,
) -> tuple[list[list[int]], float | None]:
    """Вписать точки в сетку с сохранением пропорций.

    Оси масштабируются одинаково, поэтому короткий маршрут занимает
    малую часть карты, а поворот остаётся поворотом.

    Возвращает (точки, единиц_на_ячейку). Второе значение — None,
    если все точки совпали.
    """

    array = np.asarray(points, dtype=float)

    x = array[:, 0]
    y = array[:, 1]

    min_x, max_x = float(x.min()), float(x.max())
    min_y, max_y = float(y.min()), float(y.max())

    span_x = max_x - min_x
    span_y = max_y - min_y
    span = max(span_x, span_y)

    if span <= 1e-9:
        return [], None

    usable_cols = max(1, cols - 2 * MARGIN_CELLS)
    usable_rows = max(1, rows - 2 * MARGIN_CELLS)
    usable = max(1, min(usable_cols, usable_rows) - 1)

    scale = usable / span
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    center_col = (cols - 1) / 2.0
    center_row = (rows - 1) / 2.0

    result = []

    for px, py in zip(x, y):
        col = center_col + (px - center_x) * scale
        # Экранная ось Y растёт вниз; для карты разворачиваем.
        row = center_row - (py - center_y) * scale

        result.append([
            max(0, min(cols - 1, int(round(col)))),
            max(0, min(rows - 1, int(round(row)))),
        ])

    return result, 1.0 / scale


def _nearest_index(
    timestamps: list,
    moment,
    fallback: int,
    total_frames: int,
    count: int,
) -> int:
    """Найти точку траектории, ближайшую по времени к кадру."""

    usable = min(len(timestamps), count)

    if usable and moment is not None:
        try:
            target = float(moment)

        except (TypeError, ValueError):
            target = None

        if target is not None:
            return min(
                range(usable),
                key=lambda index: abs(float(timestamps[index]) - target),
            )

    return min(
        count - 1,
        max(0, int(fallback / max(total_frames, 1) * count)),
    )


def _clues_of(frame: dict) -> list[dict]:
    """Достать улики кадра в новом или старом формате."""

    clues = frame.get("geo_clues")

    if isinstance(clues, list) and clues:
        return clues

    legacy = frame.get("detections")

    if not isinstance(legacy, list):
        return []

    return [
        item
        for item in legacy
        if item.get("match_priority") or item.get("type")
    ]


def _is_strong(clue: dict) -> bool:
    """Оставить только сильные якоря."""

    priority = str(clue.get("match_priority") or "").lower()

    if priority == "high":
        return True

    if priority in {"medium", "low"}:
        return False

    return str(clue.get("type") or "") in STRONG_TYPES


def _anchors(
    trajectory: list[list[int]],
    detections_per_frame: list[dict],
    timestamps: list,
    frame_indices: list,
    rows: int,
    cols: int,
    max_anchors: int,
) -> tuple[list[dict], int]:
    """Собрать компактный набор сильных якорей.

    Возвращает (якоря, число отброшенных улик). Якоря одного типа
    сливаются, если оказались рядом: дом, видимый в десяти кадрах,
    должен остаться одним домом, а не десятью точками.
    """

    if not detections_per_frame or not trajectory:
        return [], 0

    total_frames = max(len(detections_per_frame), 1)
    collected: dict[str, list[dict]] = {}
    ignored = 0

    for index, frame in enumerate(detections_per_frame):
        clues = _clues_of(frame)

        if not clues:
            continue

        position_index = _nearest_index(
            timestamps,
            frame.get("timestamp"),
            index,
            total_frames,
            len(trajectory),
        )
        position = trajectory[position_index]
        tangent = _tangent(trajectory, position_index)

        size = frame.get("size") or []

        for clue in clues:
            if not _is_strong(clue):
                ignored += 1
                continue

            bbox = clue.get("bbox")

            if not bbox or len(bbox) != 4:
                ignored += 1
                continue

            if not _valid_bbox(bbox):
                ignored += 1
                continue

            anchor = _anchor_cell(
                position,
                tangent,
                bbox,
                size,
                rows,
                cols,
            )

            label = str(clue.get("label") or "clue")
            entry = {
                "label": label,
                "label_ru": clue.get("label_ru") or label,
                "type": clue.get("type") or "other",
                "match_priority": clue.get("match_priority") or "high",
                "confidence": float(clue.get("confidence") or 0.0),
                "visibility_fraction": clue.get(
                    "visibility_fraction"
                ),
                "shape_complexity": clue.get("shape_complexity"),
                "timestamp": frame.get("timestamp"),
                "artifact": frame.get("artifact"),
                "frame_index": _frame_number(frame_indices, position_index),
                "cell": anchor["cell"],
                "radius_cells": anchor["radius"],
                "bbox": [round(float(value), 1) for value in bbox],
                "frame_count": 1,
                "timestamps": [frame.get("timestamp")],
            }

            merged = False

            for existing in collected.setdefault(label, []):
                if _cell_distance(
                    existing["cell"],
                    entry["cell"],
                ) <= MERGE_CELLS:
                    _merge_anchor(existing, entry)
                    merged = True
                    break

            if not merged:
                collected[label].append(entry)

    anchors = [
        item
        for items in collected.values()
        for item in items
    ]

    anchors.sort(key=lambda item: (
        _priority_rank(item.get("match_priority")),
        -float(item.get("confidence") or 0.0),
        -int(item.get("frame_count") or 1),
    ))

    return anchors[:max(1, int(max_anchors))], ignored


def _valid_bbox(bbox) -> bool:
    try:
        x1, y1, x2, y2 = (float(value) for value in bbox)
    except (TypeError, ValueError):
        return False

    return x2 > x1 and y2 > y1


def _tangent(
    trajectory: list[list[int]],
    index: int,
) -> tuple[float, float]:
    """Направление маршрута в точке, в координатах сетки."""

    if len(trajectory) < 2:
        return 0.0, -1.0

    first = trajectory[max(0, index - 1)]
    second = trajectory[min(len(trajectory) - 1, index + 1)]

    dx = float(second[0] - first[0])
    dy = float(second[1] - first[1])
    length = math.hypot(dx, dy)

    if length <= 1e-9:
        return 0.0, -1.0

    return dx / length, dy / length


def _anchor_cell(
    position: list[int],
    tangent: tuple[float, float],
    bbox,
    size,
    rows: int,
    cols: int,
) -> dict:
    """Разместить якорь рядом с маршрутом по его рамке в кадре."""

    x1, y1, x2, y2 = (float(value) for value in bbox)

    width = float(size[0]) if len(size) == 2 and size[0] else 0.0
    height = float(size[1]) if len(size) == 2 and size[1] else 0.0

    if width > 0 and height > 0:
        center_x = (x1 + x2) / 2.0 / width
        bottom = y2 / height
        area_ratio = (
            max(0.0, x2 - x1) * max(0.0, y2 - y1)
            / (width * height)
        )
    else:
        center_x = 0.5
        bottom = 1.0
        area_ratio = 0.02

    # Боковое смещение: объект слева/справа от оптической оси.
    lateral = max(-1.0, min(1.0, (center_x - 0.5) * 2.0))
    lateral *= LATERAL_CELLS

    # Чем выше объект в кадре, тем он дальше: сдвигаем вперёд
    # по направлению маршрута.
    forward = max(0.5, min(4.5, (1.0 - bottom) * 7.0))

    # Нормаль к маршруту.
    normal_x = -tangent[1]
    normal_y = tangent[0]

    col = (
        position[0]
        + normal_x * lateral
        + tangent[0] * forward
    )
    row = (
        position[1]
        + normal_y * lateral
        + tangent[1] * forward
    )

    radius = max(
        1.5,
        min(5.0, math.sqrt(max(area_ratio, 0.0001)) * 45.0),
    )

    return {
        "cell": [
            max(0, min(cols - 1, int(round(col)))),
            max(0, min(rows - 1, int(round(row)))),
        ],
        "radius": round(radius, 2),
    }


def _merge_anchor(existing: dict, incoming: dict) -> None:
    """Слить два наблюдения одного и того же якоря."""

    existing["frame_count"] = int(
        existing.get("frame_count") or 1
    ) + 1
    existing.setdefault("timestamps", []).extend(
        incoming.get("timestamps") or []
    )

    if float(incoming.get("confidence") or 0.0) > float(
        existing.get("confidence") or 0.0
    ):
        existing["confidence"] = incoming["confidence"]
        existing["bbox"] = incoming["bbox"]
        existing["timestamp"] = incoming.get("timestamp")
        existing["artifact"] = incoming.get("artifact")
        existing["frame_index"] = incoming.get("frame_index")
        existing["cell"] = incoming["cell"]

    existing_visibility = existing.get("visibility_fraction")
    incoming_visibility = incoming.get("visibility_fraction")

    if incoming_visibility is not None and (
        existing_visibility is None
        or float(incoming_visibility) > float(existing_visibility)
    ):
        existing["visibility_fraction"] = incoming_visibility


def _cell_distance(first: list[int], second: list[int]) -> float:
    return math.hypot(
        float(first[0]) - float(second[0]),
        float(first[1]) - float(second[1]),
    )


def _priority_rank(value) -> int:
    return {
        "high": 0,
        "medium": 1,
        "low": 2,
    }.get(str(value or "").lower(), 3)


def _frame_number(frame_indices: list, position_index: int) -> int | None:
    if 0 <= position_index < len(frame_indices):
        try:
            return int(frame_indices[position_index])
        except (TypeError, ValueError):
            return None

    return None


def _road_mask(
    trajectory: list[list[int]],
    road_segments: list[dict],
    frame_indices: list,
    rows: int,
    cols: int,
) -> list[list[int]]:
    """Отметить тонкий коридор вокруг маршрута.

    В v2 коридор занимает одну ячейку по бокам, а не 3×3: карта
    должна показывать маршрут, а не закрашивать пол-экрана.
    """

    mask = [[0 for _ in range(cols)] for _ in range(rows)]

    if not trajectory:
        return mask

    episodes = road_segments or []

    if episodes:
        active = set()

        for episode in episodes:
            start = episode.get("start")
            end = episode.get("end")

            for position, moment in enumerate(frame_indices):
                if moment is None:
                    continue

                if start is not None and end is not None:
                    if float(start) <= float(moment) <= float(end):
                        active.add(position)

        selected = [
            trajectory[index]
            for index in sorted(active)
            if index < len(trajectory)
        ] or trajectory
    else:
        selected = trajectory

    for col, row in selected:
        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            x = max(0, min(cols - 1, col + dx))
            y = max(0, min(rows - 1, row + dy))
            mask[y][x] = 1

    return mask
