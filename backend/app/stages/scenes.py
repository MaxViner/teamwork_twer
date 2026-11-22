"""Поиск сцен в видео.

Библиотека PySceneDetect ищет моменты резкой смены картинки.
Полученные интервалы сохраняются как наблюдения и используются
другими этапами, чтобы брать кадры из середины каждой сцены.
"""

from pathlib import Path
from typing import Callable

from app.utils.observations import observation
from app.utils.packages import package_version


def extract_scenes(
    folder: Path,
    run_folder: Path,
    video: Path,
    duration: float,
    progress: Callable[[float, str], None],
) -> dict:
    progress(0.0, "Ищу смены сцен")

    intervals = _detect_intervals(
        video,
        duration,
    )

    observations = _build_observations(
        duration,
        intervals,
    )

    progress(
        100.0,
        f"Найдено сцен: {len(intervals)}",
    )

    return {
        "intervals": intervals,
        "scene_count": len(intervals),
        "observations": observations,
    }


def _detect_intervals(
    video: Path,
    duration: float,
) -> list[list[float]]:
    from scenedetect import ContentDetector, detect

    detected = detect(
        str(video),
        ContentDetector(),
        start_in_scene=True,
    )

    intervals = [
        [
            start.get_seconds(),
            end.get_seconds(),
        ]
        for start, end in detected
    ]

    return intervals or [[0.0, duration]]


def _build_observations(
    duration: float,
    intervals: list[list[float]],
) -> list[dict]:
    """Складывает все сцены в одно наблюдение-сводку."""

    if not intervals:
        return []

    normalized = [
        [
            max(0.0, float(start)),
            min(duration, float(end)),
        ]
        for start, end in intervals
    ]

    total = sum(
        end - start
        for start, end in normalized
    )

    average = total / len(normalized)

    return [
        observation(
            source="scene",
            start=normalized[0][0],
            end=normalized[-1][1],
            text=(
                f"Сцены: {len(normalized)}. "
                "Средняя длительность: "
                f"{_format_duration(average)}."
            ),
            extractor="PySceneDetect",
            data={
                "scene_count": len(normalized),
                "total_seconds": round(total, 3),
                "intervals": [
                    [
                        round(start, 3),
                        round(end, 3),
                    ]
                    for start, end in normalized[:100]
                ],
                "intervals_truncated": (
                    len(normalized) > 100
                ),
                "version": package_version(
                    "scenedetect"
                ),
                "time_is_approximate": True,
            },
        )
    ]


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, seconds = divmod(total, 60)

    return f"{minutes}:{seconds:02d}"