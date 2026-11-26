"""Рендер anchor-BEV в PNG.

Карта v2 показывает маршрут и небольшое число сильных якорей.
Слабые улики и «облако» детекций не рисуются: именно они делали
прошлую карту нечитаемой. Подписи — латинские метки; кириллица в
cv2.putText не поддерживается. PNG пишется через imencode/tofile,
чтобы работали пути с кириллицей.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from app.services.bevService.projection import TYPE_COLORS


CANVAS_SIZE = 800
GRID_COLOR = (232, 232, 232)
ROAD_COLOR = (214, 214, 214)
TRAJECTORY_COLOR = (200, 90, 20)
TEXT_COLOR = (60, 60, 60)
MUTED_COLOR = (140, 140, 140)


def render_bev_png(bev: dict, output_path: Path) -> Path:
    """Нарисовать маршрут и якоря, сохранить PNG."""

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
    _draw_anchors(
        canvas,
        bev.get("anchors") or [],
        rows,
        cols,
    )

    anchors = bev.get("anchors") or []

    if anchors:
        caption = (
            f"Anchor BEV: {len(anchors)} key landmark(s), "
            "route only, no metric"
        )
    else:
        caption = (
            "Anchor BEV: route only, no strong landmarks, no metric"
        )

    cv2.putText(
        canvas,
        caption,
        (16, CANVAS_SIZE - 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
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
    """Нарисовать редкую сетку каждые 20 ячеек."""

    step = 20

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
    """Закрасить тонкий коридор маршрута."""

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
    """Нарисовать маршрут оранжевой ломаной."""

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
        thickness=4,
        lineType=cv2.LINE_AA,
    )

    cv2.circle(canvas, tuple(points[0]), 7, (40, 160, 60), -1)
    cv2.circle(canvas, tuple(points[-1]), 7, (40, 40, 200), -1)

    cv2.putText(
        canvas,
        "start",
        (points[0][0] + 9, points[0][1] + 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (40, 140, 60),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "end",
        (points[-1][0] + 9, points[-1][1] + 4),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (40, 40, 180),
        1,
        cv2.LINE_AA,
    )


def _draw_anchors(
    canvas: np.ndarray,
    anchors: list[dict],
    rows: int,
    cols: int,
) -> None:
    """Нарисовать якоря кругами с подписями и легендой."""

    if not anchors:
        return

    for index, item in enumerate(anchors):
        cell = item.get("cell") or [0, 0]
        x, y = _cell_to_pixel(cell[0], cell[1], rows, cols)
        color = TYPE_COLORS.get(
            str(item.get("type") or "other"),
            TYPE_COLORS["other"],
        )
        radius = int(
            max(8, min(28, float(item.get("radius_cells") or 2) * 6))
        )

        cv2.circle(canvas, (x, y), radius, color, 2, cv2.LINE_AA)
        cv2.circle(canvas, (x, y), 4, color, -1, cv2.LINE_AA)

        label = str(item.get("label") or "clue")[:18]
        cv2.putText(
            canvas,
            f"{index + 1}. {label}",
            (x + radius + 4, y + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )

    _draw_legend(canvas, anchors)


def _draw_legend(canvas: np.ndarray, anchors: list[dict]) -> None:
    """Короткая легенда: номер, метка, уверенность."""

    x = 14
    y = 24

    cv2.putText(
        canvas,
        "Key landmarks:",
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        TEXT_COLOR,
        1,
        cv2.LINE_AA,
    )

    for index, item in enumerate(anchors[:8]):
        y += 20
        color = TYPE_COLORS.get(
            str(item.get("type") or "other"),
            TYPE_COLORS["other"],
        )
        label = str(item.get("label") or "clue")[:24]
        confidence = float(item.get("confidence") or 0.0)

        cv2.putText(
            canvas,
            f"{index + 1}. {label} ({confidence:.2f})",
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            color,
            1,
            cv2.LINE_AA,
        )

    if len(anchors) > 8:
        cv2.putText(
            canvas,
            f"+{len(anchors) - 8} more",
            (x, y + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            MUTED_COLOR,
            1,
            cv2.LINE_AA,
        )
