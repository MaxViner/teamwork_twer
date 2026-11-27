"""Многокадровый стек и OCR по стеку.

Самый дешёвый прирост качества: один и тот же знак или столб
попадает в 10–30 кадров. Кадры выравниваются по фичам (ECC),
усредняются медианой — шум и смаз уходят, — и только потом
распознаётся текст. Одиночный кадр для OCR больше не нужен.

Модуль работает с путями к кадрам и рамками в пикселях. Если
выравнивание не удалось, кадр пропускается; если кадров меньше
min_frames, стек не строится.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


MIN_FRAMES = 3
MAX_FRAMES = 30
MIN_SIDE = 16


def _load_gray(path: str | Path) -> np.ndarray | None:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)

    if image is None or image.size == 0:
        return None

    return image


def _crop(
    image: np.ndarray,
    box: list[float] | tuple[float, ...] | None,
    margin: float,
) -> np.ndarray:
    if not box or len(box) != 4:
        return image

    height, width = image.shape[:2]
    left, top, right, bottom = (float(value) for value in box)
    pad_x = max(2.0, (right - left) * margin)
    pad_y = max(2.0, (bottom - top) * margin)

    left = int(max(0, min(width - 1, left - pad_x)))
    top = int(max(0, min(height - 1, top - pad_y)))
    right = int(max(left + 1, min(width, right + pad_x)))
    bottom = int(max(top + 1, min(height, bottom + pad_y)))

    return image[top:bottom, left:right]


def _resize(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    width, height = size

    if image.shape[1] == width and image.shape[0] == height:
        return image

    return cv2.resize(
        image,
        (width, height),
        interpolation=cv2.INTER_AREA,
    )


def _align(
    image: np.ndarray,
    template: np.ndarray,
) -> tuple[np.ndarray, bool]:
    """Выровнять изображение по шаблону (ECC, евклидово)."""

    if (
        image.shape[0] < MIN_SIDE
        or image.shape[1] < MIN_SIDE
    ):
        return image, False

    criteria = (
        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
        60,
        1e-5,
    )
    height, width = template.shape[:2]

    for motion in (cv2.MOTION_TRANSLATION, cv2.MOTION_EUCLIDEAN):
        warp = np.eye(2, 3, dtype=np.float32)

        try:
            _, warp = cv2.findTransformECC(
                template,
                image,
                warp,
                motion,
                criteria,
                None,
                5,
            )

        except cv2.error:
            continue

        return cv2.warpAffine(
            image,
            warp,
            (width, height),
            flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REPLICATE,
        ), True

    # Запасной путь для чистого сдвига: фазовая корреляция.
    try:
        (shift_x, shift_y), response = cv2.phaseCorrelate(
            template.astype(np.float32),
            image.astype(np.float32),
        )

    except cv2.error:
        return image, False

    if response < 0.05:
        return image, False

    return cv2.warpAffine(
        image,
        np.float32([
            [1.0, 0.0, -shift_x],
            [0.0, 1.0, -shift_y],
        ]),
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    ), True


def sharpness(image: np.ndarray) -> float:
    """Дисперсия лапласиана — грубая мера резкости."""

    if image is None or image.size == 0:
        return 0.0

    if image.dtype != np.uint8:
        image = np.clip(image, 0, 255).astype(np.uint8)

    return float(cv2.Laplacian(image, cv2.CV_64F).var())


def stack_images(
    images: list[np.ndarray],
    *,
    min_frames: int = MIN_FRAMES,
) -> dict:
    """Выровнять и сложить изображения в медианный стек."""

    prepared = [
        image
        for image in images
        if image is not None and image.size
    ]

    if len(prepared) < max(1, min_frames):
        return {
            "image": None,
            "used": 0,
            "skipped": len(images) - len(prepared),
            "reason": "too_few_frames",
        }

    prepared = prepared[:MAX_FRAMES]
    height = max(image.shape[0] for image in prepared)
    width = max(image.shape[1] for image in prepared)
    size = (width, height)

    base = _resize(prepared[0], size).astype(np.float32)
    aligned = [base]
    used = 1
    skipped = len(images) - len(prepared)

    for image in prepared[1:]:
        resized = _resize(image, size).astype(np.float32)
        warped, ok = _align(resized, base)

        if not ok:
            skipped += 1
            continue

        aligned.append(warped)
        used += 1

    if used < max(1, min_frames):
        return {
            "image": None,
            "used": used,
            "skipped": skipped,
            "reason": "alignment_failed",
        }

    stack = np.median(np.stack(aligned, axis=0), axis=0)
    result = np.clip(stack, 0, 255).astype(np.uint8)

    return {
        "image": result,
        "used": used,
        "skipped": skipped,
        "reason": None,
        "sharpness": round(sharpness(result), 2),
        "sharpness_before": round(
            max(sharpness(image) for image in aligned),
            2,
        ),
        "size": [int(width), int(height)],
    }


def stack_crops(
    paths: list[str | Path],
    boxes: list[list[float] | None] | None = None,
    *,
    margin: float = 0.25,
    min_frames: int = MIN_FRAMES,
) -> dict:
    """Стек одинаковых объектов: обрезать рамками и сложить."""

    crops: list[np.ndarray] = []
    box_list = boxes or [None] * len(paths)

    for index, path in enumerate(paths):
        image = _load_gray(path)

        if image is None:
            continue

        box = box_list[index] if index < len(box_list) else None
        crops.append(_crop(image, box, margin))

    return stack_images(crops, min_frames=min_frames)


@lru_cache(maxsize=1)
def ocr_reader():
    """Ленивая загрузка EasyOCR (русский + английский)."""

    import easyocr

    return easyocr.Reader(["ru", "en"], gpu=False)


def read_stack(
    image: np.ndarray | None,
    *,
    min_score: float = 0.2,
) -> list[dict]:
    """Распознать текст на стеке."""

    if image is None or image.size == 0:
        return []

    try:
        reader = ocr_reader()
        recognized = reader.readtext(image)

    except Exception:
        return []

    result = []

    for polygon, text, score in recognized:
        text = " ".join(str(text).split())

        if not text or float(score) < min_score:
            continue

        result.append({
            "text": text,
            "score": round(float(score), 3),
            "polygon": [
                [float(x), float(y)]
                for x, y in polygon
            ],
        })

    result.sort(key=lambda item: -item["score"])

    return result


def stack_and_ocr(
    paths: list[str | Path],
    boxes: list[list[float] | None] | None = None,
    *,
    margin: float = 0.25,
    min_frames: int = MIN_FRAMES,
    min_score: float = 0.2,
) -> dict:
    """Полный проход: стек → OCR. Возвращает стек и распознанный текст."""

    stacked = stack_crops(
        paths,
        boxes,
        margin=margin,
        min_frames=min_frames,
    )

    if stacked.get("image") is None:
        return {
            **stacked,
            "text": [],
        }

    return {
        **stacked,
        "text": read_stack(stacked["image"], min_score=min_score),
    }


def save_stack(image: np.ndarray, path: str | Path) -> str:
    """Сохранить стек на диск (для артефакта стадии)."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)

    return str(path)


__all__ = [
    "MAX_FRAMES",
    "MIN_FRAMES",
    "read_stack",
    "save_stack",
    "sharpness",
    "stack_and_ocr",
    "stack_crops",
    "stack_images",
]
