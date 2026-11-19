"""FastAPI-приложение и маршруты API.

Принимает видео, создаёт задание, отдаёт статус и прогресс,
позволяет править наблюдения, запускать выбранные этапы,
скачивать артефакты и готовый Markdown-отчёт.
"""

import json
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.executor import POOL, schedule
from app.jobs import (
    DATA,
    LOCK,
    job_folder,
    load_job,
    mutate_job,
    now,
    save_job,
    stage_enabled,
)
from app.models import AnalyzeOptions, ReviewPatch
from app.pipeline import STAGES
from app.reporting import render_report

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024


@asynccontextmanager
async def lifespan(appServer):
    _recover_interrupted_jobs()

    yield

    POOL.shutdown(wait=True, cancel_futures=True)


def _recover_interrupted_jobs() -> None:
    for path in DATA.glob("*/job.json"):
        job = json.loads(path.read_text(encoding="utf-8"))

        if job["status"] not in ("queued", "running"):
            continue

        job["status"] = "partial"
        job["progress"] = (
            "Прошлый запуск был прерван. Повторите нужный этап."
        )

        for stage in job["stages"].values():
            if stage["status"] in ("pending", "running"):
                stage["status"] = "failed"
                stage["error"] = "Запуск прерван."

        save_job(job)


appServer = FastAPI(
    title="Local Video Evidence",
    lifespan=lifespan,
)


@appServer.get("/api/jobs")
def list_jobs():
    items = []

    with LOCK:
        for path in DATA.glob("*/job.json"):
            job = json.loads(path.read_text(encoding="utf-8"))

            items.append({
                key: job[key]
                for key in ("id", "name", "status", "created_at")
            })

    return sorted(
        items,
        key=lambda item: item["created_at"],
        reverse=True,
    )


@appServer.post("/api/jobs", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    options: str = Form("{}"),
):
    try:
        parsed = AnalyzeOptions.model_validate_json(options)
    except ValidationError as error:
        raise HTTPException(
            400,
            f"Некорректные настройки: {error}",
        ) from None

    job_id = uuid4().hex
    folder = job_folder(job_id)
    folder.mkdir()

    try:
        size = 0

        with (folder / "original.bin").open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)

                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413,
                        "Максимальный размер видео — 1 ГиБ.",
                    )

                target.write(chunk)

        if not size:
            raise HTTPException(400, "Файл пустой.")

        job = {
            "id": job_id,
            "name": Path(
                (file.filename or "video").replace("\\", "/")
            ).name,
            "status": "created",
            "progress": "Файл загружен",
            "created_at": now(),
            "updated_at": now(),
            "options": parsed.model_dump(),
            "stages": {
                name: {
                    "status": "pending",
                    "run_id": None,
                    "result_run_id": None,
                    "result": {},
                    "observations": [],
                    "history": [],
                    "error": None,
                    "note": None,
                }
                for name in STAGES
            },
        }

        save_job(job)
        schedule(job_id, list(STAGES))

        return {"id": job_id}

    except Exception:
        if not (folder / "job.json").exists():
            shutil.rmtree(folder, ignore_errors=True)
        raise

    finally:
        await file.close()


@appServer.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = load_job(job_id)

    for stage in job["stages"].values():
        stage["history_count"] = len(stage["history"])
        stage.pop("history")

    return job


@appServer.post("/api/jobs/{job_id}/retry/{stage}", status_code=202)
def retry_stage(job_id: str, stage: str):
    if stage not in STAGES:
        raise HTTPException(
            404,
            "Этап не найден.",
        )



    job = load_job(job_id)



    if not stage_enabled(stage, job["options"]):
        raise HTTPException(
            400,
            "Этап отключён. Создайте задание с другими настройками.",
        )



    if (
        stage != "prepare"
        and job["stages"]["prepare"]["status"] != "completed"
    ):
        raise HTTPException(
            409,
            "Сначала повторите подготовку видео.",
        )



    if stage == "prepare":
        selected = list(STAGES)


    elif stage == "scenes":
        selected = [
            "scenes",
            "ocr",
            "structure",
            "scene_objects",
            "visual_profile",
            "road_geometry",
            "location_evidence",
        ]


    elif stage == "ocr":
        selected = [
            "ocr",
            "structure",
            "scene_objects",
            "visual_profile",
            "road_geometry",
            "location_evidence",
        ]


    elif stage == "structure":
        selected = [
            "structure",
            "location_evidence",
        ]


    elif stage == "scene_objects":
        selected = [
            "scene_objects",
            "location_evidence",
        ]


    elif stage == "visual_profile":
        selected = [
            "visual_profile",
            "location_evidence",
        ]


    elif stage == "road_geometry":
        selected = [
            "road_geometry",
            "location_evidence",
        ]


    elif stage == "speech":
        selected = [
            "speech",
            "location_evidence",
        ]


    elif stage == "audio_structure":
        selected = [
            "audio_structure",
            "location_evidence",
        ]


    elif stage == "metadata":
        selected = [
            "metadata",
            "location_evidence",
        ]


    else:
        selected = [stage]



    schedule(job_id, selected)



    return {"status": "queued"}

@appServer.patch("/api/jobs/{job_id}/observations/{observation_id}")
def review_observation(
    job_id: str,
    observation_id: str,
    patch: ReviewPatch,
):
    def update(job):
        if job["status"] in ("queued", "running"):
            raise HTTPException(
                409,
                "Дождитесь завершения обработки.",
            )

        for stage in job["stages"].values():
            for item in stage["observations"]:
                if item["id"] == observation_id:
                    item["corrected_text"] = patch.text
                    item["review"] = patch.review
                    item["reviewed_at"] = now()
                    return

        raise HTTPException(404, "Наблюдение не найдено.")

    mutate_job(job_id, update)

    return {"status": "saved"}


@appServer.get("/api/jobs/{job_id}/files/{artifact_path:path}")
def get_artifact(job_id: str, artifact_path: str):
    load_job(job_id)

    folder = job_folder(job_id).resolve()
    runs = (folder / "runs").resolve()
    path = (folder / artifact_path).resolve()

    if not path.is_relative_to(runs) or not path.is_file():
        raise HTTPException(404, "Файл не найден.")

    return FileResponse(path)


@appServer.get("/api/jobs/{job_id}/export")
def export_job(job_id: str):
    load_job(job_id)

    return FileResponse(
        job_folder(job_id) / "job.json",
        media_type="application/json",
        filename=f"{job_id}.json",
    )


@appServer.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    with LOCK:
        job = load_job(job_id)

        if job["status"] in ("queued", "running"):
            raise HTTPException(
                409,
                "Нельзя удалить выполняющееся задание.",
            )

        shutil.rmtree(job_folder(job_id))

    return {"status": "deleted"}

@appServer.get("/api/jobs/{job_id}/report")
def export_markdown_report(job_id: str):
    with LOCK:
        job = load_job(job_id)

        if job["status"] in ("queued", "running"):
            raise HTTPException(
                409,
                "Дождитесь завершения обработки "
                "перед формированием отчёта.",
            )

        report = render_report(job)

        folder = job_folder(job_id)
        destination = folder / "report.md"
        temporary = folder / "report.md.tmp"

        temporary.write_text(
            report,
            encoding="utf-8",
        )

        temporary.replace(destination)

    # Отдаём снимок содержимого, а не общий изменяемый файл.
    from fastapi.responses import Response

    return Response(
        content=report.encode("utf-8"),
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                'attachment; filename="report.md"'
            ),
        },
    )

@appServer.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "video-service"
    }