"""Сегментация гео-улик: SAM2.1 hiera tiny.

Изображение кодируется один раз (get_image_embeddings), затем для
пакета рамок вызывается predict. Это соответствует требованию
«set_image один раз, predict(box=...) пакетом» и экономит время на
CPU.

Возвращаются бинарные маски в пикселях исходного кадра. Если SAM2
недоступен, вызывающий код использует рамку как полигон и помечает
улику segmented=False.
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image

from app.services.geoCluesService import runtime


BATCH_SIZE = int(os.getenv("GEO_CLUES_SAM_BATCH", "8"))


def _to_numpy(mask) -> np.ndarray:
    if hasattr(mask, "detach"):
        mask = mask.detach().cpu().numpy()

    mask = np.asarray(mask)

    if mask.ndim == 4:
        # (num_boxes, num_masks, H, W) — берём лучшую маску.
        mask = mask[:, 0]

    if mask.ndim == 3:
        # (num_boxes, H, W)
        return mask

    if mask.ndim == 2:
        return mask[None, ...]

    return np.empty((0,), dtype=np.uint8)


def segment_boxes(
    image: np.ndarray,
    boxes: list[list[float]],
) -> list[np.ndarray] | None:
    """Построить маски для рамок.

    None означает, что сегментатор недоступен. Пустой список — что
    рамок не было.
    """

    if not boxes:
        return []

    loaded = runtime.load_segmenter()

    if loaded is None:
        return None

    processor, model = loaded

    import torch

    pil_image = Image.fromarray(image)
    results: list[np.ndarray] = []

    try:
        with torch.inference_mode():
            base = processor(
                images=pil_image,
                return_tensors="pt",
            )
            embeddings = model.get_image_embeddings(
                base["pixel_values"],
            )

            for start in range(0, len(boxes), BATCH_SIZE):
                chunk = boxes[start:start + BATCH_SIZE]

                box_inputs = processor(
                    images=pil_image,
                    input_boxes=[chunk],
                    return_tensors="pt",
                )

                outputs = model(
                    image_embeddings=embeddings,
                    input_boxes=box_inputs["input_boxes"],
                    multimask_output=False,
                )

                masks = processor.post_process_masks(
                    outputs.pred_masks.cpu(),
                    box_inputs["original_sizes"],
                )[0]

                array = _to_numpy(masks)

                for index in range(len(chunk)):
                    if index < len(array):
                        results.append(array[index])
                    else:
                        results.append(
                            np.zeros(
                                image.shape[:2],
                                dtype=np.uint8,
                            )
                        )

    except Exception:
        return None

    return results


def segment_with_timing(
    image: np.ndarray,
    boxes: list[list[float]],
) -> tuple[list[np.ndarray] | None, int]:
    import time

    started = time.perf_counter()
    masks = segment_boxes(image, boxes)

    return masks, int(round(
        (time.perf_counter() - started) * 1000
    ))
