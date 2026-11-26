"""Ленивая загрузка zero-shot моделей для гео-улик.

Модели большие, поэтому они не импортируются и не скачиваются при
старте backend. Первый вызов детектора или сегментатора загружает
нужную модель один раз на процесс.

Если transformers/torch недоступны, нет сети или не хватает памяти,
модуль возвращает None и сохраняет причину. Стадия визуального
анализа из-за этого не падает: geo_clues остаются пустыми, а
ошибка видна в отчёте и тестовом эндпоинте.
"""

from __future__ import annotations

import os
from threading import RLock


DETECTOR_MODEL_ID = os.getenv(
    "GEO_CLUES_DETECTOR_MODEL",
    "IDEA-Research/grounding-dino-tiny",
)

SEGMENTER_MODEL_ID = os.getenv(
    "GEO_CLUES_SEGMENTER_MODEL",
    "facebook/sam2.1-hiera-tiny",
)

BOX_THRESHOLD = float(os.getenv("GEO_CLUES_BOX_THRESHOLD", "0.35"))
TEXT_THRESHOLD = float(os.getenv("GEO_CLUES_TEXT_THRESHOLD", "0.35"))


_LOCK = RLock()

_DETECTOR = None
_DETECTOR_ERROR: str | None = None

_SEGMENTER = None
_SEGMENTER_ERROR: str | None = None


def _disabled() -> bool:
    return os.getenv(
        "GEO_CLUES_DISABLE",
        "",
    ).strip().lower() in {"1", "true", "yes", "on"}


def load_detector():
    """Загрузить Grounding DINO tiny и вернуть (processor, model)."""

    global _DETECTOR, _DETECTOR_ERROR

    if _disabled():
        _DETECTOR_ERROR = "Гео-улики отключены через GEO_CLUES_DISABLE."
        return None

    with _LOCK:
        if _DETECTOR is not None:
            return _DETECTOR

        if _DETECTOR_ERROR is not None:
            return None

        try:
            import torch
            from transformers import (
                AutoModelForZeroShotObjectDetection,
                AutoProcessor,
            )

            processor = AutoProcessor.from_pretrained(
                DETECTOR_MODEL_ID,
            )
            model = (
                AutoModelForZeroShotObjectDetection
                .from_pretrained(DETECTOR_MODEL_ID)
            )
            model.to("cpu")
            model.eval()

            # На CPU градиенты не нужны и только занимают память.
            torch.set_grad_enabled(False)

            _DETECTOR = (processor, model)
            _DETECTOR_ERROR = None

        except Exception as error:  # pragma: no cover - зависит от сети
            _DETECTOR_ERROR = str(error)[:1000]
            _DETECTOR = None

        return _DETECTOR


def load_segmenter():
    """Загрузить SAM2.1 hiera tiny и вернуть (processor, model)."""

    global _SEGMENTER, _SEGMENTER_ERROR

    if _disabled():
        _SEGMENTER_ERROR = "Гео-улики отключены через GEO_CLUES_DISABLE."
        return None

    with _LOCK:
        if _SEGMENTER is not None:
            return _SEGMENTER

        if _SEGMENTER_ERROR is not None:
            return None

        try:
            import torch
            from transformers import Sam2Model, Sam2Processor

            processor = Sam2Processor.from_pretrained(
                SEGMENTER_MODEL_ID,
            )
            model = Sam2Model.from_pretrained(
                SEGMENTER_MODEL_ID,
            )
            model.to("cpu")
            model.eval()

            torch.set_grad_enabled(False)

            _SEGMENTER = (processor, model)
            _SEGMENTER_ERROR = None

        except Exception as error:  # pragma: no cover - зависит от сети
            _SEGMENTER_ERROR = str(error)[:1000]
            _SEGMENTER = None

        return _SEGMENTER


def detector_loaded() -> bool:
    return _DETECTOR is not None


def segmenter_loaded() -> bool:
    return _SEGMENTER is not None


def detector_error() -> str | None:
    return _DETECTOR_ERROR


def segmenter_error() -> str | None:
    return _SEGMENTER_ERROR


def status() -> dict:
    """Состояние моделей без попытки их загрузить."""

    return {
        "enabled": not _disabled(),
        "detector": {
            "model": DETECTOR_MODEL_ID,
            "loaded": _DETECTOR is not None,
            "error": _DETECTOR_ERROR,
        },
        "segmenter": {
            "model": SEGMENTER_MODEL_ID,
            "loaded": _SEGMENTER is not None,
            "error": _SEGMENTER_ERROR,
        },
        "thresholds": {
            "box_threshold": BOX_THRESHOLD,
            "text_threshold": TEXT_THRESHOLD,
        },
    }


def reset() -> None:
    """Сбросить кэш моделей — используется тестами."""

    global _DETECTOR, _DETECTOR_ERROR
    global _SEGMENTER, _SEGMENTER_ERROR

    with _LOCK:
        _DETECTOR = None
        _DETECTOR_ERROR = None
        _SEGMENTER = None
        _SEGMENTER_ERROR = None
