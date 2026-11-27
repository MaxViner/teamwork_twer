"""Аудиопрофиль и семантические звуки.

Две независимые части:
1. Профиль громкости (RMS/тишина/громкость/спектр) — «тихая
   среда», «шумная среда», карта громких участков. Полезно для
   контекста, но не для геолокации.
2. Семантические звуки (YAMNet): поезд, сирена, церковный
   колокол, вертолёт, стройка и т.д. Это реальные улики для
   определения места.

Наблюдения создаются только сводные — по одному на тип звука.
Поштучные события сохраняются в result.sound_events для UI.
"""

import math
import wave
from pathlib import Path

import numpy as np

from app.storage import StorageService
from app.utils.commands import command
from app.utils.errors import SkipStage
from app.utils.observations import observation

from app.services.audioService.sound_events import (
    YamnetDetector,
    model_available,
    model_note,
    summarize,
)
from app.services.weakCluesService import birdnet, infrastructure


AUDIO_RATE = 16000
WINDOW_SECONDS = 1.0
SILENCE_RMS = 0.005
LOUD_RMS = 0.08


def extract_audio_structure(
    storage: StorageService,
    video: Path,
    prepared: dict,
    progress,
) -> dict:
    if not prepared["has_audio"]:
        raise SkipStage("Аудиодорожки нет.")

    audio_path = storage.run_path("audio_structure.wav")

    progress(0, "Извлекаю аудио")

    command([
        "ffmpeg", "-nostdin", "-y", "-v", "error",
        "-i", str(video),
        "-map", "0:a:0",
        "-vn",
        "-ac", "1",
        "-ar", str(AUDIO_RATE),
        "-c:a", "pcm_s16le",
        str(audio_path),
    ])

    # 1. Профиль громкости (быстро, ~секунда)
    progress(20, "Считаю профиль громкости")
    windows = _volume_windows(audio_path, prepared)
    profile = _build_profile(windows)

    # 2. Семантические звуки (YAMNet, если модель есть)
    sound_events: list[dict] = []
    sound_summary: list[dict] = []
    sound_model_note: str | None = None

    if model_available():
        progress(45, "Распознаю звуковые события")

        try:
            waveform = _load_waveform(audio_path)
            detector = YamnetDetector()
            sound_events = detector.analyze(waveform)
            sound_summary = summarize(sound_events)
        except Exception as error:
            sound_model_note = (
                f"YAMNet недоступен: {str(error)[:200]}"
            )
    else:
        sound_model_note = model_note()

    # 3. Птицы (BirdNET) и класс дорожного шума. BirdNET требует
    # 48 кГц, поэтому отдельный WAV извлекается только при наличии
    # модели — иначе лишняя работа и лишний файл.
    bird_species: list[dict] = []
    bird_clues: list[dict] = []
    bird_model_note: str | None = None

    if birdnet.model_available():
        progress(70, "Распознаю птиц (BirdNET)")

        try:
            bird_path = storage.run_path("audio_birdnet.wav")
            command([
                "ffmpeg", "-nostdin", "-y", "-v", "error",
                "-i", str(video),
                "-map", "0:a:0",
                "-vn",
                "-ac", "1",
                "-ar", "48000",
                "-c:a", "pcm_s16le",
                str(bird_path),
            ])
            bird_result = birdnet.analyze_audio(bird_path)
            bird_species = bird_result.get("detections") or []
            bird_clues = birdnet.species_clues(
                bird_species,
                float(prepared.get("duration") or 0.0),
            )
            bird_model_note = bird_result.get("note")
        except Exception as error:  # noqa: BLE001
            bird_model_note = (
                f"BirdNET недоступен: {str(error)[:200]}"
            )
    else:
        bird_model_note = birdnet.model_note()

    road_class = infrastructure.classify_road_noise(profile)

    progress(90, "Формирую наблюдения")
    observations = _build_observations(
        sound_summary,
        profile,
        bird_clues,
        road_class,
    )

    progress(100, "Аудиальный анализ завершён")

    return {
        "sound_events": sound_events,
        "sound_summary": sound_summary,
        "profile": profile,
        "bird_species": bird_species,
        "bird_clues": bird_clues,
        "bird_model_note": bird_model_note,
        "road_noise": (
            {"road_class": road_class}
            if road_class else None
        ),
        "observations": observations,
        "model": "yamnet-onnx" if sound_events else None,
        "window_seconds": WINDOW_SECONDS,
        "note": sound_model_note or (
            "Распознаются классы AudioSet, полезные как "
            "географические улики: транспорт, сирены, колокола, "
            "природа, стройка, люди. Это не полное распознавание "
            "всех звуков."
        ),
    }


# ─────────────────────── профиль громкости ───────────────────────

def _volume_windows(audio_path: Path, prepared: dict) -> list[dict]:
    windows = []
    window_size = int(AUDIO_RATE * WINDOW_SECONDS)
    offset = max(0.0, float(prepared.get("audio_start", 0.0)))
    duration = float(prepared["duration"])

    with wave.open(str(audio_path), "rb") as audio:
        frames = audio.getnframes()
        total = max(1, math.ceil(frames / window_size))

        for index in range(total):
            raw = audio.readframes(window_size)

            if not raw:
                break

            block = np.frombuffer(
                raw,
                dtype=np.int16,
            ).astype(np.float32) / 32768.0

            if not len(block):
                break

            start = offset + index * WINDOW_SECONDS
            end = min(duration, start + len(block) / AUDIO_RATE)

            if start >= duration:
                break

            windows.append({
                "start": start,
                "end": end,
                **_window_metrics(block),
            })

    return windows


def _window_metrics(block: np.ndarray) -> dict:
    rms = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))

    signs = np.signbit(block)
    zcr = float(np.mean(signs[1:] != signs[:-1]))

    spectrum = np.abs(np.fft.rfft(block * np.hanning(len(block))))
    frequencies = np.fft.rfftfreq(len(block), 1.0 / AUDIO_RATE)
    total = float(spectrum.sum())

    centroid = (
        float((frequencies * spectrum).sum() / total)
        if total > 0 else 0.0
    )

    return {"rms": rms, "zcr": zcr, "centroid": centroid}


def _build_profile(windows: list[dict]) -> dict:
    if not windows:
        return {}

    rms_values = [w["rms"] for w in windows]
    centroid_values = [w["centroid"] for w in windows]

    silence = sum(1 for v in rms_values if v < SILENCE_RMS) / len(windows)
    loud = sum(1 for v in rms_values if v >= LOUD_RMS) / len(windows)

    if silence > 0.6:
        environment = "тихая среда"
    elif loud > 0.3:
        environment = "шумная среда"
    else:
        environment = "смешанный звуковой фон"

    return {
        "mean_rms": round(sum(rms_values) / len(rms_values), 5),
        "peak_rms": round(max(rms_values), 5),
        "silence_ratio": round(silence, 3),
        "loud_ratio": round(loud, 3),
        "mean_centroid_hz": round(
            sum(centroid_values) / len(centroid_values),
            1,
        ),
        "environment": environment,
        "windows": len(windows),
    }


# ─────────────────────── загрузка waveform ───────────────────────

def _load_waveform(audio_path: Path) -> np.ndarray:
    with wave.open(str(audio_path), "rb") as audio:
        frames = audio.readframes(audio.getnframes())

    return (
        np.frombuffer(frames, dtype=np.int16)
        .astype(np.float32) / 32768.0
    )


# ─────────────────────── наблюдения ───────────────────────

def _build_observations(
    sound_summary: list[dict],
    profile: dict,
    bird_clues: list[dict] | None = None,
    road_class: str | None = None,
) -> list[dict]:
    """Одно сводное observation на тип звука + профиль, птицы, дорога."""
    observations: list[dict] = []

    for item in sound_summary[:8]:
        intervals = item.get("intervals") or []

        start = intervals[0][0] if intervals else 0.0
        end = intervals[-1][1] if intervals else 0.0

        observations.append(
            observation(
                source="audio_event",
                start=start,
                end=end,
                text=(
                    f"Идентифицирован звук «{item['label_ru']}»: "
                    f"{item['count']} участк., "
                    f"суммарно {item['total_seconds']} с."
                ),
                extractor="yamnet-onnx",
                data={
                    "kind": "sound_summary",
                    "sound_kind": item["kind"],
                    "label_ru": item["label_ru"],
                    "importance": item["importance"],
                    "count": item["count"],
                    "total_seconds": item["total_seconds"],
                    "max_confidence": item["max_confidence"],
                    "intervals": intervals[:10],
                    "intervals_truncated": len(intervals) > 10,
                    "time_is_approximate": True,
                },
            )
        )

    if profile:
        observations.append(
            observation(
                source="audio_profile",
                start=0.0,
                end=0.0,
                text=(
                    f"Акустическая обстановка: "
                    f"{profile.get('environment')}; "
                    f"тишина {profile.get('silence_ratio', 0) * 100:.0f}%."
                ),
                extractor="numpy-rms-spectrum",
                data={
                    "kind": "audio_profile_summary",
                    "environment": profile.get("environment"),
                    "silence_ratio": profile.get("silence_ratio"),
                    "loud_ratio": profile.get("loud_ratio"),
                },
            )
        )

    for item in (bird_clues or [])[:6]:
        details = item.get("details") or {}

        observations.append(
            observation(
                source="audio_bird",
                start=0.0,
                end=0.0,
                text=item.get("text") or "BirdNET: вид птицы",
                extractor="birdnet-onnx",
                data={
                    "kind": "bird_species",
                    "scientific": details.get("scientific"),
                    "label_ru": details.get("label_ru"),
                    "months": details.get("months"),
                    "narrow_range": details.get("narrow_range"),
                    "confidence": item.get("confidence"),
                    "requires_review": True,
                },
            )
        )

    if road_class:
        observations.append(
            observation(
                source="audio_road",
                start=0.0,
                end=0.0,
                text=(
                    f"Дорожный шум по акустике: {road_class}. "
                    "Это класс дороги, а не её номер."
                ),
                extractor="numpy-rms-spectrum",
                data={
                    "kind": "road_noise",
                    "road_class": road_class,
                    "requires_review": True,
                },
            )
        )

    return observations