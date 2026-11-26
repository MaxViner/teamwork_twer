"""Тестовая панель визуального анализа видео.

Позволяет загрузить видео, выбрать кадр по таймкоду и запустить
отдельные визуальные функции без создания задания и полного pipeline.

Поддерживаются:
- метрики кадра;
- словесное описание сцены;
- гео-улики Grounding DINO + SAM2;
- семантическая разметка SegFormer;
- лица YuNet;
- OCR EasyOCR;
- поиск сцен PySceneDetect;
- все визуальные функции одновременно.
"""


from __future__ import annotations


import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable

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
from app.services.geoCluesService import analyze_frame as analyze_geo_clues
from app.services.visualAnalysisService.faces import detect_faces
from app.services.visualAnalysisService.metrics import (
    analyze_frame,
    describe_metrics,
)
from app.services.visualAnalysisService.segmentation import run_segformer


router = APIRouter(
    prefix="/api/dev/video-lab",
    tags=["video-lab"],
)


LAB_ROOT = Path(
    os.getenv(
        "VIDEO_LAB_DIR",
        str(DATA_DIR / "video_lab"),
    )
)


ALLOWED_VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
}


def _lab_dir(lab_id: str) -> Path:
    if not lab_id or not lab_id.isalnum():
        raise HTTPException(
            400,
            "Некорректный lab_id.",
        )

    path = LAB_ROOT / lab_id

    if not path.is_dir():
        raise HTTPException(
            404,
            "Сессия Video Lab не найдена.",
        )

    return path



def _lab_json(lab_id: str) -> dict:
    path = _lab_dir(lab_id) / "lab.json"

    if not path.is_file():
        raise HTTPException(
            404,
            "Сессия Video Lab не найдена.",
        )

    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )



def _save_lab_json(
    lab_id: str,
    data: dict,
) -> None:
    path = _lab_dir(lab_id) / "lab.json"

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )



def _video_duration(path: Path) -> float:
    import cv2

    capture = cv2.VideoCapture(str(path))

    if not capture.isOpened():
        raise HTTPException(
            400,
            "Не удалось открыть видео.",
        )

    fps = capture.get(
        cv2.CAP_PROP_FPS,
    ) or 25.0

    frames = capture.get(
        cv2.CAP_PROP_FRAME_COUNT,
    )

    capture.release()

    if frames <= 0:
        raise HTTPException(
            400,
            "Не удалось определить длительность видео.",
        )

    return float(frames / fps)



def _noop_progress(
    percent: float,
    message: str | None = None,
) -> None:
    return None



def _extract_frame(
    video: Path,
    timestamp: float,
    output: Path,
) -> None:
    from app.services.mediaService.ffmpeg import extract_frame

    extract_frame(
        video,
        output,
        timestamp,
    )



def _analyze_frame_file(
    frame_path: Path,
    functions: list[str],
) -> dict:
    result: dict = {}
    timings: dict[str, int] = {}
    errors: list[dict] = []

    def run(name: str, function: Callable[[], object]) -> None:
        started = time.perf_counter()

        try:
            result[name] = function()

        except Exception as error:
            errors.append({
                "function": name,
                "error": str(error)[:1500],
            })

        finally:
            timings[name] = int(
                round(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000,
                )
            )

    if "metrics" in functions or "all" in functions:
        def metrics_task():
            metrics = analyze_frame(frame_path)
            descriptors = describe_metrics(metrics)

            return {
                "metrics": metrics,
                "descriptors": descriptors,
            }

        run(
            "metrics",
            metrics_task,
        )

    if "geo_clues" in functions or "all" in functions:
        run(
            "geo_clues",
            lambda: analyze_geo_clues(frame_path),
        )

    if "segmentation" in functions or "all" in functions:
        run(
            "segmentation",
            lambda: run_segformer(frame_path),
        )

    if "faces" in functions or "all" in functions:
        run(
            "faces",
            lambda: detect_faces(frame_path),
        )

    if "ocr" in functions or "all" in functions:
        run(
            "ocr",
            lambda: _ocr_frame(frame_path),
        )

    return {
        "result": result,
        "timings_ms": timings,
        "errors": errors,
    }



def _ocr_frame(frame_path: Path) -> dict:
    from app.services.visyalInspectorService.ocr import ocr_reader

    reader = ocr_reader()
    recognized = reader.readtext(
        str(frame_path),
    )

    items = []

    for polygon, text, score in recognized:
        text = str(text).strip()

        if not text:
            continue

        items.append({
            "text": text,
            "confidence": round(
                float(score),
                3,
            ),
            "polygon": [
                [
                    float(x),
                    float(y),
                ]
                for x, y in polygon
            ],
        })

    return {
        "items": items,
        "count": len(items),
    }



class AnalyzeRequest(BaseModel):
    timestamp: float = Field(
        ge=0,
    )
    functions: list[str] = Field(
        default_factory=lambda: ["all"],
    )



@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
) -> dict:
    mime = (
        file.content_type or ""
    ).lower()


    if mime not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(
            400,
            "Поддерживаются MP4, MOV, WebM и MKV.",
        )


    lab_id = uuid.uuid4().hex
    folder = LAB_ROOT / lab_id
    frames = folder / "frames"

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )
    frames.mkdir(
        exist_ok=True,
    )


    source = folder / "source.mp4"


    try:
        with source.open(
            "wb",
        ) as target:
            while chunk := await file.read(
                1024 * 1024,
            ):
                target.write(chunk)

        if not source.stat().st_size:
            raise HTTPException(
                400,
                "Файл пустой.",
            )

        duration = await run_in_threadpool(
            _video_duration,
            source,
        )

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            500,
            f"Не удалось подготовить видео: "
            f"{str(error)[:500]}",
        ) from None

    data = {
        "id": lab_id,
        "created_at": time.time(),
        "filename": file.filename,
        "source": source.name,
        "duration": duration,
        "status": "ready",
    }

    _save_lab_json(
        lab_id,
        data,
    )

    return data



@router.get("/{lab_id}")
def get_lab(lab_id: str) -> dict:
    return _lab_json(lab_id)



@router.get("/{lab_id}/frame")
def get_frame(
    lab_id: str,
    timestamp: float,
) -> FileResponse:
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

    safe_name = (
        f"frame_{timestamp:.3f}.jpg"
        .replace(
            ":",
            "_",
        )
    )

    frame = folder / "frames" / safe_name

    if not frame.is_file():
        _extract_frame(
            folder / data["source"],
            timestamp,
            frame,
        )

    return FileResponse(
        frame,
        media_type="image/jpeg",
    )



@router.post("/{lab_id}/analyze")
async def analyze_frame_endpoint(
    lab_id: str,
    payload: AnalyzeRequest,
) -> dict:
    data = _lab_json(lab_id)
    folder = _lab_dir(lab_id)

    if payload.timestamp > data["duration"]:
        raise HTTPException(
            400,
            "Таймкод больше длительности видео.",
        )

    allowed = {
        "metrics",
        "geo_clues",
        "segmentation",
        "faces",
        "ocr",
        "all",
    }

    functions = payload.functions or ["all"]

    unknown = set(functions) - allowed

    if unknown:
        raise HTTPException(
            400,
            f"Неизвестные функции: "
            f"{', '.join(sorted(unknown))}",
        )

    safe_name = (
        f"frame_{payload.timestamp:.3f}.jpg"
        .replace(
            ":",
            "_",
        )
    )

    frame = folder / "frames" / safe_name

    if not frame.is_file():
        _extract_frame(
            folder / data["source"],
            payload.timestamp,
            frame,
        )

    analysis = await run_in_threadpool(
        _analyze_frame_file,
        frame,
        functions,
    )

    return {
        "lab_id": lab_id,
        "timestamp": payload.timestamp,
        "functions": functions,
        "frame_url": (
            f"/api/dev/video-lab/{lab_id}/frame"
            f"?timestamp={payload.timestamp}"
        ),
        **analysis,
    }



@router.post("/{lab_id}/scenes")
async def analyze_scenes(
    lab_id: str,
) -> dict:
    from app.services.visyalInspectorService.scenes import extract_scenes

    data = _lab_json(lab_id)
    folder = _lab_dir(lab_id)
    video = folder / data["source"]

    result = await run_in_threadpool(
        extract_scenes,
        video,
        data["duration"],
        _noop_progress,
    )

    return {
        "lab_id": lab_id,
        **result,
    }



@router.delete("/{lab_id}")
def delete_lab(lab_id: str) -> dict:
    import shutil

    folder = _lab_dir(lab_id)

    shutil.rmtree(
        folder,
        ignore_errors=True,
    )

    return {
        "status": "deleted",
    }