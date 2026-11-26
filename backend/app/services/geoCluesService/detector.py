"""Детекция гео-улик: Grounding DINO tiny + тайлинг.

Модель получает словарь улик и возвращает рамки, метки и уверенность.
Кадр режется на перекрывающиеся тайлы 640×640 (overlap 0.2), чтобы
не потерять мелкие объекты. После переноса рамок в координаты
исходного кадра дубли на стыках тайлов удаляются: сравниваются
рамки одной и той же улики по IoU и по вложенности.

Пороги из ТЗ: box_threshold=0.35, text_threshold=0.35.
"""

from __future__ import annotations

import os
import time
from typing import Callable

import numpy as np
from PIL import Image

from app.services.geoCluesService import dictionary, runtime
from app.services.geoCluesService.tiling import (
    OVERLAP_RATIO,
    SLICE_SIZE,
    Tile,
    slices,
)


MAX_TILES = int(os.getenv("GEO_CLUES_MAX_TILES", "36"))

MIN_BOX_SIDE = 6.0

IOU_DUPLICATE = 0.45
CONTAINMENT_DUPLICATE = 0.75


def _area(box) -> float:
    x1, y1, x2, y2 = (float(value) for value in box)
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _intersection(first, second) -> float:
    ax1, ay1, ax2, ay2 = (float(value) for value in first)
    bx1, by1, bx2, by2 = (float(value) for value in second)

    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))

    return width * height


def _iou(first, second) -> float:
    intersection = _intersection(first, second)

    if intersection <= 0:
        return 0.0

    union = _area(first) + _area(second) - intersection

    return intersection / union if union > 0 else 0.0


def _containment(first, second) -> float:
    """Доля меньшей рамки, попавшая в большую."""

    intersection = _intersection(first, second)

    if intersection <= 0:
        return 0.0

    smaller = min(_area(first), _area(second))

    return intersection / smaller if smaller > 0 else 0.0


def _is_duplicate(first: dict, second: dict) -> bool:
    if first["label"] != second["label"]:
        return False

    return (
        _iou(first["bbox"], second["bbox"]) >= IOU_DUPLICATE
        or _containment(
            first["bbox"],
            second["bbox"],
        ) >= CONTAINMENT_DUPLICATE
    )


def dedupe(detections: list[dict]) -> list[dict]:
    """Убрать повторы одной улики на стыках тайлов."""

    ordered = sorted(
        detections,
        key=lambda item: -float(item.get("confidence") or 0.0),
    )

    kept: list[dict] = []

    for item in ordered:
        if any(_is_duplicate(item, existing) for existing in kept):
            continue

        kept.append(item)

    return kept


def _adaptive_tiles(image: np.ndarray) -> list[Tile]:
    """Тайлить кадр, не превышая лимит по памяти."""

    slice_size = SLICE_SIZE

    for _ in range(4):
        tiles = slices(
            image,
            slice_size=slice_size,
            overlap_ratio=OVERLAP_RATIO,
        )

        if len(tiles) <= MAX_TILES:
            return tiles

        slice_size = int(round(slice_size * 1.5))

    return tiles


def _label_from_result(
    result: dict,
    index: int,
) -> str | None:
    labels = result.get("text_labels") or result.get("labels") or []

    if index >= len(labels):
        return None

    return dictionary.canonical_label(labels[index])


def detect(
    image: np.ndarray,
    progress: Callable[[float, str], None] | None = None,
    box_threshold: float = runtime.BOX_THRESHOLD,
    text_threshold: float = runtime.TEXT_THRESHOLD,
) -> list[dict]:
    """Найти гео-улики на RGB-изображении.

    Возвращает список словарей с полями label, confidence, bbox,
    tile_index. Пустой список означает либо отсутствие улик, либо
    недоступность модели — причина доступна через runtime.
    """

    loaded = runtime.load_detector()

    if loaded is None:
        return []

    processor, model = loaded
    tiles = _adaptive_tiles(image)

    if not tiles:
        return []

    import torch

    prompt = dictionary.PROMPT_TEXT
    collected: list[dict] = []

    with torch.inference_mode():
        for index, tile in enumerate(tiles):
            if progress is not None:
                progress(
                    index / max(len(tiles), 1) * 100.0,
                    f"Гео-улики: тайл {index + 1}/{len(tiles)}",
                )

            tile_image = Image.fromarray(tile.image)

            try:
                inputs = processor(
                    images=tile_image,
                    text=prompt,
                    return_tensors="pt",
                )
                outputs = model(**inputs)
                result = (
                    processor
                    .post_process_grounded_object_detection(
                        outputs,
                        input_ids=inputs.get("input_ids"),
                        threshold=box_threshold,
                        text_threshold=text_threshold,
                        target_sizes=[
                            (tile.height, tile.width),
                        ],
                    )[0]
                )

            except Exception:
                continue

            scores = result.get("scores")
            boxes = result.get("boxes")

            if scores is None or boxes is None:
                continue

            for item_index, (score, box) in enumerate(
                zip(scores.tolist(), boxes.tolist())
            ):
                label = _label_from_result(
                    result,
                    item_index,
                )

                if label is None:
                    continue

                x1, y1, x2, y2 = (
                    float(value)
                    for value in box
                )

                x1 = max(0.0, min(float(tile.width), x1))
                y1 = max(0.0, min(float(tile.height), y1))
                x2 = max(0.0, min(float(tile.width), x2))
                y2 = max(0.0, min(float(tile.height), y2))

                if (
                    x2 - x1 < MIN_BOX_SIDE
                    or y2 - y1 < MIN_BOX_SIDE
                ):
                    continue

                collected.append({
                    "label": label,
                    "confidence": round(float(score), 4),
                    "bbox": [
                        round(x1 + tile.x, 2),
                        round(y1 + tile.y, 2),
                        round(x2 + tile.x, 2),
                        round(y2 + tile.y, 2),
                    ],
                    "tile_index": index,
                })

    if progress is not None:
        progress(100.0, "Гео-улики: детекция завершена")

    return dedupe(collected)


def detect_with_timing(
    image: np.ndarray,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[list[dict], int]:
    """Вернуть детекции и время инференса в миллисекундах."""

    started = time.perf_counter()
    result = detect(image, progress=progress)

    return result, int(round(
        (time.perf_counter() - started) * 1000
    ))
