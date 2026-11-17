"""Распознавание речи.

Из превью извлекается аудио (WAV 16 кГц), модель faster-whisper
переводит речь в текст с таймкодами. Каждый непустой фрагмент
становится наблюдением с языком и уверенностью распознавания.
"""

from functools import lru_cache
from pathlib import Path
from typing import Callable


from app.errors import SkipStage
from app.media.ffmpeg import extract_audio
from app.observations import observation
from app.utils.packages import package_version
from app.utils.paths import relative


@lru_cache(maxsize=2)
def speech_model(name: str):
    from faster_whisper import WhisperModel

    return WhisperModel(
        name,
        device="cpu",
        compute_type="int8",
    )


def extract_speech(
    folder: Path,
    run_folder: Path,
    video: Path,
    prepared: dict,
    options: dict,
    progress: Callable[[float, str], None],
) -> dict:
    if not prepared["has_audio"]:
        raise SkipStage("Аудиодорожки нет.")

    audio = run_folder / "audio.wav"

    progress(1.0, "Извлекаю аудио")
    extract_audio(video, audio)

    progress(
        5.0,
        "Аудио готово, загружаю модель Whisper",
    )

    model = speech_model(options["whisper_model"])

    progress(
        10.0,
        "Модель загружена, начинаю распознавание",
    )

    segments, info = model.transcribe(
        str(audio),
        language=options.get("language") or None,
        vad_filter=True,
        word_timestamps=True,
    )

    observations = []
    offset = prepared.get("audio_start", 0.0)
    duration = prepared["duration"]

    for segment in segments:
        percent = min(
            99.0,
            10.0
            + float(segment.end)
            / max(duration, 0.001)
            * 89.0,
        )

        progress(
            percent,
            f"Распознаю речь: {percent:.0f}%",
        )

        text = segment.text.strip()

        if not text:
            continue

        item = _build_segment(
            folder=folder,
            audio=audio,
            duration=duration,
            offset=offset,
            segment=segment,
            options=options,
            info=info,
        )

        if item:
            observations.append(item)

    progress(100.0, "Распознавание речи завершено")
    
    return {
        "language": info.language,
        "language_probability": float(info.language_probability),
        "observations": observations,
    }


def _build_segment(
    folder: Path,
    audio: Path,
    duration: float,
    offset: float,
    segment,
    options: dict,
    info,
) -> dict | None:
    text = segment.text.strip()

    if not text:
        return None

    start = _clamp(float(segment.start) + offset, duration)
    end = _clamp(float(segment.end) + offset, duration, minimum=start)

    return observation(
        source="speech",
        start=start,
        end=end,
        text=text,
        artifact=relative(folder, audio),
        extractor="faster-whisper",
        data={
            "model": options["whisper_model"],
            "version": package_version("faster-whisper"),
            "language": info.language,
            "words": _build_words(segment.words or [], duration, offset),
            "time_is_approximate": True,
        },
    )


def _build_words(words, duration: float, offset: float) -> list[dict]:
    return [
        {
            "word": word.word,
            "start": _clamp(float(word.start) + offset, duration),
            "end": _clamp(float(word.end) + offset, duration),
            "probability": float(word.probability),
        }
        for word in words
    ]


def _clamp(
    value: float,
    maximum: float,
    minimum: float = 0.0,
) -> float:
    return min(maximum, max(minimum, value))