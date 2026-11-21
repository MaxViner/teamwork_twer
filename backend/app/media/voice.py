"""Разделение речи по спикерам.

Без внешних моделей оценивает высоту голоса (F0) на каждой реплике
и делит реплики на 1–2 спикера. Это приблизительная эвристика:
она помогает читать диалог, но не заменяет полноценную
диаризацию. Если голоса похожи, все реплики остаются за одним
спикером.
"""

import wave

import numpy as np


MIN_PITCH_HZ = 70.0
MAX_PITCH_HZ = 400.0
MIN_RMS = 0.004
SPEAKER_GAP_RATIO = 0.12


def assign_speakers(
    audio_path,
    segments: list[dict],
) -> tuple[list[dict], list[dict], str]:
    """
    Добавляет поле speaker к репликам.

    Возвращает (реплики, спикеры, метод). Метод описывает,
    на чём основано разделение, чтобы отчёт не выдавал
    эвристику за точную диаризацию.
    """
    if not segments:
        return segments, [], "нет реплик"

    samples, rate = _load_mono(audio_path)

    if samples is None or rate <= 0:
        return (
            _single_speaker(segments),
            _speaker_list(segments),
            "высота голоса недоступна",
        )

    pitches = [
        _segment_pitch(
            samples,
            rate,
            float(item.get("start") or 0),
            float(item.get("end") or 0),
        )
        for item in segments
    ]

    valid = [
        (index, value)
        for index, value in enumerate(pitches)
        if value
    ]

    if len(valid) < 4:
        return (
            _single_speaker(segments),
            _speaker_list(segments),
            "слишком мало голосовых реплик",
        )

    logs = np.array([
        np.log(value)
        for _, value in valid
    ])

    low = float(np.percentile(logs, 25))
    high = float(np.percentile(logs, 75))

    if high - low < SPEAKER_GAP_RATIO:
        return (
            _single_speaker(segments),
            _speaker_list(segments),
            "голоса похожи по высоте",
        )

    for _ in range(12):
        low_group = np.abs(logs - low) <= np.abs(logs - high)

        if not low_group.any() or low_group.all():
            break

        new_low = float(logs[low_group].mean())
        new_high = float(logs[~low_group].mean())

        if abs(new_low - low) < 1e-6 and abs(new_high - high) < 1e-6:
            low, high = new_low, new_high
            break

        low, high = new_low, new_high

    if high - low < SPEAKER_GAP_RATIO:
        return (
            _single_speaker(segments),
            _speaker_list(segments),
            "голоса похожи по высоте",
        )

    labels = {}

    for index, pitch in valid:
        group = "low" if (
            abs(np.log(pitch) - low)
            <= abs(np.log(pitch) - high)
        ) else "high"

        if group not in labels:
            labels[group] = f"Спикер {len(labels) + 1}"

        segments[index]["speaker"] = labels[group]
        segments[index]["speaker_pitch_hz"] = round(
            float(pitch),
            1,
        )

    _fill_missing(segments)
    _smooth(segments)

    return (
        segments,
        _speaker_list(segments),
        "оценка по высоте голоса",
    )


def _load_mono(path):
    """Читает WAV и сводит его в моно float32."""
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())

    except (OSError, wave.Error):
        return None, 0

    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(
            np.float32
        ) / 32768.0

    elif width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(
            np.float32
        ) / 2147483648.0

    elif width == 1:
        data = (
            np.frombuffer(raw, dtype=np.uint8).astype(
                np.float32
            ) - 128.0
        ) / 128.0

    else:
        return None, 0

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    return data, rate


def _segment_pitch(samples, rate, start, end):
    """Медианная высота голоса на реплике или None."""
    first = int(max(0.0, start) * rate)
    last = int(max(start + 0.05, end) * rate)

    if first >= len(samples):
        return None

    chunk = samples[first:min(last, len(samples))]

    if len(chunk) < int(rate * 0.05):
        return None

    values = []
    window = int(rate * 0.06)

    for offset in range(
        0,
        max(1, len(chunk) - window),
        max(window, 1),
    ):
        piece = chunk[offset:offset + window]

        if len(piece) < window:
            break

        value = _pitch(piece, rate)

        if value:
            values.append(value)

        if len(values) >= 6:
            break

    return float(np.median(values)) if values else None


def _pitch(piece, rate):
    """Одна оценка F0 через автокорреляцию."""
    piece = piece - float(np.mean(piece))
    rms = float(np.sqrt(np.mean(piece ** 2)))

    if rms < MIN_RMS:
        return None

    correlation = np.correlate(
        piece,
        piece,
        mode="full",
    )[len(piece) - 1:]

    min_lag = max(2, int(rate / MAX_PITCH_HZ))
    max_lag = min(
        int(rate / MIN_PITCH_HZ),
        len(correlation) - 1,
    )

    if max_lag <= min_lag:
        return None

    window = correlation[min_lag:max_lag]
    lag = min_lag + int(np.argmax(window))

    if correlation[lag] < 0.2 * max(correlation[0], 1e-9):
        return None

    return rate / lag


def _fill_missing(segments):
    """Репликам без высоты голоса даёт ближайшего спикера."""
    known = [
        index
        for index, item in enumerate(segments)
        if item.get("speaker")
    ]

    if not known:
        _single_speaker(segments)
        return

    for index, item in enumerate(segments):
        if item.get("speaker"):
            continue

        nearest = min(
            known,
            key=lambda position: abs(position - index),
        )
        item["speaker"] = segments[nearest]["speaker"]


def _smooth(segments):
    """Убирает одиночные переключения спикера между соседями."""
    for index in range(1, len(segments) - 1):
        previous = segments[index - 1].get("speaker")
        current = segments[index].get("speaker")
        following = segments[index + 1].get("speaker")

        if (
            previous
            and previous == following
            and current != previous
        ):
            segments[index]["speaker"] = previous


def _single_speaker(segments):
    for item in segments:
        item.setdefault("speaker", "Спикер 1")

    return segments


def _speaker_list(segments):
    collected = {}

    for item in segments:
        label = item.get("speaker") or "Спикер 1"
        entry = collected.setdefault(label, {
            "label": label,
            "segment_count": 0,
            "first_start": item.get("start"),
            "last_end": item.get("end"),
            "pitches": [],
        })

        entry["segment_count"] += 1
        entry["last_end"] = item.get("end")

        if item.get("speaker_pitch_hz"):
            entry["pitches"].append(
                item["speaker_pitch_hz"]
            )

    result = []

    for entry in collected.values():
        pitches = entry.pop("pitches")
        entry["mean_pitch_hz"] = (
            round(float(np.mean(pitches)), 1)
            if pitches
            else None
        )
        result.append(entry)

    result.sort(key=lambda item: item["first_start"] or 0)

    return result
