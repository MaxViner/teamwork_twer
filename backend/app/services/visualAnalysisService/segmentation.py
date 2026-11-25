"""Семантическая разметка кадров (SegFormer и эвристический fallback).

Основной путь — модель nvidia/segformer-b0-finetuned-ade-512-512 через
transformers. Она тяжёлая, поэтому импортируется лениво внутри
функции: если torch/transformers не установлены или модель не
скачалась, стадия не падает, а переходит на быстрые эвристики по
цвету и текстуре.

Модуль самодостаточен: не импортирует старые
visyalInspectorService.scene_objects / visual_profile, чтобы те
можно было удалить без регрессии visual_analysis.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.services.visualAnalysisService.metrics import (
    analyze_frame,
    describe_metrics,
)


SCENE_MODEL = (
    "nvidia/segformer-b0-finetuned-ade-512-512"
)


LABEL_RU = {
    "road": "дорога",
    "building": "здание",
    "house": "дом",
    "tree": "деревья",
    "grass": "трава",
    "water": "вода",
    "river": "река",
    "lake": "озеро",
    "sea": "море",
    "sky": "небо",
    "earth": "земля",
    "mountain": "гора",
    "bridge": "мост",
    "fence": "забор",
    "path": "тропинка",
    "car": "автомобиль",
    "bus": "автобус",
    "truck": "грузовик",
    "signboard": "вывеска",
    "streetlight": "фонарь",
    "pole": "столб",
    "plant": "растения",
    "sand": "песок",
    "rock": "камни",
    "field": "поле",
    "hill": "холм",
    "boat": "лодка",
    "pier": "причал",
    "swimming pool": "бассейн",
    "fountain": "фонтан",
    "tower": "башня",
    "column": "колонна",
    "skyscraper": "небоскрёб",
    "wall": "стена",
    "castle": "замок",
    "church": "церковь",
    "temple": "храм",
    "monument": "памятник",
}


CATEGORY_ORDER = (
    "architecture",
    "transport",
    "nature",
    "street",
    "other",
)


CATEGORY_LABELS_RU = {
    "architecture": "Архитектура и ориентиры",
    "transport": "Транспорт и дороги",
    "nature": "Природа",
    "street": "Уличные объекты",
    "other": "Другие объекты",
}


LABEL_CATEGORY = {
    "building": "architecture",
    "house": "architecture",
    "tower": "architecture",
    "skyscraper": "architecture",
    "wall": "architecture",
    "castle": "architecture",
    "church": "architecture",
    "temple": "architecture",
    "monument": "architecture",
    "column": "architecture",
    "fountain": "architecture",
    "bridge": "architecture",
    "pier": "architecture",
    "car": "transport",
    "bus": "transport",
    "truck": "transport",
    "boat": "transport",
    "road": "transport",
    "path": "transport",
    "tree": "nature",
    "grass": "nature",
    "plant": "nature",
    "field": "nature",
    "mountain": "nature",
    "hill": "nature",
    "rock": "nature",
    "sand": "nature",
    "water": "nature",
    "river": "nature",
    "lake": "nature",
    "sea": "nature",
    "earth": "nature",
    "sky": "nature",
    "snow": "nature",
    "signboard": "street",
    "streetlight": "street",
    "pole": "street",
    "fence": "street",
    "водная поверхность": "nature",
    "растительность": "nature",
    "открытое небо": "nature",
    "дорога или асфальт, возможно": "transport",
    "скалы или плотная застройка, возможно": "architecture",
    "яркая светлая поверхность": "nature",
    "крупная ровная поверхность (вода, асфальт или снег)": "nature",
}


INTERESTING_LABELS = {
    "road",
    "building",
    "house",
    "tree",
    "grass",
    "water",
    "river",
    "lake",
    "sea",
    "earth",
    "mountain",
    "bridge",
    "fence",
    "path",
    "car",
    "bus",
    "truck",
    "signboard",
    "streetlight",
    "pole",
    "plant",
    "sand",
    "rock",
    "field",
    "hill",
    "boat",
    "pier",
    "swimming pool",
    "fountain",
    "tower",
    "column",
    "skyscraper",
    "wall",
    "castle",
    "church",
    "temple",
    "monument",
}


HEURISTIC_LABELS = {
    "водная поверхность": "вода",
    "растительность": "растительность",
    "открытое небо": "небо",
    "дорога или асфальт, возможно": "дорога",
    "скалы или плотная застройка, возможно": "скалы или застройка",
    "яркая светлая поверхность": "снег или светлая поверхность",
    "крупная ровная поверхность (вода, асфальт или снег)": "ровная поверхность",
}


MAX_ERROR_EXAMPLES = 20
SMALL_LANDMARK_LABELS = {"signboard", "tower", "pole", "bridge"}


def extract_segments(
    frames: list[dict],
    progress,
) -> dict:
    """Разметить кадры и вернуть объекты по каждому кадру.

    Сначала пробует SegFormer, затем эвристики. Возвращает словарь
    с полями frames (timestamp, artifact, objects), method, model,
    errors, error_count и note.
    """

    try:
        result = _extract_with_model(frames, progress)
        result.setdefault("method", "segformer")
        return result

    except Exception as error:
        progress(
            0,
            "Семантическая модель недоступна, "
            "использую оценочный профиль сцены",
        )

        return _extract_with_heuristics(
            frames,
            progress,
            error,
        )


def run_segformer(image_path: Path) -> list[dict]:
    """Разметить одно изображение моделью SegFormer.

    Публичная обёртка для тестового эндпоинта и отладки. При
    недоступной модели возвращает эвристические объекты.
    """

    frames = [
        {
            "path": str(image_path),
            "timestamp": 0.0,
            "artifact": "",
        }
    ]

    result = extract_segments(
        frames,
        lambda percent, message: None,
    )

    saved = result.get("frames") or []

    if not saved:
        return []

    return list(saved[0].get("objects") or [])


def unique_objects_from_frames(
    frames: list[dict],
) -> list[dict]:
    """Собрать уникальные типы объектов по всем кадрам.

    Модель размечает классы, а не отдельные экземпляры, поэтому
    «уникальный объект» здесь — тип объекта. Для каждого типа
    сохраняются число кадров, лучший кадр и таймкоды.
    """

    collected = {}

    for frame in frames:
        if not isinstance(frame, dict):
            continue

        timestamp = frame.get("timestamp")

        if timestamp is None:
            continue

        timestamp = round(float(timestamp), 6)
        artifact = frame.get("artifact")

        for item in frame.get("objects", []):
            if not isinstance(item, dict):
                continue

            label = item.get("label")

            if not label:
                continue

            entry = collected.setdefault(label, {
                "label": label,
                "label_ru": (
                    item.get("label_ru")
                    or LABEL_RU.get(label, label)
                ),
                "category": LABEL_CATEGORY.get(
                    label,
                    "other",
                ),
                "frame_count": 0,
                "max_area_percent": 0.0,
                "mean_confidence": 0.0,
                "best_frame": None,
                "best_timestamp": None,
                "timestamps": [],
                "_confidence_sum": 0.0,
            })

            area = float(item.get("area_percent") or 0)
            confidence = float(item.get("confidence") or 0)

            entry["frame_count"] += 1
            entry["_confidence_sum"] += confidence
            entry["timestamps"].append(timestamp)

            if area > entry["max_area_percent"]:
                entry["max_area_percent"] = area
                entry["best_frame"] = artifact
                entry["best_timestamp"] = timestamp

    result = []

    for entry in collected.values():
        count = entry["frame_count"]

        entry["timestamps"] = sorted(set(
            entry["timestamps"]
        ))
        entry["frame_count"] = len(entry["timestamps"])
        entry["max_area_percent"] = round(
            entry["max_area_percent"],
            2,
        )
        entry["mean_confidence"] = round(
            entry["_confidence_sum"] / max(count, 1),
            3,
        )
        entry.pop("_confidence_sum", None)
        result.append(entry)

    result.sort(key=lambda item: (
        CATEGORY_ORDER.index(item["category"])
        if item["category"] in CATEGORY_ORDER
        else len(CATEGORY_ORDER),
        -item["frame_count"],
        -item["max_area_percent"],
        item["label_ru"],
    ))

    return result


def _extract_with_model(
    frames: list[dict],
    progress,
) -> dict:
    """Разметить кадры SegFormer, если модель доступна."""

    import torch
    from PIL import Image
    from transformers import (
        AutoImageProcessor,
        SegformerForSemanticSegmentation,
    )

    progress(0, "Загружаю модель объектов и признаков места")

    processor = AutoImageProcessor.from_pretrained(
        SCENE_MODEL,
    )

    model = SegformerForSemanticSegmentation.from_pretrained(
        SCENE_MODEL,
    ).eval()

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    model = model.to(device)

    saved_frames = []
    errors = []

    try:
        for index, frame in enumerate(frames):
            progress(
                index / len(frames) * 100,
                f"Анализ объектов: кадр {index + 1}/{len(frames)}",
            )

            try:
                with Image.open(frame["path"]) as source:
                    image = source.convert("RGB")

                inputs = processor(
                    images=image,
                    return_tensors="pt",
                ).to(device)

                with torch.inference_mode():
                    outputs = model(**inputs)

                probabilities = torch.nn.functional.softmax(
                    outputs.logits,
                    dim=1,
                )[0]

                segmentation = probabilities.argmax(
                    dim=0,
                ).cpu().numpy()

                found = _labels_from_segmentation(
                    segmentation,
                    probabilities,
                    model.config.id2label,
                )

                saved_frames.append({
                    "timestamp": frame["timestamp"],
                    "artifact": frame["artifact"],
                    "objects": found,
                })

            except Exception as error:
                errors.append({
                    "timestamp": frame["timestamp"],
                    "error": str(error)[:1500],
                })

        if not saved_frames:
            raise RuntimeError(
                "Ни один кадр не проанализирован. "
                + json.dumps(
                    errors[:2],
                    ensure_ascii=False,
                )
            )

        progress(100, "Анализ объектов завершён")

        unique_objects = unique_objects_from_frames(
            saved_frames
        )

        return {
            "frames": saved_frames,
            "errors": errors[:MAX_ERROR_EXAMPLES],
            "error_count": len(errors),
            "model": SCENE_MODEL,
            "method": "segformer",
            "sampled_frames": len(frames),
            "successful_frames": len(saved_frames),
            "frames_with_objects": sum(
                bool(frame["objects"])
                for frame in saved_frames
            ),
            "unique_objects": unique_objects,
            "object_count": len(unique_objects),
            "category_count": len({
                item["category"]
                for item in unique_objects
            }),
            "note": (
                "Определены видимые типы объектов и областей. "
                "Это не координаты и не подтверждённый адрес."
            ),
        }

    finally:
        del model, processor

        import gc

        gc.collect()

        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        except ImportError:
            pass


def _labels_from_segmentation(
    segmentation,
    probabilities,
    id2label: dict,
) -> list[dict]:
    """Превратить карту классов SegFormer в список объектов."""

    found = []
    height, width = segmentation.shape[:2]

    for label_id in np.unique(segmentation):
        label = id2label[int(label_id)]

        if label not in INTERESTING_LABELS:
            continue

        mask = segmentation == label_id
        area_percent = float(mask.mean() * 100)

        # Мелкие ориентиры могут занимать меньше 1% кадра. Для них
        # требуем более высокий средний балл, а не выдаём метку за факт.
        min_area = 0.15 if label in SMALL_LANDMARK_LABELS else 1.0
        if area_percent < min_area:
            continue

        ys, xs = np.where(mask)

        if not len(xs):
            continue

        bbox = [
            float(xs.min() / width),
            float(ys.min() / height),
            float((xs.max() + 1) / width),
            float((ys.max() + 1) / height),
        ]

        confidence = float(
            probabilities[
                int(label_id),
                ys,
                xs,
            ].mean()
        )

        if area_percent < 1.0 and (len(xs) < 4 or confidence < 0.60):
            continue

        found.append({
            "label": label,
            "label_ru": LABEL_RU.get(label, label),
            "area_percent": round(area_percent, 2),
            "bbox": [round(value, 4) for value in bbox],
            "confidence": round(confidence, 3),
        })

    found.sort(key=lambda entry: -entry["area_percent"])

    return found


def _extract_with_heuristics(
    frames: list[dict],
    progress,
    model_error: Exception,
) -> dict:
    """Оценить типы поверхностей по метрикам, если модели нет."""

    saved_frames = []
    errors = []

    for index, frame in enumerate(frames):
        progress(
            index / len(frames) * 100,
            "Оценка сцены: кадр "
            f"{index + 1}/{len(frames)}",
        )

        try:
            metrics = analyze_frame(frame["path"])
            descriptors = describe_metrics(metrics)

        except Exception as error:
            errors.append({
                "timestamp": frame["timestamp"],
                "error": str(error)[:1000],
            })
            continue

        objects = _objects_from_descriptors(
            descriptors,
            metrics,
        )

        saved_frames.append({
            "timestamp": frame["timestamp"],
            "artifact": frame["artifact"],
            "objects": objects,
        })

    if not saved_frames:
        raise RuntimeError(
            "Не удалось оценить ни один кадр. "
            + str(model_error)[:500]
        )

    progress(100, "Оценка сцены завершена")

    unique_objects = unique_objects_from_frames(
        saved_frames
    )

    return {
        "frames": saved_frames,
        "errors": errors[:MAX_ERROR_EXAMPLES],
        "error_count": len(errors),
        "model": None,
        "method": "heuristic-fallback",
        "model_error": str(model_error)[:1000],
        "sampled_frames": len(frames),
        "successful_frames": len(saved_frames),
        "frames_with_objects": sum(
            bool(frame["objects"])
            for frame in saved_frames
        ),
        "unique_objects": unique_objects,
        "object_count": len(unique_objects),
        "category_count": len({
            item["category"]
            for item in unique_objects
        }),
        "note": (
            "Семантическая модель недоступна или не обработала выборку. "
            "Типы поверхностей оценены по цвету и текстуре; "
            "это не координаты и не подтверждённый адрес."
        ),
    }


def _objects_from_descriptors(
    descriptors: dict,
    metrics: dict,
) -> list[dict]:
    """Собрать объекты-поверхности из словесного описания кадра."""

    landscape = descriptors.get("landscape", [])
    objects = []

    shares = {
        "водная поверхность": metrics.get("water", 0),
        "растительность": metrics.get("vegetation", 0),
        "открытое небо": metrics.get("sky", 0),
        "дорога или асфальт, возможно": metrics.get(
            "asphalt",
            0,
        ),
        "скалы или плотная застройка, возможно": max(
            metrics.get("gray", 0),
            metrics.get("edge_density", 0),
        ),
        "яркая светлая поверхность": metrics.get("snow", 0),
        "крупная ровная поверхность (вода, асфальт или снег)": metrics.get(
            "gray_lower",
            0,
        ),
    }

    for label in landscape:
        label_ru = HEURISTIC_LABELS.get(label)

        if not label_ru:
            continue

        area = float(shares.get(label, 0.0))

        objects.append({
            "label": label,
            "label_ru": label_ru,
            "area_percent": round(max(area, 1.0), 1),
            "confidence": 0.35,
            "method": "heuristic",
        })

    if not objects:
        objects.append({
            "label": "surface",
            "label_ru": "поверхность без выраженных признаков",
            "area_percent": 100.0,
            "confidence": 0.2,
            "method": "heuristic",
        })

    objects.sort(key=lambda entry: -entry["area_percent"])

    return objects[:6]
