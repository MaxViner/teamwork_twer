"""Накопление относительной траектории.

Каждая успешная пара даёт вектор t. Аккумулятор складывает их и
хранит точки пути в условных единицах (до применения масштаба).
Это минимальная версия без loop closure и сшивки сцен.
"""

from __future__ import annotations


class TrajectoryAccumulator:
    """Суммирует относительные смещения в одну ломаную."""

    def __init__(self) -> None:
        """Начать траекторию в точке (0, 0, 0)."""

        self.reset()

    def reset(self) -> None:
        """Очистить накопленные точки."""

        self._position = [0.0, 0.0, 0.0]
        self._points: list[list[float]] = [[0.0, 0.0, 0.0]]
        self._frame_indices: list[int] = [0]

    def add(self, pose: dict) -> None:
        """Добавить позу с вектором t (относительное смещение)."""

        raw = pose.get("t") if isinstance(pose, dict) else None

        if raw is None:
            return

        try:
            values = [float(value) for value in raw]
        except (TypeError, ValueError):
            return

        if len(values) != 3:
            return

        self._position = [
            self._position[index] + values[index]
            for index in range(3)
        ]

        self._points.append(list(self._position))
        self._frame_indices.append(len(self._frame_indices))

    def build(self) -> dict:
        """Отдать точки траектории и номера кадров."""

        return {
            "points": [list(point) for point in self._points],
            "frame_indices": list(self._frame_indices),
        }
