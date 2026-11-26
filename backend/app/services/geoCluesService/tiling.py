"""Тайлинг кадра для поиска мелких улик.

SAHI режет кадр на перекрывающиеся фрагменты, чтобы мелкая табличка
или фрагмент кладки не потерялись при уменьшении всего изображения.
Параметры из ТЗ: slice=640, overlap=0.2.

Если пакет sahi установлен, используется его slice_image; иначе
работает совместимый внутренний тайлер. Это важно для окружений,
где sahi ещё не установлен: модуль не должен падать.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np


SLICE_SIZE = 640
OVERLAP_RATIO = 0.2

USE_SAHI = os.getenv(
    "GEO_CLUES_USE_SAHI",
    "1",
).strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Tile:
    """Фрагмент кадра и его положение в исходном изображении."""

    image: np.ndarray
    x: int
    y: int
    width: int
    height: int


def _starts(length: int, slice_size: int, step: int) -> list[int]:
    """Начать с 0 и закончить ровно на краю изображения."""

    if length <= slice_size:
        return [0]

    starts = list(range(0, max(length - slice_size, 0) + 1, step))

    if not starts or starts[-1] != length - slice_size:
        starts.append(length - slice_size)

    return starts


def slices(
    image: np.ndarray,
    slice_size: int = SLICE_SIZE,
    overlap_ratio: float = OVERLAP_RATIO,
) -> list[Tile]:
    """Разрезать RGB/BGR-изображение на перекрывающиеся тайлы."""

    if image is None or not getattr(image, "size", 0):
        return []

    height, width = image.shape[:2]

    if height == 0 or width == 0:
        return []

    slice_size = max(64, int(slice_size))
    overlap_ratio = max(0.0, min(0.9, float(overlap_ratio)))

    if USE_SAHI:
        sahi_tiles = _sahi_slices(
            image,
            slice_size,
            overlap_ratio,
        )

        if sahi_tiles:
            return sahi_tiles

    step = max(1, int(round(slice_size * (1.0 - overlap_ratio))))

    result: list[Tile] = []

    for y in _starts(height, slice_size, step):
        for x in _starts(width, slice_size, step):
            x2 = min(width, x + slice_size)
            y2 = min(height, y + slice_size)

            crop = image[y:y2, x:x2]

            if crop.size == 0:
                continue

            result.append(Tile(
                image=crop,
                x=x,
                y=y,
                width=x2 - x,
                height=y2 - y,
            ))

    return result


def _sahi_slices(
    image: np.ndarray,
    slice_size: int,
    overlap_ratio: float,
) -> list[Tile] | None:
    """Использовать SAHI, если пакет установлен.

    SAHI даёт ту же сетку тайлов и удобен для совместимости с
    остальной экосистемой. Если пакета нет, вызывающий код
    переходит на внутренний тайлер.
    """

    try:
        from sahi.slicing import slice_image
    except Exception:
        return None

    try:
        sliced = slice_image(
            image=image,
            slice_height=slice_size,
            slice_width=slice_size,
            overlap_height_ratio=overlap_ratio,
            overlap_width_ratio=overlap_ratio,
            auto_slice_resolution=False,
        )
    except Exception:
        return None

    tiles: list[Tile] = []

    for crop, start in zip(
        sliced.images,
        sliced.starting_pixels,
    ):
        if crop is None or not getattr(crop, "size", 0):
            continue

        x, y = start
        height, width = crop.shape[:2]

        tiles.append(Tile(
            image=crop,
            x=int(x),
            y=int(y),
            width=int(width),
            height=int(height),
        ))

    return tiles
