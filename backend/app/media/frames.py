"""Выбор кадров для анализа.

Считает равномерные моменты времени, добавляет середины найденных
сцен и убирает дубли. stage_frames сохраняет выбранные кадры,
чтобы OCR, визуальный профиль и дорога работали по одним и тем же
изображениям.
"""

from pathlib import Path

from app.media.ffmpeg import extract_frame
from app.utils.paths import relative


def select_timestamps(
    duration: float,
    count: int,
    stages: dict,
) -> list[float]:
    count = max(1, int(count))

    times = [
        duration * (index + 0.5) / count
        for index in range(count)
    ]

    times.extend(_scene_centers(stages))

    times = sorted({
        round(min(max(0.0, value), duration * 0.999), 6)
        for value in times
    })

    return _limit_timestamps(times, count)


def _scene_centers(stages: dict) -> list[float]:
    stage = stages.get("scenes", {})

    if stage.get("status") != "completed":
        return []

    intervals = stage.get("result", {}).get(
        "intervals",
        [],
    )

    return [
        (float(start) + float(end)) / 2
        for start, end in intervals
    ]


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
