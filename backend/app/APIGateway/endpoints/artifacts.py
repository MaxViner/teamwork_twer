"""Файлы, кадры и дорожные эпизоды задания."""


import math

from fastapi import (
    APIRouter,
    HTTPException,
)
from fastapi.responses import FileResponse


from app.APIGateway.jobs import load_job
from app.services.visyalInspectorService.keyframes import (
    collect_frames,
    group_frames,
    scene_intervals,
)
from app.storage import StorageService


router = APIRouter(prefix="/api/jobs")



@router.get("/{job_id}/files/{artifact_path:path}")
def get_artifact(
    job_id: str,
    artifact_path: str,
):
    load_job(job_id)
    storage = StorageService.for_job(job_id)


    try:
        path = storage.resolve_in_runs(
            artifact_path,
        )


    except ValueError:
        raise HTTPException(
            404,
            "Файл не найден.",
        ) from None


    if not path.is_file():
        raise HTTPException(
            404,
            "Файл не найден.",
        )


    return FileResponse(path)



@router.get("/{job_id}/keyframes")
def paged_keyframes(
    job_id: str,
    page: int = 1,
    page_size: int = 12,
    group: int | None = None,
):
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
            "scene_numbers": item.get(
                "scene_numbers",
                [],
            ),
        }
        for item in groups
    ]


    selected = None


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
        selected["frames"]
        if selected
        else frames
    )


    bounds = _page_bounds(
        page,
        page_size,
        len(selected_frames),
    )


    visible = selected_frames[
        bounds["offset"]:
        bounds["offset"] + bounds["page_size"]
    ]


    return {
        "mode": (
            "group"
            if group is not None
            else "all"
        ),
        "group": group,
        "groups": summary,
        "frames": visible,
        **bounds,
    }



@router.get("/{job_id}/roads")
def paged_roads(
    job_id: str,
    page: int = 1,
    page_size: int = 8,
):
    job = load_job(job_id)
    stages = job.get("stages") or {}
    stage = stages.get("place_profile") or {}
    result = stage.get("result") or {}
    road = result.get("road") or {}


    if not road:
        road = (
            (stages.get("road_geometry") or {})
            .get("result")
        ) or {}


    episodes = [
        item
        for item in road.get("episodes") or []
        if isinstance(item, dict)
    ]


    bounds = _page_bounds(
        page,
        page_size,
        len(episodes),
    )


    visible = episodes[
        bounds["offset"]:
        bounds["offset"] + bounds["page_size"]
    ]


    return {
        "episodes": visible,
        "schematic": road.get("schematic") or {},
        "summary": road.get("summary") or {},
        **bounds,
    }



def _page_bounds(
    page: int,
    page_size: int,
    total: int,
):
    page_size = max(
        1,
        min(60, page_size),
    )


    pages = max(
        1,
        math.ceil(total / page_size),
    )


    current = max(
        1,
        min(page, pages),
    )


    start = (current - 1) * page_size


    return {
        "page": current,
        "page_size": page_size,
        "pages": pages,
        "total": total,
        "offset": start,
    }