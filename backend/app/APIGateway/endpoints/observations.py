"""Правки наблюдений и AI-описания объектов."""


from fastapi import (
    APIRouter,
    HTTPException,
)
from app.models.models import ReviewPatch
from app.APIGateway.jobs import (
    load_job,
    mutate_job,
    now,
)
from app.services.aiService import client as ai_client
from app.services.aiService.describe import (
    describe_unique_object,
    find_unique_object,
)
from app.storage import StorageService


router = APIRouter(prefix="/api/jobs")



@router.patch(
    "/{job_id}/observations/{observation_id}",
)
def review_observation(
    job_id: str,
    observation_id: str,
    patch: ReviewPatch,
):
    def update(job):
        if job.get("status") in (
            "queued",
            "running",
        ):
            raise HTTPException(
                409,
                "Дождитесь завершения обработки.",
            )


        for stage in job.get("stages", {}).values():
            for item in stage.get("observations", []):
                if item["id"] == observation_id:
                    item["corrected_text"] = patch.text
                    item["review"] = patch.review
                    item["reviewed_at"] = now()

                    return


        raise HTTPException(
            404,
            "Наблюдение не найдено.",
        )


    mutate_job(job_id, update)


    return {"status": "saved"}



@router.post(
    "/{job_id}/objects/{label}/ai-description",
)
def describe_object(
    job_id: str,
    label: str,
    refresh: bool = False,
):
    job = load_job(job_id)


    if job.get("status") in (
        "queued",
        "running",
    ):
        raise HTTPException(
            409,
            "Дождитесь завершения обработки.",
        )


    stages = job.get("stages") or {}
    stage = (
        stages.get("visual_analysis")
        or stages.get("scene_objects")
        or {}
    )

    item = find_unique_object(
        stage,
        label,
    )


    if item is None:
        raise HTTPException(
            404,
            "Объект не найден "
            "в результатах анализа.",
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
        raise HTTPException(
            503,
            str(error),
        ) from None


    except ai_client.AiServiceError as error:
        raise HTTPException(
            502,
            str(error),
        ) from None


    except Exception as error:
        raise HTTPException(
            500,
            "Не удалось получить AI-описание: "
            f"{str(error)[:500]}",
        ) from None


    description = payload["description"]


    def update(current):
        current_stages = current.get(
            "stages",
            {},
        )


        current_stage = (
            current_stages.get("visual_analysis")
            or current_stages.get("scene_objects")
            or {}
        )


        current_item = find_unique_object(
            current_stage,
            label,
        )


        if current_item is None:
            raise HTTPException(
                404,
                "Объект не найден.",
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