"""Подготовка видео к анализу.

Проверяет ffmpeg/ffprobe, читает длительность и разрешение исходника,
считает SHA-256 файла и перекодирует видео в лёгкий MP4-превью.
Дальше все этапы работают уже с превью, а не с оригиналом.
"""

from pathlib import Path
from typing import Callable

from app.config import MAX_DURATION_SECONDS, MAX_SOURCE_PIXELS
from app.services.mediaService.ffmpeg import make_preview_with_progress
from app.services.mediaService.probing import (
    duration_of,
    first_stream,
    probe,
    stream_start_time,
)
from app.utils.observations import observation
from app.utils.commands import require_tools
from app.utils.hashing import sha256_of
from app.utils.paths import relative


def prepare(
    folder: Path,
    run_folder: Path,
    progress: Callable[[float, str], None],
) -> dict:
    require_tools("ffmpeg", "ffprobe")

    source = folder / "original.bin"
    source_info = probe(source)

    video_stream = _require_video_stream(source_info)
    duration = _require_allowed_duration(source_info)
    width, height = _require_frame_size(video_stream)

    progress(0.0, "Считаю SHA-256 исходного файла")
    digest = sha256_of(source)

    progress(0.0, "Создаю MP4 для просмотра и анализа")

    preview = run_folder / "preview.mp4"

    make_preview_with_progress(
        source=source,
        destination=preview,
        duration=duration,
        on_progress=progress,
    )

    preview_info = probe(preview)
    preview_duration = duration_of(preview_info)
    audio_stream = first_stream(preview_info, "audio")

    result = {
        "preview": relative(folder, preview),
        "duration": preview_duration,
        "has_audio": audio_stream is not None,
        "audio_start": stream_start_time(audio_stream),
        "sha256": digest,
        "source_info": source_info,
        "preview_info": preview_info,
    }

    result["observations"] = [
        observation(
            source="technical",
            text=(
                f"Исходник: {width}×{height}; "
                f"длительность: {duration:.2f} с; "
                f"аудио: {'есть' if audio_stream else 'нет'}"
            ),
            extractor="ffprobe",
            data={
                "sha256": digest,
                "source_info": source_info,
            },
        )
    ]

    return result


def _require_video_stream(info: dict) -> dict:
    stream = first_stream(info, "video")

    if stream is None:
        raise RuntimeError("В файле нет видеопотока.")

    return stream


def _require_allowed_duration(info: dict) -> float:
    duration = duration_of(info)

    if duration > MAX_DURATION_SECONDS:
        raise RuntimeError(
            "Для этой версии разрешены видео до 20 минут."
        )

    return duration


def _require_frame_size(stream: dict) -> tuple[int, int]:
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))

    if width <= 0 or height <= 0:
        raise RuntimeError("Не удалось определить размер кадра.")

    if width * height > MAX_SOURCE_PIXELS:
        raise RuntimeError(
            "Разрешение исходного видео превышает лимит MVP."
        )

    return width, height