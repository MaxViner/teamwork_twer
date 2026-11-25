"""Рендер топологической BEV-карты в PNG.

Рисует сетку, коридор дороги, траекторию и объекты. Подписи —
латинские метки классов; кириллица в cv2.putText не поддерживается.
PNG пишется через imencode/tofile, чтобы работали пути с кириллицей.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


CANVAS_SIZE = 800
GRID_COLOR = (225, 225, 225)
ROAD_COLOR = (205, 205, 205)
TRAJECTORY_COLOR = (200, 90, 20)
TEXT_COLOR = (60, 60, 60)

OBJECT_COLORS = (
    (40, 160, 60),
    (180, 90, 40),
    (40, 90, 200),
    (160, 40, 160),
    (30, 160, 180),
    (90, 90, 220),
)


def render_bev_png(bev: dict, output_path: Path) -> Path:
    """Нарисовать BEV и сохранить PNG. Возвращает путь файла."""

    grid = bev.get("grid") or {}
    rows = max(1, int(grid.get("rows") or 100))
    cols = max(1, int(grid.get("cols") or 100))

    canvas = np.full(
        (CANVAS_SIZE, CANVAS_SIZE, 3),
        250,
        dtype=np.uint8,
    )

    _draw_grid(canvas, rows, cols)
    _draw_road(canvas, bev.get("road_mask") or [], rows, cols)
    _draw_trajectory(
        canvas,
        bev.get("trajectory") or [],
        rows,
        cols,
    )
    _draw_objects(
        canvas,
        bev.get("objects") or [],
        rows,
        cols,
    )

    cv2.putText(
        canvas,
        "Topological BEV, no metric",
        (16, CANVAS_SIZE - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        TEXT_COLOR,
        1,
        cv2.LINE_AA,
    )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    ok, encoded = cv2.imencode(".png", canvas)

    if not ok:
        raise RuntimeError("Не удалось закодировать BEV в PNG.")

    encoded.tofile(str(path))

    return path


def _cell_to_pixel(
    col: float,
    row: float,
    rows: int,
    cols: int,
) -> tuple[int, int]:
    """Перевести координаты ячейки в пиксели холста."""

    x = int(col / max(cols - 1, 1) * (CANVAS_SIZE - 1))
    y = int(row / max(rows - 1, 1) * (CANVAS_SIZE - 1))

    return x, y


def _draw_grid(
    canvas: np.ndarray,
    rows: int,
    cols: int,
) -> None:
    """Нарисовать сетку каждые 10 ячеек."""

    step = 10

    for col in range(0, cols, step):
        x, _ = _cell_to_pixel(col, 0, rows, cols)
        cv2.line(canvas, (x, 0), (x, CANVAS_SIZE - 1), GRID_COLOR, 1)

    for row in range(0, rows, step):
        _, y = _cell_to_pixel(0, row, rows, cols)
        cv2.line(canvas, (0, y), (CANVAS_SIZE - 1, y), GRID_COLOR, 1)


def _draw_road(
    canvas: np.ndarray,
    road_mask: list[list[int]],
    rows: int,
    cols: int,
) -> None:
    """Закрасить ячейки дорожного коридора."""

    for row_index, row in enumerate(road_mask):
        for col_index, value in enumerate(row):
            if not value:
                continue

            x1, y1 = _cell_to_pixel(col_index, row_index, rows, cols)
            x2, y2 = _cell_to_pixel(
                col_index + 1,
                row_index + 1,
                rows,
                cols,
            )

            cv2.rectangle(
                canvas,
                (x1, y1),
                (x2, y2),
                ROAD_COLOR,
                -1,
            )


def _draw_trajectory(
    canvas: np.ndarray,
    trajectory: list[list[int]],
    rows: int,
    cols: int,
) -> None:
    """Нарисовать траекторию синей ломаной."""

    if len(trajectory) < 2:
        return

    points = np.array([
        _cell_to_pixel(col, row, rows, cols)
        for col, row in trajectory
    ], dtype=np.int32)

    cv2.polylines(
        canvas,
        [points],
        isClosed=False,
        color=TRAJECTORY_COLOR,
        thickness=3,
        lineType=cv2.LINE_AA,
    )

    cv2.circle(
        canvas,
        tuple(points[0]),
        6,
        (40, 160, 60),
        -1,
    )
    cv2.circle(
        canvas,
        tuple(points[-1]),
        6,
        (40, 40, 200),
        -1,
    )


def _draw_objects(
    canvas: np.ndarray,
    objects: list[dict],
    rows: int,
    cols: int,
) -> None:
    """Нарисовать объекты точками и подписать классы."""

    for index, item in enumerate(objects):
        label = str(item.get("label") or "object")
        color = OBJECT_COLORS[index % len(OBJECT_COLORS)]
        cells = item.get("cells") or []

        for col, row in cells:
            x, y = _cell_to_pixel(col, row, rows, cols)
            cv2.circle(canvas, (x, y), 4, color, -1)

        if cells:
            x, y = _cell_to_pixel(
                cells[0][0],
                cells[0][1],
                rows,
                cols,
            )
            cv2.putText(
                canvas,
                label[:16],
                (x + 6, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1,
                cv2.LINE_AA,
            )
