"""BEV-проекция для стадии place_profile.

Тонкая обёртка над bevService: собирает входные данные из
траектории и детекций visual_analysis, строит топологическую
карту и рендерит PNG в runs/<run_id>/bev_overlay.png.

Если данных меньше трёх пар, BEV не строится: bev = null.
"""

from __future__ import annotations

from pathlib import Path

from app.storage import StorageService


def build_bev_artifact(
    storage: StorageService,
    trajectory: dict,
    visual_result: dict,
    road: dict,
    camera_height_m: float = 1.2,
) -> dict | None:
    """Построить BEV и сохранить PNG, если хватает данных."""

    points = trajectory.get("points") or []

    if len(points) < 3:
        return None

    try:
        from app.services.bevService.projection import build_bev
        from app.services.bevService.render import render_bev_png

    except ImportError:
        return None

    detections_per_frame = [
        {
            "timestamp": frame.get("timestamp"),
            "artifact": frame.get("artifact"),
            "size": frame.get("size"),
            "detections": frame.get("detections") or [],
        }
        for frame in visual_result.get("frames") or []
    ]

    road_segments = road.get("episodes") or []

    try:
        bev = build_bev(
            trajectory=trajectory,
            detections_per_frame=detections_per_frame,
            road_segments=road_segments,
            camera_height_m=camera_height_m,
        )

    except Exception:
        return None

    if not bev:
        return None

    output = storage.run_path("bev_overlay.png")

    try:
        rendered = render_bev_png(bev, output)

    except Exception:
        return None

    bev["overlay_png"] = storage.relative(Path(rendered))

    return bev
