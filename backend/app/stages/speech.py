"""Распознавание речи.

Из превью извлекается аудио (WAV 16 кГц), модель faster-whisper
переводит речь в текст с таймкодами. Все реплики складываются
в одно наблюдение-сводку со списком сегментов: так карточка
занимает одну строку интерфейса, а таймкоды остаются доступны.
"""

from functools import lru_cache
from pathlib import Path
from typing import Callable


from app.errors import SkipStage
from app.media.ffmpeg import extract_audio
from app.media.voice import assign_speakers
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

    speech_segments = []
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

        start = _clamp(
            float(segment.start) + offset,
            duration,
        )
        end = _clamp(
            float(segment.end) + offset,
            duration,
            minimum=start,
        )

        speech_segments.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
            **_words(segment, offset, duration),
        })

    progress(100.0, "Распознавание речи завершено")

    speech_segments, speakers, speaker_method = assign_speakers(
        audio,
        speech_segments,
    )

    observations = _build_observations(
        folder=folder,
        audio=audio,
        segments=speech_segments,
        options=options,
        info=info,
        speakers=speakers,
        speaker_method=speaker_method,
    )

    return {
        "language": info.language,
        "language_probability": float(info.language_probability),
        "segment_count": len(speech_segments),
        "segments": speech_segments,
        "speakers": speakers,
        "speaker_method": speaker_method,
        "observations": observations,
    }


def _build_observations(
    folder: Path,
    audio: Path,
    segments: list[dict],
    options: dict,
    info,
    speakers: list[dict] | None = None,
    speaker_method: str | None = None,
) -> list[dict]:
    """Складывает все реплики в одно наблюдение-сводку."""

    if not segments:
        return []

    return [
        observation(
            source="speech",
            start=segments[0]["start"],
            end=segments[-1]["end"],
            text="\n".join(
                item["text"]
                for item in segments
            ),
            artifact=relative(folder, audio),
            extractor="faster-whisper",
            data={
                "model": options["whisper_model"],
                "version": package_version("faster-whisper"),
                "language": info.language,
                "segment_count": len(segments),
                "segments": segments,
                "speakers": speakers or [],
                "speaker_method": speaker_method,
                "time_is_approximate": True,
            },
        )
    ]


def _clamp(
    value: float,
    maximum: float,
    minimum: float = 0.0,
) -> float:
    return min(maximum, max(minimum, value))


def _words(segment, offset: float, duration: float) -> dict:
    """
    Таймкоды слов и оценка уверенности реплики.

    Слова нужны для точного перехода внутри фразы и для экспорта
    субтитров. Низкая оценка помечает фрагмент как вероятно
    неточный, а не как гарантированно распознанный.
    """
    words = []

    for item in getattr(segment, "words", None) or []:
        word = str(getattr(item, "word", "") or "").strip()

        if not word:
            continue

        start = _clamp(float(item.start) + offset, duration)
        end = _clamp(
            float(item.end) + offset,
            duration,
            minimum=start,
        )

        words.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "word": word,
            "probability": round(
                float(getattr(item, "probability", 0) or 0),
                3,
            ),
        })

    probabilities = [
        item["probability"]
        for item in words
        if item["probability"]
    ]

    probability = (
        round(sum(probabilities) / len(probabilities), 3)
        if probabilities
        else None
    )

    return {
        "words": words,
        "probability": probability,
        "uncertain": bool(
            probability is not None and probability < 0.5
        ),
    }