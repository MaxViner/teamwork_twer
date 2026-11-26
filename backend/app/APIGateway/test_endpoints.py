"""Тестовые эндпоинты визуальных сервисов.

Роутер доступен только при ENABLE_TEST_ENDPOINTS=1. Он не создаёт
задание и не пишет в job.json: файл сохраняется во временную папку,
анализируется и удаляется.

Здесь собраны все обработчики визуального сервиса:
- метрики и словесные дескрипторы кадра;
- гео-улики Grounding DINO tiny + SAM2.1 hiera tiny (geo_clues);
- семантическая разметка SegFormer;
- лица YuNet;
- одометрия двух кадров и тест AI-чата.

Отдельный /api/geo-clues оставлен для проверки только гео-улик.
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

from app.services import geoCluesService
from app.services.aiService import client as ai_client
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

# Короткий алиас из ТЗ: /api/geo-clues.
geo_clue_router = APIRouter(
    prefix="/api",
    tags=["test"],
)

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


def _analyze_image(path: Path) -> dict:
    """Прогнать изображение через все визуальные обработчики."""

    timings: dict[str, int] = {}

    started = time.perf_counter()
    metrics = analyze_frame(path)
    descriptors = describe_metrics(metrics)
    timings["metrics"] = _elapsed_ms(started)

    started = time.perf_counter()
    clue_result = geoCluesService.analyze_frame(path)
    timings["geo_clues"] = _elapsed_ms(started)

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

    clues = clue_result.get("geo_clues") or []

    return {
        "image_size": clue_result.get("image_size"),
        "metrics": metrics,
        "descriptors": descriptors,
        "geo_clues": clues,
        "frame_summary": clue_result.get("frame_summary"),
        "detections": _legacy_detections(clues),
        "faces": faces,
        "segments": segments,
        "text_description": text_description,
        "models": clue_result.get("models"),
        "model_status": geoCluesService.status(),
        "geo_clue_error": clue_result.get("error"),
        "geo_clue_timings_ms": clue_result.get("timings_ms"),
        "inference_time_ms": timings,
    }


def _analyze_geo_clues(path: Path) -> dict:
    """Прогнать только детектор и сегментатор гео-улик."""

    result = geoCluesService.analyze_frame(path)
    clues = result.get("geo_clues") or []

    return {
        "image_size": result.get("image_size"),
        "geo_clues": clues,
        "frame_summary": result.get("frame_summary"),
        "detections": _legacy_detections(clues),
        "models": result.get("models"),
        "model_status": geoCluesService.status(),
        "error": result.get("error"),
        "timings_ms": result.get("timings_ms"),
    }


def _legacy_detections(clues: list[dict]) -> list[dict]:
    return [
        {
            "label": item["label"],
            "label_ru": item["label_ru"],
            "category": "geo_clue",
            "confidence": item["confidence"],
            "bbox": item["bbox"],
            "is_dynamic": False,
            "type": item["type"],
            "match_priority": item["match_priority"],
        }
        for item in clues
    ]


def _elapsed_ms(started: float) -> int:
    """Перевести прошедшее время в целые миллисекунды."""

    return int(round((time.perf_counter() - started) * 1000))


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


async def _vision_response(upload: UploadFile) -> dict:
    _ensure_enabled()

    paths: list[Path] = []

    try:
        path = await _write_upload(upload, paths)
        result = await run_in_threadpool(_analyze_image, path)

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось разобрать изображение: {str(error)[:500]}",
        ) from None

    finally:
        for path in paths:
            path.unlink(missing_ok=True)

    return {
        "filename": upload.filename,
        **result,
    }


@test_router.post("/vision")
async def vision_test(file: UploadFile = File(...)) -> dict:
    """Проверить все визуальные сервисы на одном изображении."""

    return await _vision_response(file)


@test_router.post("/geo-clues")
async def geo_clues_test(file: UploadFile = File(...)) -> dict:
    """Проверить только гео-улики на одном изображении."""

    _ensure_enabled()

    paths: list[Path] = []

    try:
        path = await _write_upload(file, paths)
        result = await run_in_threadpool(_analyze_geo_clues, path)

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось найти гео-улики: {str(error)[:500]}",
        ) from None

    finally:
        for path in paths:
            path.unlink(missing_ok=True)

    return {
        "filename": file.filename,
        **result,
    }


@geo_clue_router.post("/geo-clues")
async def geo_clues_alias(file: UploadFile = File(...)) -> dict:
    """Алиас /api/geo-clues из ТЗ."""

    return await geo_clues_test(file)


def _default_camera_matrix(path: Path) -> np.ndarray:
    """Собрать правдоподобную K по размеру кадра."""

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
