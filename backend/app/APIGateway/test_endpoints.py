"""Тестовые эндпоинты для визуальных сервисов.

Роутер доступен только при ENABLE_TEST_ENDPOINTS=1. Он не создаёт
задание и не пишет в job.json: файл сохраняется во временную папку,
анализируется и удаляется. Нужен для быстрой проверки YOLO,
SegFormer, лиц и метрик на одном изображении.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import MODELS_DIR
from app.services.aiService import client as ai_client
from app.services.objectDetectionService.detector import YoloDetector
from app.services.odometryService.visual_odometry import VisualOdometry
from app.services.visualAnalysisService.faces import detect_faces
from app.services.visualAnalysisService.metrics import (
    analyze_frame,
    describe_metrics,
)
from app.services.visualAnalysisService.segmentation import run_segformer


test_router = APIRouter(
    prefix="/api/test",
    tags=["test"],
)

# Одна сессия ONNX на процесс: чтение модели занимает заметное время.
_DETECTOR: YoloDetector | None = None

_ENABLED_VALUES = {"1", "true", "yes", "on"}


def _ensure_enabled() -> None:
    """Пускать только при явно включённых тестовых эндпоинтах."""

    value = os.getenv(
        "ENABLE_TEST_ENDPOINTS",
        "",
    ).strip().lower()

    if value not in _ENABLED_VALUES:
        # Скрываем существование роутера, когда он выключен.
        raise HTTPException(404, "Not Found")


def _detector() -> YoloDetector:
    """Лениво открыть общий детектор YOLO."""

    global _DETECTOR

    if _DETECTOR is None:
        _DETECTOR = YoloDetector(
            MODELS_DIR / "yolov8n.onnx",
        )

    return _DETECTOR


def _analyze_image(path: Path) -> dict:
    """Прогнать изображение через метрики, YOLO, лица и SegFormer."""

    timings: dict[str, int] = {}

    started = time.perf_counter()
    metrics = analyze_frame(path)
    descriptors = describe_metrics(metrics)
    timings["metrics"] = _elapsed_ms(started)

    started = time.perf_counter()
    detections = _detector().detect(path)
    timings["yolo"] = _elapsed_ms(started)

    started = time.perf_counter()
    faces = detect_faces(path)
    timings["faces"] = _elapsed_ms(started)

    started = time.perf_counter()
    segments = run_segformer(path)[:10]
    timings["segformer"] = _elapsed_ms(started)

    landscape = descriptors.get("landscape") or []
    lighting = descriptors.get("lighting") or ""

    text_description = " ".join(
        part
        for part in [*landscape, lighting]
        if part
    )

    return {
        "metrics": metrics,
        "descriptors": descriptors,
        "detections": detections,
        "faces": faces,
        "segments": segments,
        "text_description": text_description,
        "inference_time_ms": timings,
    }


def _elapsed_ms(started: float) -> int:
    """Перевести прошедшее время в целые миллисекунды."""

    return int(round((time.perf_counter() - started) * 1000))


@test_router.post("/vision")
async def vision_test(file: UploadFile = File(...)) -> dict:
    """Проверить визуальные сервисы на загруженном изображении."""

    _ensure_enabled()

    suffix = Path(file.filename or "upload.jpg").suffix or ".jpg"

    handle, name = tempfile.mkstemp(suffix=suffix)
    os.close(handle)

    path = Path(name)

    try:
        payload = await file.read()

        if not payload:
            raise HTTPException(400, "Файл пустой.")

        path.write_bytes(payload)

        result = await run_in_threadpool(_analyze_image, path)

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось разобрать изображение: {str(error)[:500]}",
        ) from None

    finally:
        path.unlink(missing_ok=True)

    return {
        "filename": file.filename,
        **result,
    }


async def _write_upload(
    upload: UploadFile,
    paths: list[Path],
) -> Path:
    """Сохранить загруженный файл во временный путь."""

    suffix = Path(upload.filename or "frame.jpg").suffix or ".jpg"

    handle, name = tempfile.mkstemp(suffix=suffix)
    os.close(handle)

    path = Path(name)
    paths.append(path)

    payload = await upload.read()

    if not payload:
        raise HTTPException(400, "Файл пустой.")

    path.write_bytes(payload)
    return path


def _default_camera_matrix(path: Path) -> np.ndarray:
    """Собрать правдоподобную K по размеру кадра.

    Тестовый эндпоинт не знает реальную калибровку, поэтому берёт
    фокусное расстояние порядка 0.9 от большей стороны. Для проверки
    контракта этого достаточно.
    """

    with Image.open(path) as image:
        width, height = image.size

    focal = 0.9 * max(width, height)

    return np.array(
        [
            [focal, 0.0, width / 2],
            [0.0, focal, height / 2],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _analyze_odometry(
    path_a: Path,
    path_b: Path,
) -> tuple[dict | None, str | None, dict[str, int]]:
    """Оценить позу между двумя файлами и вернуть тайминги."""

    odometry = VisualOdometry(
        _default_camera_matrix(path_a),
    )

    result, reason = odometry.estimate_with_reason(
        path_a,
        path_b,
    )

    return result, reason, odometry.timings


@test_router.post("/odometry")
async def odometry_test(
    frame_a: UploadFile = File(...),
    frame_b: UploadFile = File(...),
):
    """Оценить относительную позу двух кадров."""

    _ensure_enabled()

    paths: list[Path] = []

    try:
        path_a = await _write_upload(frame_a, paths)
        path_b = await _write_upload(frame_b, paths)

        result, reason, timings = await run_in_threadpool(
            _analyze_odometry,
            path_a,
            path_b,
        )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось оценить одометрию: {str(error)[:500]}",
        ) from None

    finally:
        for path in paths:
            path.unlink(missing_ok=True)

    if result is None:
        return JSONResponse(
            status_code=422,
            content={"reason": reason or "degenerate"},
        )

    return {
        **result,
        "inference_time_ms": timings,
    }


class ChatRequest(BaseModel):
    """Запрос к AI-провайдеру из тестового эндпоинта."""

    prompt: str
    system: str | None = None


@test_router.post("/chat")
async def chat_test(payload: ChatRequest) -> dict:
    """Проверить текстовый запрос к настроенному AI-провайдеру."""

    _ensure_enabled()

    prompt = payload.prompt.strip()

    if not prompt:
        raise HTTPException(400, "Пустой prompt.")

    try:
        answer = await run_in_threadpool(
            ai_client.generate_text,
            prompt,
            system=payload.system,
            json_mode=False,
        )

    except ai_client.AiNotConfigured as error:
        raise HTTPException(400, str(error)) from None

    except ai_client.AiServiceError as error:
        raise HTTPException(502, str(error)) from None

    return {
        "ok": True,
        "response": str(answer.get("text") or ""),
    }
