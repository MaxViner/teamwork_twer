"""BirdNET: виды птиц как слабая гео-улика.

Модель BirdNET (Apache-2.0) — ONNX-файл, которого нет в
репозитории. Ожидается app/models/birdnet.onnx и рядом
birdnet_labels.txt (по одному виду на строку). Если файла нет,
канал аккуратно отключается: остальные улики продолжают работать.

Для каждого вида хранится подсказка: русское название, окно
месяцев и страновые веса. Узкоареальные виды (деркач, иволга,
удод) дают более сильную улику, чем космополиты.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np


SAMPLE_RATE = 48000
WINDOW_SECONDS = 3.0
MIN_CONFIDENCE = 0.25
TOP_K = 5

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parents[2] / "models" / "birdnet.onnx"
)
DEFAULT_LABELS_PATH = DEFAULT_MODEL_PATH.with_name(
    "birdnet_labels.txt"
)

MODEL_PATH = Path(
    os.environ.get("VIDEO_SERVICE_BIRDNET", DEFAULT_MODEL_PATH)
)
LABELS_PATH = Path(
    os.environ.get(
        "VIDEO_SERVICE_BIRDNET_LABELS",
        DEFAULT_LABELS_PATH,
    )
)


# scientific name -> подсказка
SPECIES_HINTS: dict[str, dict] = {
    "Crex crex": {
        "label_ru": "деркач (коростель)",
        "months": [5, 8],
        "countries": {"RU": 0.5, "BY": 0.2, "UA": 0.15},
        "narrow": True,
        "note": "луга и поля, летний крик самца",
    },
    "Oriolus oriolus": {
        "label_ru": "иволга",
        "months": [5, 7],
        "countries": {"RU": 0.35, "BY": 0.2, "UA": 0.15},
        "narrow": True,
        "note": "широколиственные леса и поймы",
    },
    "Upupa epops": {
        "label_ru": "удод",
        "months": [5, 8],
        "countries": {"RU": 0.25, "UA": 0.2, "KZ": 0.15},
        "narrow": True,
        "note": "юг умеренной зоны, открытые местообитания",
    },
    "Luscinia luscinia": {
        "label_ru": "соловей",
        "months": [5, 6],
        "countries": {"RU": 0.3, "BY": 0.15, "UA": 0.1},
        "narrow": False,
        "note": "пойменные заросли, ночное пение",
    },
    "Cuculus canorus": {
        "label_ru": "кукушка",
        "months": [5, 7],
        "countries": {"RU": 0.2},
        "narrow": False,
        "note": "широкий ареал, только сезон",
    },
    "Alauda arvensis": {
        "label_ru": "полевой жаворонок",
        "months": [4, 7],
        "countries": {"RU": 0.2},
        "narrow": False,
        "note": "открытые поля и луга",
    },
    "Motacilla alba": {
        "label_ru": "белая трясогузка",
        "months": [4, 9],
        "countries": {"RU": 0.15},
        "narrow": False,
        "note": "широкий ареал, слабая улика",
    },
    "Remiz pendulinus": {
        "label_ru": "ремез",
        "months": [5, 8],
        "countries": {"RU": 0.25, "UA": 0.1},
        "narrow": True,
        "note": "поймы юга лесной зоны",
    },
    "Acrocephalus paludicola": {
        "label_ru": "водяной сверчок",
        "months": [5, 7],
        "countries": {"BY": 0.4, "UA": 0.2, "PL": 0.2},
        "narrow": True,
        "note": "редкий вид болот Полесья",
    },
}


def model_available() -> bool:
    return MODEL_PATH.is_file() and LABELS_PATH.is_file()


def model_note() -> str:
    if not MODEL_PATH.is_file():
        return (
            "BirdNET недоступен: нет файла "
            f"{MODEL_PATH.name}. Положите ONNX-модель и "
            "birdnet_labels.txt в app/models/."
        )

    if not LABELS_PATH.is_file():
        return (
            "BirdNET недоступен: нет файла "
            f"{LABELS_PATH.name} рядом с моделью."
        )

    return "BirdNET готов."


def status() -> dict:
    return {
        "available": model_available(),
        "model": str(MODEL_PATH),
        "labels": str(LABELS_PATH),
        "note": model_note(),
    }


@lru_cache(maxsize=1)
def _session():
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = 1

    return ort.InferenceSession(
        str(MODEL_PATH),
        sess_options=options,
        providers=["CPUExecutionProvider"],
    )


@lru_cache(maxsize=1)
def _labels() -> list[str]:
    if not LABELS_PATH.is_file():
        return []

    return [
        line.strip()
        for line in LABELS_PATH.read_text(
            encoding="utf-8",
        ).splitlines()
        if line.strip()
    ]


def _resample(
    waveform: np.ndarray,
    source_rate: int,
    target_rate: int = SAMPLE_RATE,
) -> np.ndarray:
    if source_rate == target_rate:
        return waveform.astype(np.float32)

    import librosa

    return librosa.resample(
        np.asarray(waveform, dtype=np.float32),
        orig_sr=source_rate,
        target_sr=target_rate,
    ).astype(np.float32)


def _probabilities(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)

    if values.size == 0:
        return values

    if values.min() >= 0.0 and values.max() <= 1.0:
        return values

    shifted = values - values.max()
    exp = np.exp(shifted)

    return exp / max(exp.sum(), 1e-9)


def _parse_label(value: str) -> tuple[str, str | None]:
    """BirdNET-подпись: «Sci_Name_Common Name» или просто вид."""

    parts = value.split("_", 2)

    if len(parts) >= 3:
        scientific = f"{parts[0]} {parts[1]}"
        common = parts[2].strip()

        return scientific, common or None

    return value.replace("_", " ").strip(), None


def analyze_waveform(
    waveform: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    *,
    top_k: int = TOP_K,
    min_confidence: float = MIN_CONFIDENCE,
) -> dict:
    """Найти виды птиц в waveform 48 кГц."""

    if not model_available():
        return {
            "detections": [],
            "windows": 0,
            "note": model_note(),
        }

    audio = _resample(waveform, sample_rate)
    window_size = int(SAMPLE_RATE * WINDOW_SECONDS)

    if audio.size < window_size:
        audio = np.pad(audio, (0, window_size - audio.size))

    session = _session()
    input_meta = session.get_inputs()[0]
    labels = _labels()
    collected: dict[str, dict] = {}

    for start in range(0, audio.size - window_size + 1, window_size):
        chunk = audio[start:start + window_size]

        if not np.any(chunk):
            continue

        try:
            outputs = session.run(
                None,
                {input_meta.name: chunk.reshape(1, -1)},
            )

        except Exception:
            continue

        probabilities = _probabilities(outputs[0])
        order = np.argsort(probabilities)[::-1][:top_k]

        for index in order:
            score = float(probabilities[index])

            if score < min_confidence:
                continue

            if index >= len(labels):
                continue

            scientific, common = _parse_label(labels[index])
            entry = collected.setdefault(scientific, {
                "scientific": scientific,
                "common": common,
                "confidence": 0.0,
                "windows": 0,
            })

            entry["confidence"] = max(
                entry["confidence"],
                score,
            )
            entry["windows"] += 1

    detections = sorted(
        collected.values(),
        key=lambda item: -item["confidence"],
    )

    for item in detections:
        hint = SPECIES_HINTS.get(item["scientific"])
        item["hint"] = hint
        item["label_ru"] = (
            hint["label_ru"] if hint else item.get("common")
        )

    return {
        "detections": detections,
        "windows": max(1, audio.size // window_size),
        "note": None,
    }


def analyze_audio(path: str | Path) -> dict:
    """Прочитать аудиофайл и прогнать BirdNET."""

    if not model_available():
        return {
            "detections": [],
            "windows": 0,
            "note": model_note(),
        }

    try:
        import soundfile as sf

        waveform, sample_rate = sf.read(
            str(path),
            dtype="float32",
            always_2d=False,
        )

    except Exception as error:
        return {
            "detections": [],
            "windows": 0,
            "note": f"BirdNET: не удалось прочитать аудио ({error})",
        }

    if getattr(waveform, "ndim", 1) > 1:
        waveform = waveform.mean(axis=1)

    return analyze_waveform(waveform, sample_rate)


def species_clues(
    detections: list[dict],
    duration: float = 0.0,
    *,
    limit: int = 5,
) -> list[dict]:
    """Превратить виды птиц в улики с окном месяцев."""

    clues = []

    for item in detections[:limit]:
        hint = item.get("hint") or SPECIES_HINTS.get(
            item.get("scientific", "")
        )
        label_ru = (
            (hint or {}).get("label_ru")
            or item.get("common")
            or item.get("scientific")
        )
        confidence = float(item.get("confidence") or 0.0)

        if hint and hint.get("narrow"):
            confidence = min(0.8, confidence + 0.1)

        details = {
            "scientific": item.get("scientific"),
            "label_ru": label_ru,
            "months": (hint or {}).get("months"),
            "narrow_range": bool((hint or {}).get("narrow")),
            "note": (hint or {}).get("note"),
            "windows": item.get("windows"),
            "origin": "birdnet",
        }

        month_text = ""

        if details["months"]:
            month_text = (
                f", окно месяцев "
                f"{details['months'][0]}–{details['months'][1]}"
            )

        clues.append({
            "kind": "bird_species",
            "label": "Вид птицы",
            "text": (
                f"BirdNET: {label_ru} "
                f"({item.get('scientific')}){month_text}"
            ),
            "confidence": round(confidence, 3),
            "country_hints": dict(
                (hint or {}).get("countries") or {}
            ),
            "start": 0.0,
            "end": float(duration),
            "artifact": None,
            "frame_artifact": None,
            "details": details,
        })

    return clues


__all__ = [
    "MIN_CONFIDENCE",
    "MODEL_PATH",
    "SAMPLE_RATE",
    "SPECIES_HINTS",
    "analyze_audio",
    "analyze_waveform",
    "model_available",
    "model_note",
    "species_clues",
    "status",
]
