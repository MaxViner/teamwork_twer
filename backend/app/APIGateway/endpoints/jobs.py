"""Endpoints заданий анализа видео."""


import json

from app.APIGateway.jobs import DATA
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    File,
    Form,
    HTTPException,
    UploadFile,
)

from pydantic import ValidationError


from app.APIGateway.executor import schedule
from app.APIGateway.jobs import (
    LOCK,
    load_job,
    now,
    save_job,
    stage_enabled,
)
from app.APIGateway.pipeline import STAGES
from app.models.models import AnalyzeOptions
from app.services.geoInspectService.geo_scene import build_geo_scenes
from app.storage import StorageService


router = APIRouter(prefix="/api/jobs")

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024



@router.get("")
def list_jobs():
    items = []


    with LOCK:
        for path in (DATA := __import__(
            "app.APIGateway.jobs",
            fromlist=["DATA"],
        ).DATA).glob("*/job.json"):
            job = json.loads(
                path.read_text(
                    encoding="utf-8",
                )
            )


            items.append({
                key: job[key]
                for key in (
                    "id",
                    "name",
                    "status",
                    "created_at",
                )
            })


    return sorted(
        items,
        key=lambda item: item["created_at"],
        reverse=True,
    )



@router.post("", status_code=202)
async def create_job(
    file: UploadFile = File(...),
    options: str = Form("{}"),
):
    try:
        parsed = AnalyzeOptions.model_validate_json(
            options,
        )


    except ValidationError as error:
        raise HTTPException(
            400,
            f"Некорректные настройки: {error}",
        ) from None


    job_id = uuid4().hex
    storage = StorageService.for_job(job_id)
    storage.folder.mkdir()


    try:
        size = 0


        with storage.open_source_for_write() as target:
            while chunk := await file.read(
                1024 * 1024,
            ):
                size += len(chunk)


                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413,
                        "Максимальный размер видео — 1 ГиБ.",
                    )


                target.write(chunk)


        if not size:
            raise HTTPException(
                400,
                "Файл пустой.",
            )


        job = {
            "id": job_id,
            "name": Path(
                (file.filename or "video").replace(
                    "\\",
                    "/",
                )
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
        schedule(
            job_id,
            list(STAGES),
        )


        return {"id": job_id}


    except Exception:
        if not storage.job_json.exists():
            storage.delete_job()


        raise


    finally:
        await file.close()



@router.get("/{job_id}")
def get_job(job_id: str):
    job = load_job(job_id)


    for stage in job.get("stages", {}).values():
        stage["history_count"] = len(
            stage.get("history", []),
        )


        stage.pop("history", None)


    return job



@router.get("/{job_id}/status")
def get_job_status(job_id: str):
    job = load_job(job_id)


    return {
        "id": job["id"],
        "status": job.get("status"),
        "progress": job.get("progress"),
        "updated_at": job.get("updated_at"),
        "stage_progress": job.get(
            "stage_progress",
            {},
        ),
        "stages": {
            name: {
                "status": stage.get("status"),
                "progress": stage.get("progress"),
                "progress_message": stage.get(
                    "progress_message",
                ),
                "result_run_id": stage.get(
                    "result_run_id",
                ),
            }
            for name, stage in (
                job.get("stages") or {}
            ).items()
        },
    }



@router.get("/{job_id}/map-query")
def get_map_query(job_id: str):
    job = load_job(job_id)
    geo = build_geo_scenes(
        job.get("stages") or {},
    )


    return {
        "schema_version": 1,
        "status": geo.get(
            "status",
            "hypotheses_not_geolocation",
        ),
        "map_queries": geo.get("map_queries") or {},
        "claims": geo.get("claims") or [],
        "scenes": geo.get("scenes") or [],
        "limits": geo.get("limits") or [],
        "coordinates": None,
        "external_sources_checked": False,
    }



@router.post(
    "/{job_id}/retry/{stage}",
    status_code=202,
)
def retry_stage(
    job_id: str,
    stage: str,
):
    if stage not in STAGES:
        raise HTTPException(
            404,
            "Этап не найден.",
        )


    job = load_job(job_id)


    if not stage_enabled(
        stage,
        job["options"],
    ):
        raise HTTPException(
            400,
            "Этап отключён. Создайте задание "
            "с другими настройками.",
        )


    if (
        stage != "prepare"
        and job["stages"]["prepare"]["status"]
        != "completed"
    ):
        raise HTTPException(
            409,
            "Сначала повторите подготовку видео.",
        )


    schedule(
        job_id,
        _stages_for_retry(stage),
    )


    return {"status": "queued"}



def _stages_for_retry(stage: str) -> list[str]:
    if stage == "prepare":
        return list(STAGES)


    if stage == "scenes":
        return [
            "scenes",
            "ocr",
            "structure",
            "visual_analysis",
            "place_profile",
            "location_evidence",
        ]


    if stage == "ocr":
        return [
            "ocr",
            "structure",
            "visual_analysis",
            "place_profile",
            "location_evidence",
        ]


    if stage == "structure":
        return [
            "structure",
            "location_evidence",
        ]


    if stage == "visual_analysis":
        return [
            "visual_analysis",
            "place_profile",
            "location_evidence",
        ]


    if stage == "place_profile":
        return [
            "place_profile",
            "location_evidence",
        ]


    if stage == "location_prompt":
        return [
            "location_evidence",
            "summary",
            "location_prompt",
        ]


    if stage == "speech":
        return [
            "speech",
            "location_evidence",
        ]


    if stage == "audio_structure":
        return [
            "audio_structure",
            "location_evidence",
        ]


    if stage == "metadata":
        return [
            "metadata",
            "location_evidence",
        ]


    return [stage]