"""Повторы в видео.

Ищет одинаковые надписи, которые встречаются несколько раз.
Повторяющиеся вывески, номера и указатели помогают подтвердить
место и отсеять случайные совпадения OCR.

Наблюдения НЕ создаются: повторы — внутренние улики для
агрегатора location_evidence (text_groups) и не попадают в UI.
Визуальное сравнение кадров (ORB+RANSAC) убрано: оно не
используется потребителями и не влияет на координаты, только
тратит время и засоряет result.

Файлов этап не создаёт. Полные пути к кадрам получаются через
storage.resolve(artifact) по folder-relative ссылкам из stages.
"""

import unicodedata

from app.storage import StorageService
from app.utils.errors import SkipStage


def extract_structure(
    storage: StorageService,
    stages: dict,
    progress,
) -> dict:
    ocr_items = completed_observations(
        stages,
        "ocr",
    )

    if not ocr_items:
        raise SkipStage(
            "Нет распознанных кадров для поиска повторов. "
            "Сначала выполните этап «Текст на кадрах»."
        )

    progress(0, "Ищу повторяющиеся надписи")

    text_groups = _text_repetitions(ocr_items)

    frames = _unique_frames(
        storage,
        stages,
        ocr_items,
    )

    progress(100, "Поиск повторов завершён")

    note = (
        "Повтор надписи не доказывает, что это один и тот же "
        "объект, улица или место. Это внутренняя улика для "
        "локационного досье."
    )

    if not text_groups:
        note = "Повторяющихся надписей не найдено."

    return {
        "text_groups": text_groups,
        "compared_frames": len(frames),
        "observations": [],
        "errors": [],
        "note": note,
    }


def completed_observations(
    stages: dict,
    stage_name: str,
) -> list[dict]:
    stage = stages.get(stage_name, {})

    if stage.get("status") != "completed":
        return []

    return [
        item
        for item in stage.get("observations", [])
        if item.get("review") != "rejected"
    ]


def _text_repetitions(items: list[dict]) -> list[dict]:
    """Собирает группы одинаковых надписей. Без observations."""
    groups = {}

    for item in items:
        text = str(item.get("text", "")).strip()

        if len(text) < 4:
            continue

        key = normalized_text(text)
        groups.setdefault(key, []).append(item)

    text_groups = []

    for key, group in groups.items():
        if len(group) < 2:
            continue

        group = sorted(
            group,
            key=lambda entry: float(entry.get("start", 0.0)),
        )

        first = group[0]
        text = str(first.get("text", "")).strip()

        text_groups.append({
            "text": text[:300],
            "count": len(group),
            "observation_ids": [
                item.get("id")
                for item in group
            ],
            "times": [
                float(item.get("start", 0.0))
                for item in group
            ],
        })

    text_groups.sort(key=lambda item: -item["count"])

    return text_groups


def _unique_frames(
    storage: StorageService,
    stages: dict,
    items: list[dict],
) -> list[dict]:
    """Считает уникальные существующие кадры. Используется только
    для compared_frames в result — сравнение не выполняется."""
    frames = []
    seen = set()

    result = stages.get("ocr", {}).get("result", {})

    for entry in result.get("frames", []):
        artifact = entry.get("artifact")

        if not artifact or artifact in seen:
            continue

        path = storage.resolve(artifact)

        if not path.is_file():
            continue

        seen.add(artifact)
        frames.append({
            "timestamp": float(entry.get("timestamp", 0.0)),
            "artifact": artifact,
            "path": path,
        })

    for item in items:
        artifact = item.get("frame_artifact")

        if not artifact or artifact in seen:
            continue

        path = storage.resolve(artifact)

        if not path.is_file():
            continue

        seen.add(artifact)
        frames.append({
            "timestamp": float(item.get("start", 0.0)),
            "artifact": artifact,
            "path": path,
        })

    return frames


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value))
    return " ".join(text.casefold().split())