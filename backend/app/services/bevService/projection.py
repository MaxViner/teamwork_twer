"""Топологическая BEV-проекция (v1).

Строит карту сверху по относительной траектории и детекциям. Это не
метрическая реконструкция: масштаб условный, гомография не
восстанавливает точные мировые координаты. Задача v1 — показать
порядок движения и примерное расположение объектов относительно
маршрута.

Вход:
- trajectory: {"points": [[x, y, z], ...], ...};
- detections_per_frame: список кадров с detections (bbox в пикселях);
- road_segments: эпизоды дороги (start/end);
- camera_height_m, cell_size_m — номинальные параметры сетки.

Выход: grid, trajectory (2D), objects, road_mask, scale_source, note.
"""

from __future__ import annotations

import numpy as np

GRID_SIZE = 100
DEFAULT_CELL_M = 0.5
MARGIN_CELLS = 6


def build_bev(
    trajectory: dict,
    detections_per_frame: list[dict],
    road_segments: list[dict],
    camera_height_m: float = 1.2,
    cell_size_m: float = 0.5,
) -> dict | None:
    """Построить топологическую BEV-сетку.

    Возвращает None, если в траектории меньше трёх точек. Иначе —
    словарь с сеткой, 2D-траекторией, объектами, маской дороги и
    пометкой «без метрики».
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
        # Точки совпали: движения нет, карту строить не из чего.
        return None

    objects = _objects(
        normalized,
        detections_per_frame,
        trajectory.get("timestamps") or [],
        rows,
        cols,
    )

    road_mask = _road_mask(
        normalized,
        road_segments,
        trajectory.get("timestamps") or [],
        rows,
        cols,
    )

    return {
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
        "objects": objects,
        "road_mask": road_mask,
        "scale_source": "relative_units",
        "camera_height_m": float(camera_height_m),
        "note": "Топологическая карта, без метрики",
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

    Раньше оси масштабировались независимо, поэтому любой маршрут
    растягивался на всю сетку и терял форму. Теперь используется
    единый масштаб и центрирование: короткий путь занимает малую
    часть карты, поворот виден как поворот.

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


def _objects(
    trajectory: list[list[int]],
    detections_per_frame: list[dict],
    timestamps: list,
    rows: int,
    cols: int,
) -> list[dict]:
    """Разместить детекции рядом с точкой маршрута своего кадра."""

    if not detections_per_frame or not trajectory:
        return []

    total_frames = max(len(detections_per_frame), 1)
    collected: dict[str, dict] = {}

    for index, frame in enumerate(detections_per_frame):
        size = frame.get("size") or []
        detections = frame.get("detections") or []

        if not detections:
            continue

        position = trajectory[
            _nearest_index(
                timestamps,
                frame.get("timestamp"),
                index,
                total_frames,
                len(trajectory),
            )
        ]

        for detection in detections:
            bbox = detection.get("bbox")

            if not bbox or len(bbox) != 4:
                continue

            x1, y1, x2, y2 = (float(value) for value in bbox)

            if len(size) == 2 and size[1]:
                # Только объекты у нижней трети кадра похожи на
                # стоящие на земле; остальные пропускаем.
                if y2 < float(size[1]) * 0.66:
                    continue

                center_x = (x1 + x2) / 2 / max(float(size[0]), 1)
            else:
                center_x = 0.5

            label = str(detection.get("label") or "object")

            entry = collected.setdefault(label, {
                "label": label,
                "cells": [],
                "source_frame": index,
            })

            cell = _object_cell(
                position,
                center_x,
                rows,
                cols,
            )

            if cell not in entry["cells"]:
                entry["cells"].append(cell)

    return list(collected.values())


def _object_cell(
    position: list[int],
    center_x: float,
    rows: int,
    cols: int,
) -> list[int]:
    """Сместить объект вбок от траектории по его X в кадре."""

    offset = int(round((center_x - 0.5) * 10))
    col = position[0] + offset
    row = position[1] + 1

    return [
        max(0, min(cols - 1, col)),
        max(0, min(rows - 1, row)),
    ]


def _road_mask(
    trajectory: list[list[int]],
    road_segments: list[dict],
    frame_indices: list,
    rows: int,
    cols: int,
) -> list[list[int]]:
    """Отметить коридор вокруг траектории как вероятную дорогу."""

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
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                x = max(0, min(cols - 1, col + dx))
                y = max(0, min(rows - 1, row + dy))
                mask[y][x] = 1

    return mask
