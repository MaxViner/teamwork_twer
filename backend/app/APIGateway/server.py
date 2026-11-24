"""FastAPI-приложение и маршруты API.

Принимает видео, создаёт задание, отдаёт статус и прогресс,
позволяет править наблюдения, запускать выбранные этапы,
скачивать артефакты и готовый Markdown-отчёт.

Все файловые операции задания (создание папки, запись исходника,
чтение/удаление артефактов, сохранение отчёта) идут через
StorageService — единую точку, которая знает раскладку.
"""

import json
import math
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
from pydantic import BaseModel, ValidationError

from app.APIGateway.executor import POOL, schedule
from app.APIGateway.jobs import (
    DATA,
    LOCK,
    load_job,
    mutate_job,
    now,
    save_job,
    stage_enabled,
)
from app.APIGateway.pipeline import STAGES
from app.models.models import AnalyzeOptions, ReviewPatch
from app.search import search_job
from app.services.aiService import client as ai_client
from app.services.aiService.describe import (
    describe_unique_object,
    find_unique_object,
)
from app.services.audioService.transcript import (
    to_srt,
    to_vtt,
    transcript_payload,
)
from app.services.geoInspectService.geo_scene import build_geo_scenes
from app.services.reportingService.reporting import render_evidence_json, render_report
from app.services.visyalInspectorService.keyframes import (
    collect_frames,
    group_frames,
    scene_intervals,
)
from app.storage import StorageService

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
    storage = StorageService.for_job(job_id)
    storage.folder.mkdir()

    try:
        size = 0

        with storage.open_source_for_write() as target:
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
        if not storage.job_json.exists():
            storage.delete_job()
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


@appServer.get("/api/jobs/{job_id}/status")
def get_job_status(job_id: str):
    """Small wire payload. Full job is fetched only when its revision changes.

    Current storage is one JSON document; load_job still parses it server-side.
    A dedicated status sidecar is required to avoid that backend cost.
    """
    job = load_job(job_id)
    return {"id": job["id"], "status": job.get("status"),
            "progress": job.get("progress"),
            "updated_at": job.get("updated_at"),
            "stage_progress": job.get("stage_progress", {}),
            "stages": {name: {"status": stage.get("status"),
                               "progress": stage.get("progress"),
                               "progress_message": stage.get("progress_message"),
                               "result_run_id": stage.get("result_run_id")}
                       for name, stage in (job.get("stages") or {}).items()}}


@appServer.get("/api/jobs/{job_id}/map-query")
def get_map_query(job_id: str):
    """Return compact, source-linked map-search hypotheses; never coordinates."""
    job = load_job(job_id)
    geo = build_geo_scenes(job.get("stages") or {})
    claims_by_id = {item["id"]: item for item in geo.get("claims") or []
                    if isinstance(item, dict) and item.get("id")}
    referenced = set()
    for scene in geo.get("scenes") or []:
        referenced.update(scene.get("claim_ids") or [])
        referenced.update(scene.get("region_claim_ids") or [])
    referenced.update(geo.get("unlocated_claim_ids") or [])

    claims = []
    for source_claim in geo.get("claims") or []:
        claim_id = source_claim.get("id") if isinstance(source_claim, dict) else None
        if claim_id not in referenced:
            continue
        claim = claims_by_id.get(claim_id)
        if not claim:
            continue
        claims.append({
            "id": claim.get("id"),
            "subject": claim.get("subject"),
            "predicate": claim.get("predicate"),
            "value": claim.get("value"),
            "modality": claim.get("modality"),
            "support_count": claim.get("support_count", 0),
            "support": [
                {key: evidence.get(key) for key in
                 ("source", "start", "end", "quote", "artifact", "review", "alignment")
                 if evidence.get(key) is not None}
                for evidence in (claim.get("support") or [])[:2]
                if isinstance(evidence, dict)
            ],
        })
        if len(claims) >= 50:
            break

    scenes = []
    for scene in (geo.get("scenes") or [])[:12]:
        scenes.append({
            "id": scene.get("id"),
            "start": scene.get("start"),
            "end": scene.get("end"),
            "kind": scene.get("kind"),
            "claim_ids": scene.get("claim_ids") or [],
            "frame_candidates": [
                {key: frame.get(key) for key in ("timestamp", "artifact", "visual_candidates")
                 if frame.get(key) is not None}
                for frame in (scene.get("frame_candidates") or [])[:3]
                if isinstance(frame, dict)
            ],
        })
    return {
        "schema_version": 1,
        "status": geo.get("status", "hypotheses_not_geolocation"),
        "map_queries": geo.get("map_queries") or {},
        "claims": claims,
        "scenes": scenes,
        "limits": geo.get("limits") or [],
        "coordinates": None,
        "external_sources_checked": False,
    }


@appServer.get("/api/ai/status")
def ai_status():
    """Показать, настроен ли AI-провайдер, без раскрытия ключа."""
    return ai_client.public_status()


@appServer.post(
    "/api/jobs/{job_id}/objects/{label}/ai-description"
)
def describe_object(
    job_id: str,
    label: str,
    refresh: bool = False,
):
    """AI-описание уникального объекта по лучшему кадру.

    Результат сохраняется в scene_objects.result.unique_objects,
    поэтому описание переживает перезагрузку страницы.
    """
    job = load_job(job_id)

    if job.get("status") in ("queued", "running"):
        raise HTTPException(
            409,
            "Дождитесь завершения обработки.",
        )

    stage = (job.get("stages") or {}).get(
        "scene_objects",
    ) or {}
    item = find_unique_object(stage, label)

    if item is None:
        raise HTTPException(
            404,
            "Объект не найден в результатах анализа.",
        )

    cached = item.get("ai_description")

    if cached and not refresh:
        return {
            "label": item.get("label"),
            "description": cached,
            "cached": True,
        }

    if not ai_client.is_configured():
        raise HTTPException(
            503,
            ai_client.not_configured_message(),
        )

    storage = StorageService.for_job(job_id)

    try:
        payload = describe_unique_object(
            storage,
            item,
            stage.get("result") or {},
        )

    except ai_client.AiNotConfigured as error:
        raise HTTPException(503, str(error)) from None

    except ai_client.AiServiceError as error:
        raise HTTPException(502, str(error)) from None

    except Exception as error:
        raise HTTPException(
            500,
            "Не удалось получить AI-описание: "
            f"{str(error)[:500]}",
        ) from None

    description = payload["description"]

    def update(current):
        current_stage = (current.get("stages") or {}).get(
            "scene_objects",
        ) or {}
        current_item = find_unique_object(
            current_stage,
            label,
        )

        if current_item is None:
            raise HTTPException(
                404,
                "Объект не найден в результатах анализа.",
            )

        current_item["ai_description"] = description
        current_item["ai_description_at"] = (
            description.get("created_at")
        )

    mutate_job(job_id, update)

    return {
        "label": item.get("label"),
        "description": description,
        "image": payload.get("image"),
        "cached": False,
    }


@appServer.get("/api/jobs/{job_id}/transcript.json")
def export_transcript_json(job_id: str):
    return transcript_payload(load_job(job_id))


@appServer.get("/api/jobs/{job_id}/transcript.vtt")
def export_transcript_vtt(job_id: str):
    from fastapi.responses import Response

    job = load_job(job_id)
    payload = transcript_payload(job)

    return Response(
        content=to_vtt(payload, job.get("name") or "Расшифровка"),
        media_type="text/vtt",
        headers={
            "Content-Disposition": (
                'attachment; filename="transcript.vtt"'
            ),
        },
    )


@appServer.get("/api/jobs/{job_id}/transcript.srt")
def export_transcript_srt(job_id: str):
    from fastapi.responses import Response

    payload = transcript_payload(load_job(job_id))

    return Response(
        content=to_srt(payload),
        media_type="application/x-subrip",
        headers={
            "Content-Disposition": (
                'attachment; filename="transcript.srt"'
            ),
        },
    )


@appServer.get("/api/jobs/{job_id}/search")
def search_inside_job(job_id: str, q: str = "", limit: int = 60):
    job = load_job(job_id)

    return {
        "query": q,
        "results": search_job(
            job,
            q,
            limit=max(1, min(200, limit)),
        ),
    }


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

    storage = StorageService.for_job(job_id)

    try:
        path = storage.resolve_in_runs(artifact_path)
    except ValueError:
        raise HTTPException(404, "Файл не найден.") from None

    if not path.is_file():
        raise HTTPException(404, "Файл не найден.")

    return FileResponse(path)


@appServer.get("/api/jobs/{job_id}/export")
def export_job(job_id: str):
    load_job(job_id)

    storage = StorageService.for_job(job_id)

    return FileResponse(
        storage.job_json,
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

        StorageService.for_job(job_id).delete_job()

    return {"status": "deleted"}


@appServer.get("/api/jobs/{job_id}/evidence")
def export_evidence(job_id: str):
    """Компактный версионированный JSON с уликами для геопоиска."""
    job = load_job(job_id)
    payload = render_evidence_json(job)

    from fastapi.responses import Response

    return Response(
        content=json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                'attachment; filename="evidence.json"'
            ),
        },
    )


def _page_bounds(page: int, page_size: int, total: int):
    page_size = max(1, min(60, page_size))
    pages = max(1, math.ceil(total / page_size))
    current = max(1, min(page, pages))
    start = (current - 1) * page_size
    return {
        "page": current,
        "page_size": page_size,
        "pages": pages,
        "total": total,
        "offset": start,
    }


@appServer.get("/api/jobs/{job_id}/keyframes")
def paged_keyframes(
    job_id: str,
    page: int = 1,
    page_size: int = 12,
    group: int | None = None,
):
    """
    Кадры и их локации постранично.

    Без group отдаёт страницу всех кадров и сводку локаций.
    С group — страницу кадров одной локации.
    """
    job = load_job(job_id)
    stages = job.get("stages") or {}
    frames = collect_frames(stages)
    groups = group_frames(
        frames,
        scene_intervals(stages),
    )

    summary = [
        {
            "number": item["number"],
            "start": item["start"],
            "end": item["end"],
            "frame_count": len(item["frames"]),
            "scene_numbers": item.get("scene_numbers") or [],
        }
        for item in groups
    ]

    if group is not None:
        selected = next(
            (
                item
                for item in groups
                if item["number"] == group
            ),
            None,
        )
        selected_frames = (
            selected["frames"] if selected else []
        )
    else:
        selected_frames = frames

    bounds = _page_bounds(
        page,
        page_size,
        len(selected_frames),
    )
    visible = selected_frames[
        bounds["offset"]:bounds["offset"] + bounds["page_size"]
    ]

    return {
        "mode": "group" if group is not None else "all",
        "group": group,
        "groups": summary,
        "frames": visible,
        **bounds,
    }


@appServer.get("/api/jobs/{job_id}/roads")
def paged_roads(
    job_id: str,
    page: int = 1,
    page_size: int = 8,
):
    """Дорожные эпизоды постранично вместе со схемой."""
    job = load_job(job_id)
    stage = (job.get("stages") or {}).get(
        "road_geometry",
    ) or {}
    result = stage.get("result") or {}
    episodes = [
        item
        for item in result.get("episodes") or []
        if isinstance(item, dict)
    ]

    bounds = _page_bounds(
        page,
        page_size,
        len(episodes),
    )
    visible = episodes[
        bounds["offset"]:bounds["offset"] + bounds["page_size"]
    ]

    return {
        "episodes": visible,
        "schematic": result.get("schematic") or {},
        "summary": result.get("summary") or {},
        **bounds,
    }


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

        StorageService.for_job(job_id).save_report(report)

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




class DevChatRequest(BaseModel):
    message: str
    web_search: bool = False
    system: str | None = None



@appServer.post("/api/dev/vision/describe")
async def dev_vision_describe(
    file: UploadFile = File(...),
    prompt: str = Form(""),
):
    """Тестовый анализ загруженного изображения через AI-сервис."""


    allowed = {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    }


    mime_type = (
        file.content_type or "image/jpeg"
    ).lower()


    if mime_type not in allowed:
        raise HTTPException(
            400,
            "Поддерживаются изображения JPEG, PNG, WebP и HEIC/HEIF.",
        )


    image_bytes = await file.read()


    if not image_bytes:
        raise HTTPException(400, "Файл изображения пустой.")


    if len(image_bytes) > 15 * 1024 * 1024:
        raise HTTPException(
            413,
            "Максимальный размер изображения — 15 МБ.",
        )


    if not ai_client.is_configured():
        raise HTTPException(
            503,
            ai_client.not_configured_message(),
        )


    user_prompt = prompt.strip() or (
        "Проанализируй изображение для геолокационного поиска. "
        "Верни JSON со следующими полями: "
        "short_description, detailed_description, "
        "main_objects (массив объектов с name и confidence), "
        "visible_text, location_clues, likely_place_types, "
        "search_queries, warnings."
    )


    try:
        result = ai_client.describe_image(
            image_bytes=image_bytes,
            mime_type=mime_type,
            prompt=user_prompt,
            json_mode=True,
        )


    except ai_client.AiNotConfigured as error:
        raise HTTPException(503, str(error)) from None


    except ai_client.AiServiceError as error:
        raise HTTPException(502, str(error)) from None


    except Exception as error:
        raise HTTPException(
            500,
            "Не удалось проанализировать изображение: "
            f"{str(error)[:500]}",
        ) from None


    parsed = _safe_json(result.get("text", ""))


    return {
        "provider": result.get("provider"),
        "model": result.get("model"),
        "analysis": parsed or result.get("text"),
        "raw_text": result.get("text"),
        "sources": result.get("sources", []),
        "search_queries": result.get("search_queries", []),
    }



@appServer.post("/api/dev/ai/chat")
def dev_ai_chat(request: DevChatRequest):
    """Тестовый чат с AI API без привязки к конкретному видео."""


    message = request.message.strip()


    if not message:
        raise HTTPException(400, "Сообщение пустое.")


    if not ai_client.is_configured():
        raise HTTPException(
            503,
            ai_client.not_configured_message(),
        )


    system = request.system or (
        "Ты — аккуратный аналитический ассистент. "
        "Отвечай по-русски, ясно и по существу. "
        "Если информации недостаточно, прямо скажи об этом."
    )


    try:
        result = ai_client.generate_text(
            prompt=message,
            system=system,
            web_search=request.web_search,
        )


    except ai_client.AiNotConfigured as error:
        raise HTTPException(503, str(error)) from None


    except ai_client.AiServiceError as error:
        raise HTTPException(502, str(error)) from None


    except Exception as error:
        raise HTTPException(
            500,
            "Не удалось получить ответ AI: "
            f"{str(error)[:500]}",
        ) from None


    return {
        "provider": result.get("provider"),
        "model": result.get("model"),
        "answer": result.get("text"),
        "sources": result.get("sources", []),
        "search_queries": result.get("search_queries", []),
    }



def _safe_json(text: str):
    try:
        value = json.loads(text)


        return value if isinstance(value, dict) else None


    except (json.JSONDecodeError, TypeError):
        return None