"""Преобразование масок SAM2 в признаки географических улик.

Для каждой маски берётся наибольший контур, упрощается approxPolyDP
(epsilon = 0.005 * периметр) и превращается в полигон. Дополнительно
считаются два важных признака:

- visibility_fraction = площадь маски / площадь bbox. Значение 0.2–0.4
  не является ошибкой: объект есть, но скрыт листвой или другим
  объектом. Для геопривязки это ценная информация.
- shape_complexity = периметр² / (4π · площадь). Безразмерная мера:
  круг ≈ 1.0, простой прямоугольник ≈ 1.27, угловатое здание с
  мезонином — заметно больше. Она помогает отличить «простой куст»
  от сложной постройки.
"""

from __future__ import annotations

import math

import cv2
import numpy as np


EPSILON_RATIO = 0.005
MIN_CONTOUR_AREA = 16.0


def bbox_polygon(bbox) -> list[list[int]]:
    """Полигон из рамки — запасной вариант без SAM2."""

    x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)

    return [
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2],
    ]


def _bbox_area(bbox) -> float:
    x1, y1, x2, y2 = (float(value) for value in bbox)

    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _bbox_shape_complexity(bbox) -> float:
    """Сложность прямоугольника по той же формуле."""

    x1, y1, x2, y2 = (float(value) for value in bbox)
    width = max(1.0, x2 - x1)
    height = max(1.0, y2 - y1)
    perimeter = 2.0 * (width + height)
    area = width * height

    return perimeter * perimeter / (4.0 * math.pi * area)


def mask_to_features(
    mask: np.ndarray | None,
    bbox,
    image_size: tuple[int, int] | None = None,
) -> dict:
    """Собрать полигон, visibility_fraction и shape_complexity.

    mask — бинарная маска в пикселях исходного кадра (0/1 или 0/255).
    Если маска пустая или меньше рамки, используется рамка, а
    visibility_fraction остаётся 1.0: это честный запасной вариант,
    который видно по полю segmented=False.
    """

    bbox = [float(value) for value in bbox]
    fallback = {
        "polygon": bbox_polygon(bbox),
        "visibility_fraction": 1.0,
        "shape_complexity": round(
            _bbox_shape_complexity(bbox),
            2,
        ),
        "segmented": False,
        "mask_area": 0,
        "bbox_area": int(round(_bbox_area(bbox))),
    }

    if mask is None:
        return fallback

    mask = np.asarray(mask)

    if mask.ndim == 3:
        mask = mask.squeeze()

    if mask.ndim != 2 or mask.size == 0:
        return fallback

    if image_size is not None:
        width, height = image_size

        if mask.shape[:2] != (height, width):
            mask = cv2.resize(
                mask,
                (int(width), int(height)),
                interpolation=cv2.INTER_NEAREST,
            )

    binary = (mask > 0).astype(np.uint8) * 255
    bbox_area = _bbox_area(bbox)

    if bbox_area <= 0:
        return fallback

    # Ограничиваем маску рамкой: SAM2 иногда «протекает» на соседние
    # объекты, и тогда visibility_fraction становится больше 1.
    x1, y1, x2, y2 = (int(round(value)) for value in bbox)
    height, width = binary.shape[:2]
    x1 = max(0, min(width, x1))
    y1 = max(0, min(height, y1))
    x2 = max(0, min(width, x2))
    y2 = max(0, min(height, y2))

    if x2 <= x1 or y2 <= y1:
        return fallback

    clipped = np.zeros_like(binary)
    clipped[y1:y2, x1:x2] = binary[y1:y2, x1:x2]

    mask_area = int(cv2.countNonZero(clipped))

    if mask_area < MIN_CONTOUR_AREA:
        return fallback

    contours, _ = cv2.findContours(
        clipped,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    if not contours:
        return fallback

    contour = max(contours, key=cv2.contourArea)
    contour_area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))

    if contour_area < MIN_CONTOUR_AREA or perimeter <= 0:
        return fallback

    epsilon = max(1.0, EPSILON_RATIO * perimeter)
    approx = cv2.approxPolyDP(contour, epsilon, True)

    polygon = [
        [int(point[0][0]), int(point[0][1])]
        for point in approx
    ]

    if len(polygon) < 3:
        polygon = bbox_polygon(bbox)

    visibility = mask_area / bbox_area
    complexity = (
        perimeter * perimeter
        / (4.0 * math.pi * contour_area)
    )

    return {
        "polygon": polygon,
        "visibility_fraction": round(
            max(0.0, min(1.0, visibility)),
            3,
        ),
        "shape_complexity": round(
            max(1.0, min(12.0, complexity)),
            2,
        ),
        "segmented": True,
        "mask_area": mask_area,
        "bbox_area": int(round(bbox_area)),
    }
