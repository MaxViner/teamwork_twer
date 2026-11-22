"""Выбор кадров для анализа.

Считает равномерные моменты времени, добавляет середины найденных
сцен и убирает слишком близкие дубли. Один и тот же набор кадров
используют OCR, визуальный профиль, объекты и геометрия дороги.
"""

from pathlib import Path

from app.config import (
    DEFAULT_ANALYSIS_FRAMES,
    MAX_ANALYSIS_FRAMES,
    MIN_FRAME_SPACING_SECONDS,
)
from app.services.mediaService.ffmpeg import extract_frame
from app.utils.paths import relative


def analysis_frame_count(options: dict) -> int:
    """Сколько кадров запросил пользователь с учётом лимита."""
    try:
        value = int(options.get(
            "max_frames",
            DEFAULT_ANALYSIS_FRAMES,
        ))

    except (TypeError, ValueError):
        value = DEFAULT_ANALYSIS_FRAMES

    return max(1, min(MAX_ANALYSIS_FRAMES, value))


def select_timestamps(
    duration: float,
    count: int,
    stages: dict,
) -> list[float]:
    count = max(1, int(count))

    if duration <= 0:
        return []

    # Для короткого клипа не имеет смысла брать тысячи почти
    # одинаковых кадров: держим минимальный шаг между ними.
    uniform_count = min(
        count,
        max(
            1,
            int(duration / MIN_FRAME_SPACING_SECONDS) + 1,
        ),
    )

    times = [
        duration * (index + 0.5) / uniform_count
        for index in range(uniform_count)
    ]

    times.extend(_scene_centers(stages))

    times = sorted({
        round(min(max(0.0, value), duration * 0.999), 6)
        for value in times
    })

    return _thin(_limit_timestamps(times, count))


def _scene_centers(stages: dict) -> list[float]:
    stage = stages.get("scenes", {})

    if stage.get("status") != "completed":
        return []

    intervals = stage.get("result", {}).get(
        "intervals",
        [],
    )

    centers = []

    for value in intervals:
        if not isinstance(value, (list, tuple)):
            continue

        if len(value) < 2:
            continue

        centers.append(
            (float(value[0]) + float(value[1])) / 2
        )

    return centers


def _limit_timestamps(
    times: list[float],
    count: int,
) -> list[float]:
    if len(times) <= count:
        return times

    return [
        times[
            min(
                len(times) - 1,
                int((index + 0.5) * len(times) / count),
            )
        ]
        for index in range(count)
    ]


def _thin(times: list[float]) -> list[float]:
    """Убирает кадры, которые стоят почти вплотную."""
    result = []

    for value in times:
        if (
            result
            and value - result[-1] < MIN_FRAME_SPACING_SECONDS
        ):
            continue

        result.append(value)

    return result


def ocr_frames(folder: Path, stages: dict) -> list[dict]:
    stage = stages.get("ocr", {})

    if stage.get("status") != "completed":
        return []

    frames = []

    for item in stage.get("result", {}).get("frames", []):
        artifact = item.get("artifact")

        if not artifact:
            continue

        path = folder / artifact

        if not path.is_file():
            continue

        frames.append({
            "timestamp": float(item.get("timestamp", 0.0)),
            "artifact": artifact,
            "path": path,
        })

    return frames


def stage_frames(
    folder: Path,
    run_folder: Path,
    video: Path,
    duration: float,
    stages: dict,
    count: int,
    prefix: str = "frame",
) -> list[dict]:
    """Переиспользует кадры OCR либо извлекает собственные."""

    frames = ocr_frames(folder, stages)

    if frames:
        return frames[: max(1, int(count))]

    saved = []

    for index, timestamp in enumerate(
        select_timestamps(duration, count, stages)
    ):
        destination = run_folder / (
            f"{prefix}_{index:03d}.jpg"
        )

        extract_frame(video, destination, timestamp)

        saved.append({
            "timestamp": timestamp,
            "artifact": relative(folder, destination),
            "path": destination,
        })

    return saved
