"""Консолидированная стадия place_profile.

Один проход по кадрам visual_analysis объединяет бывшие стадии
road_geometry и landmarks и добавляет два новых блока:

- road — геометрия дороги, эпизоды и схема (Hough);
- geometry/landmarks — горизонт, точка схода, симметрия, силуэт и
  узнаваемые ориентиры;
- odometry — ORB + essential matrix по последовательным кадрам;
- bev — топологическая карта сверху, если хватает данных.

Старые имена полей сохранены: result.road повторяет результат
road_geometry, result.geometry и result.landmarks — результат
landmarks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.services.mediaService.frames import (
    analysis_frame_count,
    stage_frames,
)
from app.services.placeProfileService import bev as bev_module
from app.services.placeProfileService import geometry as geometry_module
from app.services.placeProfileService import odometry as odometry_module
from app.services.placeProfileService import road as road_module
from app.storage import StorageService
from app.utils.errors import SkipStage
from app.utils.observations import observation


ROAD_SHARE = 30.0
GEOMETRY_SHARE = 20.0
ODOMETRY_SHARE = 30.0
BEV_SHARE = 20.0


def extract_place_profile(
    storage: StorageService,
    video: Path,
    duration: float,
    stages: dict,
    options: dict,
    progress: Callable[[float, str], None],
) -> dict:
    """Собрать профиль места: дорога, геометрия, одометрия и BEV."""

    visual_result = (
        (stages.get("visual_analysis") or {}).get("result") or {}
    )

    frames = _frames(
        storage,
        video,
        duration,
        stages,
        options,
        visual_result,
    )

    if not frames:
        raise SkipStage(
            "Нет кадров для профиля места: визуальный анализ "
            "не завершён."
        )

    road = road_module.extract_road(
        frames,
        visual_result,
        stages,
        duration,
        _scaled(progress, 0.0, ROAD_SHARE),
    )

    geometry = geometry_module.extract_geometry(
        frames,
        visual_result,
        stages,
        _scaled(progress, ROAD_SHARE, GEOMETRY_SHARE),
    )

    odometry = odometry_module.extract_odometry(
        frames,
        visual_result,
        stages,
        road.get("summary"),
        _scaled(
            progress,
            ROAD_SHARE + GEOMETRY_SHARE,
            ODOMETRY_SHARE,
        ),
    )

    progress(
        ROAD_SHARE + GEOMETRY_SHARE + ODOMETRY_SHARE,
        "Строю BEV-проекцию",
    )

    bev = bev_module.build_bev_artifact(
        storage,
        odometry.get("trajectory") or {},
        visual_result,
        road,
    )

    progress(100, "Профиль места готов")

    observations = [
        *(road.get("observations") or []),
        *(geometry.get("observations") or []),
        *(odometry.get("observations") or []),
    ]

    if bev:
        observations.append(
            observation(
                source="place_profile",
                start=0.0,
                end=float(duration or 0.0),
                text=(
                    "BEV-проекция построена: топологическая карта "
                    "без метрики."
                ),
                artifact=bev.get("overlay_png"),
                extractor="bev-projection",
                data={
                    "kind": "bev_summary",
                    "grid": bev.get("grid"),
                    "objects": len(bev.get("objects") or []),
                    "scale_source": bev.get("scale_source"),
                    "requires_review": True,
                    "map_match_ready": False,
                },
            )
        )

    road_result = _without(road, "observations")
    odometry_result = _without(odometry, "observations")

    return {
        "road": road_result,
        "geometry": geometry.get("geometry") or {},
        "geometry_frames": geometry.get("frames") or [],
        "geometry_frame_count": geometry.get("frame_count_total", 0),
        "landmarks": geometry.get("landmarks") or [],
        "landmark_count": geometry.get("landmark_count", 0),
        "odometry": odometry_result,
        "bev": bev,
        "observations": observations,
        "note": (
            "Дорога, геометрия и ориентиры описаны в координатах "
            "кадра; одометрия даёт относительную траекторию, BEV — "
            "топологию. Это не подтверждённые координаты."
        ),
    }


def _frames(
    storage: StorageService,
    video: Path,
    duration: float,
    stages: dict,
    options: dict,
    visual_result: dict,
) -> list[dict]:
    """Взять кадры visual_analysis или извлечь свои."""

    frames = []

    for frame in visual_result.get("frames") or []:
        artifact = frame.get("artifact")

        if not artifact:
            continue

        path = storage.resolve(artifact)

        if not path.is_file():
            continue

        frames.append({
            "timestamp": float(frame["timestamp"]),
            "artifact": artifact,
            "path": path,
        })

    if frames:
        return frames

    return stage_frames(
        folder=storage.folder,
        run_folder=storage.run_dir,
        video=video,
        duration=duration,
        stages=stages,
        count=analysis_frame_count(options),
        prefix="road",
    )


def _scaled(
    progress: Callable[[float, str], None],
    start: float,
    span: float,
) -> Callable[[float, str], None]:
    """Сдвинуть прогресс подэтапа в общий диапазон стадии."""

    def report(percent: float, message: str | None = None) -> None:
        value = max(0.0, min(100.0, float(percent)))
        progress(
            start + span * value / 100.0,
            message or "",
        )

    return report


def _without(data: dict, key: str) -> dict:
    """Копия словаря без служебного ключа."""

    return {
        name: value
        for name, value in data.items()
        if name != key
    }
