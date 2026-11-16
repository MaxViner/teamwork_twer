from pathlib import Path
from typing import Callable

from app.observations import observation
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
    return [
        observation(
            source="scene",
            start=max(0.0, start),
            end=min(duration, end),
            text=f"Сцена {index + 1}",
            extractor="PySceneDetect",
            data={
                "version": package_version(
                    "scenedetect"
                ),
                "time_is_approximate": True,
            },
        )
        for index, (start, end) in enumerate(intervals)
    ]