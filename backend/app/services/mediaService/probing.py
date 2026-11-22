"""Разбор ответа ffprobe.

Возвращает длительность, стартовое время и параметры потоков видео.
Используется на этапе подготовки, чтобы проверить файл и выбрать
корректные таймкоды.
"""

import json
import math

from app.utils.commands import command


def probe(path) -> dict:
    text = command([
        "ffprobe",
        "-v", "error",
        "-show_entries",
        (
            "format=duration,start_time:"
            "stream=codec_type,codec_name,width,height,"
            "duration,start_time,avg_frame_rate"
        ),
        "-of", "json",
        str(path),
    ])

    return json.loads(text)


def duration_of(info: dict) -> float:
    candidates = [
        info.get("format", {}).get("duration"),
        *[
            stream.get("duration")
            for stream in info.get("streams", [])
            if stream.get("codec_type") == "video"
        ],
    ]

    for candidate in candidates:
        try:
            value = float(candidate)
        except (TypeError, ValueError):
            continue

        if math.isfinite(value) and value > 0:
            return value

    raise RuntimeError("Не удалось определить длительность видео.")


def first_stream(info: dict, codec_type: str) -> dict | None:
    return next(
        (
            stream
            for stream in info.get("streams", [])
            if stream.get("codec_type") == codec_type
        ),
        None,
    )


def stream_start_time(stream: dict | None) -> float:
    if not stream:
        return 0.0

    try:
        return max(0.0, float(stream.get("start_time", 0)))
    except (TypeError, ValueError):
        return 0.0
