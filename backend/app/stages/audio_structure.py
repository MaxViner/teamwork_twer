"""Аудиопрофиль видео.

Аудио режется на окна по секунде; для каждого считаются громкость,
тишина, частота переходов и спектр. Отмечаются тишина, громкие
участки, низкочастотный гул и широкополосный шум — это подсказки
об акустической обстановке места, а не распознавание звуков.
"""

import math
import wave
from pathlib import Path

import numpy as np

from app.errors import SkipStage
from app.observations import observation
from app.utils.commands import command
from app.utils.paths import relative


AUDIO_RATE = 16000
WINDOW_SECONDS = 1.0
SILENCE_RMS = 0.005
LOUD_RMS = 0.08
RUMBLE_CENTROID = 300.0
BROADBAND_ZCR = 0.15


def extract_audio_structure(
    folder: Path,
    run_folder: Path,
    video: Path,
    prepared: dict,
    progress,
) -> dict:
    if not prepared["has_audio"]:
        raise SkipStage("Аудиодорожки нет.")

    audio_path = run_folder / "audio_structure.wav"

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

    events = []
    windows = []

    window_size = int(AUDIO_RATE * WINDOW_SECONDS)
    offset = max(
        0.0,
        float(prepared.get("audio_start", 0.0)),
    )
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
            end = min(
                duration,
                start + len(block) / AUDIO_RATE,
            )

            if start >= duration:
                break

            progress(
                index / total * 100,
                f"Анализ звука: окно {index + 1}/{total}",
            )

            metrics = _window_metrics(block)
            order = len(windows)

            windows.append({
                "start": start,
                "end": end,
                **metrics,
            })

            kind = _classify(metrics)

            if kind is None:
                continue

            events.append({
                "kind": kind,
                "start": start,
                "end": end,
                "window_index": order,
            })

    observations = _build_observations(
        folder=folder,
        audio_path=audio_path,
        events=events,
    )

    profile = _build_profile(windows)

    progress(100, "Анализ звуковой структуры завершён")

    return {
        "windows": windows[:300],
        "profile": profile,
        "observations": observations,
        "event_count": sum(
            item["data"]["event_count"]
            for item in observations
        ),
        "model": "ffmpeg+numpy-rms-spectrum",
        "window_seconds": WINDOW_SECONDS,
        "note": (
            "Определяются тишина, громкость, низкочастотный гул "
            "и широкополосный шум. Это не распознавание "
            "конкретных звуков или места."
        ),
    }


def _window_metrics(block: np.ndarray) -> dict:
    rms = float(
        np.sqrt(
            np.mean(block.astype(np.float64) ** 2)
        )
    )

    signs = np.signbit(block)
    zcr = float(
        np.mean(signs[1:] != signs[:-1])
    )

    spectrum = np.abs(
        np.fft.rfft(block * np.hanning(len(block)))
    )

    frequencies = np.fft.rfftfreq(
        len(block),
        1.0 / AUDIO_RATE,
    )

    total = float(spectrum.sum())

    centroid = (
        float((frequencies * spectrum).sum() / total)
        if total > 0
        else 0.0
    )

    return {
        "rms": rms,
        "zcr": zcr,
        "centroid": centroid,
    }


def _classify(metrics: dict) -> str | None:
    rms = metrics["rms"]

    if rms < SILENCE_RMS:
        return "silence"

    if rms >= LOUD_RMS:
        return "loud_audio"

    if (
        metrics["centroid"] < RUMBLE_CENTROID
        and rms >= SILENCE_RMS * 2
    ):
        return "low_frequency_rumble"

    if (
        metrics["zcr"] > BROADBAND_ZCR
        and rms >= SILENCE_RMS * 2
    ):
        return "broadband_noise"

    return None


def _build_observations(
    folder: Path,
    audio_path: Path,
    events: list[dict],
) -> list[dict]:
    """Складывает одинаковые звуковые события в одну запись."""

    observations = []

    for group in _group_events(events):
        intervals = group["intervals"]

        observations.append(
            observation(
                source="audio_event",
                start=intervals[0][0],
                end=intervals[-1][1],
                text=_event_summary(group),
                artifact=relative(folder, audio_path),
                extractor="numpy-rms-spectrum",
                data={
                    "kind": group["kind"],
                    "event_count": len(intervals),
                    "window_count": group["window_count"],
                    "total_seconds": round(
                        group["total_seconds"],
                        2,
                    ),
                    "intervals": [
                        [
                            round(start, 2),
                            round(end, 2),
                        ]
                        for start, end in intervals[:50]
                    ],
                    "intervals_truncated": (
                        len(intervals) > 50
                    ),
                    "time_is_approximate": True,
                },
            )
        )

    return observations


def _group_events(events: list[dict]) -> list[dict]:
    """Группирует окна по типу звука и склеивает соседние."""

    groups = {}

    for item in events:
        groups.setdefault(
            item["kind"],
            [],
        ).append(item)

    result = []

    for kind, items in groups.items():
        items.sort(
            key=lambda item: item["start"],
        )

        intervals = _merge_intervals(items)

        result.append({
            "kind": kind,
            "intervals": intervals,
            "window_count": len(items),
            "total_seconds": sum(
                end - start
                for start, end in intervals
            ),
        })

    return sorted(
        result,
        key=lambda group: group["intervals"][0][0],
    )


def _merge_intervals(items: list[dict]) -> list[list[float]]:
    """Склеивает соседние секундные окна в один участок."""

    intervals = []

    for item in items:
        start = float(item["start"])
        end = float(item["end"])

        if (
            intervals
            and start <= intervals[-1][1] + 0.05
        ):
            intervals[-1][1] = max(
                intervals[-1][1],
                end,
            )

        else:
            intervals.append([start, end])

    return intervals


def _event_summary(group: dict) -> str:
    labels = {
        "silence": "Тишина или очень тихий звук",
        "loud_audio": "Заметно громкий звук",
        "low_frequency_rumble": (
            "Низкочастотный гул: возможно, ветер, "
            "двигатель или техника"
        ),
        "broadband_noise": (
            "Широкополосный шум: возможно, улица, "
            "транспорт или техника"
        ),
    }

    label = labels.get(
        group["kind"],
        "Звуковое событие",
    )

    return (
        f"{label}. Участков: "
        f"{len(group['intervals'])}, суммарно "
        f"{_format_duration(group['total_seconds'])}."
    )


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, seconds = divmod(total, 60)

    return f"{minutes}:{seconds:02d}"


def _build_profile(windows: list[dict]) -> dict:
    if not windows:
        return {}

    rms_values = [window["rms"] for window in windows]
    centroid_values = [
        window["centroid"]
        for window in windows
    ]

    silence = sum(
        1 for value in rms_values
        if value < SILENCE_RMS
    ) / len(windows)

    loud = sum(
        1 for value in rms_values
        if value >= LOUD_RMS
    ) / len(windows)

    if silence > 0.6:
        environment = "тихая среда"
    elif loud > 0.3:
        environment = "шумная среда"
    else:
        environment = "смешанный звуковой фон"

    return {
        "mean_rms": round(
            sum(rms_values) / len(rms_values),
            5,
        ),
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
