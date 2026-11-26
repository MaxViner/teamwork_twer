"""Тестовая панель одометрии и BEV.

Отдельный endpoint для точечной проверки фичи: загрузить видео,
равномерно выбрать кадры, прогнать ORB + essential-матрицу и
построить anchor-BEV. Ничего не создаёт в заданиях и не запускает
полный pipeline.

Дополнительно есть режим пары кадров: два изображения дают одну
относительную позу и полную диагностику (причины отказа, число
признаков и совпадений).

BEV здесь — топология «маршрут + сильные якоря». Слабые улики и
облако детекций на карту не попадают: именно они превращали
прошлую версию в нечитаемую кашу.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import numpy as np
from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.config import DATA_DIR
from app.services.mediaService.frames import select_timestamps
from app.services.serviceHub import HUB


router = APIRouter(
    prefix="/api/dev/odometry-lab",
    tags=["odometry-lab"],
)


LAB_ROOT = Path(
    os.getenv(
        "ODOMETRY_LAB_DIR",
        str(DATA_DIR / "odometry_lab"),
    )
)

ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}


def _noop_progress(percent: float, message: str = "") -> None:
    return None


def _lab_dir(lab_id: str) -> Path:
    if not lab_id or not lab_id.isalnum():
        raise HTTPException(400, "Некорректный lab_id.")

    path = LAB_ROOT / lab_id

    if not path.is_dir():
        raise HTTPException(
            404,
            "Сессия Odometry Lab не найдена.",
        )

    return path


def _lab_json(lab_id: str) -> dict:
    path = _lab_dir(lab_id) / "lab.json"

    if not path.is_file():
        raise HTTPException(
            404,
            "Сессия Odometry Lab не найдена.",
        )

    return json.loads(path.read_text(encoding="utf-8"))


def _save_lab_json(lab_id: str, data: dict) -> None:
    path = _lab_dir(lab_id) / "lab.json"

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _video_duration(path: Path) -> float:
    import cv2

    capture = cv2.VideoCapture(str(path))

    if not capture.isOpened():
        raise HTTPException(400, "Не удалось открыть видео.")

    fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)

    capture.release()

    if frames <= 0:
        raise HTTPException(
            400,
            "Не удалось определить длительность видео.",
        )

    return float(frames / fps)


def _camera_matrix(size: tuple[int, int]) -> np.ndarray:
    """Правдоподобная K по размеру кадра (горизонтальный FOV ≈ 70°)."""

    width, height = size
    focal = 0.85 * max(width, 1)

    return np.array(
        [
            [focal, 0.0, width / 2],
            [0.0, focal, height / 2],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _extract_frames(
    video: Path,
    folder: Path,
    duration: float,
    count: int,
) -> list[dict]:
    """Равномерно извлечь кадры и вернуть список для одометрии."""

    from PIL import Image

    from app.services.mediaService.ffmpeg import extract_frame

    frames_dir = folder / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    timestamps = select_timestamps(
        duration,
        count,
        {},
    )

    frames = []

    for index, timestamp in enumerate(timestamps):
        path = frames_dir / f"odo_{index:03d}.jpg"

        if not path.is_file():
            extract_frame(video, path, timestamp)

        with Image.open(path) as image:
            width, height = image.size

        frames.append({
            "index": index,
            "timestamp": round(float(timestamp), 3),
            "artifact": f"frames/{path.name}",
            "path": path,
            "size": (width, height),
            "detections": [],
        })

    return frames


def _clue_frames(
    frames: list[dict],
    limit: int,
) -> list[dict]:
    """Прогнать гео-улики на части кадров для якорей BEV."""

    limit = max(0, min(int(limit), len(frames)))

    if limit == 0:
        return []

    step = max(1, len(frames) // limit)
    selected = frames[::step][:limit]

    result = []

    for frame in selected:
        try:
            clues = HUB.visual.geo_clues(frame["path"])

        except Exception as error:
            result.append({
                "timestamp": frame["timestamp"],
                "artifact": frame["artifact"],
                "size": list(frame["size"]),
                "geo_clues": [],
                "error": str(error)[:500],
            })
            continue

        result.append({
            "timestamp": frame["timestamp"],
            "artifact": frame["artifact"],
            "size": list(frame["size"]),
            "geo_clues": clues.get("geo_clues") or [],
            "frame_summary": clues.get("frame_summary"),
            "error": clues.get("error"),
            "timings_ms": clues.get("timings_ms"),
        })

    return result


class AnalyzeRequest(BaseModel):
    """Параметры анализа видео."""

    count: int = Field(default=16, ge=2, le=48)
    include_clues: bool = False
    clue_frames: int = Field(default=6, ge=0, le=24)
    camera_height_m: float = Field(default=1.2, gt=0, le=10)


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)) -> dict:
    """Сохранить видео для тестов одометрии."""

    mime = (file.content_type or "").lower()

    if mime not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            400,
            "Поддерживаются MP4, MOV, WebM и MKV.",
        )

    lab_id = uuid.uuid4().hex
    folder = LAB_ROOT / lab_id
    folder.mkdir(parents=True, exist_ok=True)

    source = folder / "source.mp4"

    try:
        with source.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                target.write(chunk)

        if not source.stat().st_size:
            raise HTTPException(400, "Файл пустой.")

        duration = await run_in_threadpool(
            _video_duration,
            source,
        )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось подготовить видео: {str(error)[:500]}",
        ) from None

    data = {
        "id": lab_id,
        "created_at": time.time(),
        "filename": file.filename,
        "source": source.name,
        "duration": duration,
        "status": "ready",
    }

    _save_lab_json(lab_id, data)

    return data


@router.get("/{lab_id}")
def get_lab(lab_id: str) -> dict:
    return _lab_json(lab_id)


@router.get("/{lab_id}/frame")
def get_frame(lab_id: str, timestamp: float) -> FileResponse:
    data = _lab_json(lab_id)
    folder = _lab_dir(lab_id)

    if timestamp < 0:
        raise HTTPException(
            400,
            "Таймкод не может быть отрицательным.",
        )

    if timestamp > data["duration"]:
        raise HTTPException(
            400,
            "Таймкод больше длительности видео.",
        )

    safe_name = f"frame_{timestamp:.3f}.jpg".replace(":", "_")
    frame = folder / "frames" / safe_name

    if not frame.is_file():
        from app.services.mediaService.ffmpeg import extract_frame

        frame.parent.mkdir(parents=True, exist_ok=True)
        extract_frame(folder / data["source"], frame, timestamp)

    return FileResponse(frame, media_type="image/jpeg")


@router.get("/{lab_id}/bev.png")
def get_bev(lab_id: str) -> FileResponse:
    path = _lab_dir(lab_id) / "bev.png"

    if not path.is_file():
        raise HTTPException(404, "BEV ещё не построен.")

    return FileResponse(path, media_type="image/png")


def _analyze_video(
    folder: Path,
    data: dict,
    payload: AnalyzeRequest,
) -> dict:
    """Синхронная часть анализа: кадры, одометрия, BEV."""

    started = time.perf_counter()

    frames = _extract_frames(
        folder / data["source"],
        folder,
        float(data["duration"]),
        payload.count,
    )

    if len(frames) < 2:
        raise HTTPException(
            400,
            "Не удалось извлечь достаточно кадров.",
        )

    odometry = HUB.visual.odometry(
        frames,
        {},
        {},
        None,
        _noop_progress,
    )

    clue_results = (
        _clue_frames(frames, payload.clue_frames)
        if payload.include_clues
        else []
    )

    detections_per_frame = [
        {
            "timestamp": frame["timestamp"],
            "artifact": frame["artifact"],
            "size": list(frame["size"]),
            "geo_clues": [],
            "detections": [],
        }
        for frame in frames
    ]

    clue_by_time = {
        round(float(item["timestamp"]), 3): item
        for item in clue_results
    }

    for item in detections_per_frame:
        clue = clue_by_time.get(round(float(item["timestamp"]), 3))

        if clue:
            item["geo_clues"] = clue.get("geo_clues") or []

    trajectory = odometry.get("trajectory") or {}

    bev = HUB.visual.bev(
        trajectory,
        detections_per_frame,
        [],
        camera_height_m=payload.camera_height_m,
    )

    bev_url = None

    if bev:
        HUB.visual.render_bev(bev, folder / "bev.png")
        bev_url = f"/api/dev/odometry-lab/{folder.name}/bev.png"

    elapsed = int(round((time.perf_counter() - started) * 1000))

    return {
        "frame_count": len(frames),
        "timestamps": [frame["timestamp"] for frame in frames],
        "odometry": {
            "successful_pairs": odometry.get("successful_pairs"),
            "skipped_pairs": odometry.get("skipped_pairs"),
            "pair_count": odometry.get("pair_count"),
            "diagnostics": odometry.get("diagnostics"),
            "scale": odometry.get("scale"),
            "trajectory": trajectory,
            "pairs": odometry.get("pairs") or [],
            "skipped": odometry.get("skipped") or [],
            "note": odometry.get("note"),
        },
        "bev": bev,
        "bev_url": bev_url,
        "clue_status": HUB.visual.status(),
        "clue_frames": clue_results,
        "elapsed_ms": elapsed,
    }


@router.post("/{lab_id}/analyze")
async def analyze_video(
    lab_id: str,
    payload: AnalyzeRequest,
) -> dict:
    """Прогнать одометрию и BEV по видео."""

    data = _lab_json(lab_id)
    folder = _lab_dir(lab_id)

    try:
        result = await run_in_threadpool(
            _analyze_video,
            folder,
            data,
            payload,
        )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось построить одометрию: {str(error)[:500]}",
        ) from None

    return {
        "lab_id": lab_id,
        **result,
    }


def _pair_result(
    path_a: Path,
    path_b: Path,
) -> dict:
    """Относительная поза одной пары с диагностикой."""

    from PIL import Image

    from app.services.odometryService.visual_odometry import (
        VisualOdometry,
    )

    with Image.open(path_a) as image:
        size = image.size

    odometry = VisualOdometry(_camera_matrix(size))

    result, reason = odometry.estimate_with_reason(
        path_a,
        path_b,
    )

    return {
        "ok": result is not None,
        "reason": reason,
        "result": result,
        "diagnostics": dict(odometry.diagnostics),
        "timings_ms": dict(odometry.timings),
    }


@router.post("/pair")
async def analyze_pair(
    frame_a: UploadFile = File(...),
    frame_b: UploadFile = File(...),
) -> dict:
    """Оценить одну пару кадров без видео."""

    import tempfile

    paths: list[Path] = []

    try:
        for upload in (frame_a, frame_b):
            suffix = Path(upload.filename or "frame.jpg").suffix or ".jpg"
            handle, name = tempfile.mkstemp(suffix=suffix)
            os.close(handle)
            path = Path(name)
            paths.append(path)
            payload = await upload.read()

            if not payload:
                raise HTTPException(400, "Файл пустой.")

            path.write_bytes(payload)

        result = await run_in_threadpool(
            _pair_result,
            paths[0],
            paths[1],
        )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось оценить пару: {str(error)[:500]}",
        ) from None

    finally:
        for path in paths:
            path.unlink(missing_ok=True)

    return result


@router.delete("/{lab_id}")
def delete_lab(lab_id: str) -> dict:
    import shutil

    folder = _lab_dir(lab_id)
    shutil.rmtree(folder, ignore_errors=True)

    return {"status": "deleted"}
