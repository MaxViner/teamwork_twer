"""Накопление траектории камеры с учётом поворотов.

`recoverPose` даёт относительную позу второй камеры относительно
первой:

    X2 = R_rel · X1 + t_rel

Если складывать только `t_rel`, поворот камеры теряется: маршрут
начинает «уезжать» в сторону и перестаёт быть похож на реальное
движение. Поэтому аккумулятор хранит ориентацию камеры в мире
`R_w` и её центр `C`:

    R_w' = R_rel · R_w
    C'   = C - R_w'^T · t_rel

Начальная камера считается мировым началом координат:
`R_w = I`, `C = (0, 0, 0)`. Единицы условные: `t` из recoverPose
нормирован, поэтому каждый успешный шаг имеет длину 1. Это даёт
топологию маршрута, а не метрику.
"""

from __future__ import annotations

import math


def _identity() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def _as_matrix(value) -> list[list[float]] | None:
    """Проверить и привести матрицу 3×3 к списку списков float."""

    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None

    rows: list[list[float]] = []

    for row in value:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            return None

        try:
            rows.append([float(item) for item in row])

        except (TypeError, ValueError):
            return None

    return rows


def _as_vector(value) -> list[float] | None:
    """Проверить и привести вектор длины 3 к списку float."""

    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None

    try:
        return [float(item) for item in value]

    except (TypeError, ValueError):
        return None


def _transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [
        [matrix[column][row] for column in range(3)]
        for row in range(3)
    ]


def _matmul(
    left: list[list[float]],
    right: list[list[float]],
) -> list[list[float]]:
    return [
        [
            sum(left[row][k] * right[k][column] for k in range(3))
            for column in range(3)
        ]
        for row in range(3)
    ]


def _matvec(
    matrix: list[list[float]],
    vector: list[float],
) -> list[float]:
    return [
        sum(matrix[row][k] * vector[k] for k in range(3))
        for row in range(3)
    ]


def _distance(first: list[float], second: list[float]) -> float:
    return math.sqrt(
        sum((first[index] - second[index]) ** 2 for index in range(3))
    )


def _normalize_angle(angle: float) -> float:
    """Привести угол к диапазону (-180, 180]."""

    while angle <= -180.0:
        angle += 360.0

    while angle > 180.0:
        angle -= 360.0

    return angle


class TrajectoryAccumulator:
    """Собирает относительные позы в мировую ломаную камеры."""

    def __init__(self) -> None:
        """Начать траекторию в точке (0, 0, 0)."""

        self.reset()

    def reset(self) -> None:
        """Очистить накопленные точки и статистику."""

        self._rotation = _identity()
        self._position = [0.0, 0.0, 0.0]

        self._points: list[list[float]] = [[0.0, 0.0, 0.0]]
        self._frame_indices: list[int] = [0]
        self._headings: list[float] = [0.0]

        self._steps: list[float] = []
        self._turn_angles: list[float] = []

    def add(
        self,
        pose: dict,
        frame_index: int | None = None,
    ) -> bool:
        """Добавить относительную позу. True — точка добавлена."""

        if not isinstance(pose, dict):
            return False

        rotation = _as_matrix(pose.get("R"))
        translation = _as_vector(pose.get("t"))

        if rotation is None or translation is None:
            return False

        # R_w' = R_rel · R_w
        rotation_new = _matmul(rotation, self._rotation)

        # C' = C - R_w'^T · t_rel
        shift = _matvec(_transpose(rotation_new), translation)
        position = [
            self._position[index] - shift[index]
            for index in range(3)
        ]

        step = _distance(position, self._position)
        heading = self._heading(rotation_new)
        turn = _normalize_angle(heading - self._headings[-1])

        self._rotation = rotation_new
        self._position = position

        self._points.append(list(position))
        self._frame_indices.append(
            int(frame_index)
            if frame_index is not None
            else len(self._frame_indices)
        )
        self._headings.append(heading)
        self._steps.append(step)
        self._turn_angles.append(turn)

        return True

    def _heading(self, rotation: list[list[float]]) -> float:
        """Курс камеры в плоскости BEV (x-z), в градусах."""

        # Оптическая ось камеры — +Z в её системе координат.
        forward = _matvec(_transpose(rotation), [0.0, 0.0, 1.0])

        return math.degrees(math.atan2(forward[0], forward[2]))

    def build(self) -> dict:
        """Отдать точки, статистику пути и курсы."""

        points = [list(point) for point in self._points]
        path_length = float(sum(self._steps))

        displacement = (
            _distance(points[-1], points[0])
            if len(points) > 1
            else 0.0
        )

        mean_step = (
            path_length / len(self._steps)
            if self._steps
            else 0.0
        )

        max_step = max(self._steps) if self._steps else 0.0

        total_turn = float(
            sum(abs(angle) for angle in self._turn_angles)
        )

        net_turn = (
            _normalize_angle(self._headings[-1] - self._headings[0])
            if len(self._headings) > 1
            else 0.0
        )

        return {
            "points": points,
            "frame_indices": list(self._frame_indices),
            "headings_deg": [
                round(angle, 2) for angle in self._headings
            ],
            "path_length": round(path_length, 4),
            "displacement": round(displacement, 4),
            "mean_step": round(mean_step, 4),
            "max_step": round(max_step, 4),
            "total_turn_deg": round(total_turn, 2),
            "net_turn_deg": round(net_turn, 2),
            "units": "relative",
        }
