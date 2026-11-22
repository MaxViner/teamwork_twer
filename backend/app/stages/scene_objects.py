"""Объекты и типы сцен.

Модель SegFormer размечает кадр по категориям (дорога, здание, вода,
деревья и т.д.). Если модель недоступна, используется быстрая
эвристика по цветам и текстурам. Все кадры складываются в одно
наблюдение-сводку, а уникальные типы объектов собираются в список
по категориям: архитектура, транспорт, природа и уличные объекты.
"""

import json
from pathlib import Path

import numpy as np

from app.services.mediaService.frames import analysis_frame_count, stage_frames
from app.utils.observations import observation
from app.stages.visual_profile import (
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


DEFAULT_SCENE_FRAMES = 500
MAX_SCENE_FRAMES = 2000
MAX_ERROR_EXAMPLES = 20
SMALL_LANDMARK_LABELS = {"signboard", "tower", "pole", "bridge"}


def extract_scene_objects(
    folder: Path,
    run_folder: Path,
    video: Path,
    duration: float,
    stages: dict,
    options: dict,
    progress,
) -> dict:
    count = analysis_frame_count(options)

    frames = stage_frames(
        folder=folder,
        run_folder=run_folder,
        video=video,
        duration=duration,
        stages=stages,
        count=count,
        prefix="objects",
    )

    if not frames:
        raise RuntimeError(
            "Не удалось получить кадры для анализа объектов."
        )

    try:
        result = _extract_with_model(
            folder,
            frames,
            progress,
        )

    except Exception as error:
        progress(
            0,
            "Семантическая модель недоступна, "
            "использую оценочный профиль сцены",
        )

        result = _extract_with_heuristics(
            folder,
            frames,
            progress,
            error,
        )

    result["requested_frames"] = count
    return result


def _extract_with_model(
    folder: Path,
    frames: list[dict],
    progress,
) -> dict:
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

                # Логиты SegFormer имеют низкое разрешение.
                # Считать softmax в полном разрешении кадра
                # слишком дорого по памяти и времени.
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
            "observations": _build_observations(
                saved_frames,
                unique_objects,
                method="segformer",
                model=SCENE_MODEL,
            ),
            "errors": errors[:MAX_ERROR_EXAMPLES],
            "error_count": len(errors),
            "model": SCENE_MODEL,
            "method": "segformer",
            "sampled_frames": len(frames),
            "successful_frames": len(saved_frames),
            "frames_with_objects": sum(bool(frame["objects"]) for frame in saved_frames),
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
    folder: Path,
    frames: list[dict],
    progress,
    model_error: Exception,
) -> dict:
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
        "observations": _build_observations(
            saved_frames,
            unique_objects,
            method="heuristic-fallback",
            model=None,
        ),
        "errors": errors[:MAX_ERROR_EXAMPLES],
        "error_count": len(errors),
        "model": None,
        "method": "heuristic-fallback",
        "model_error": str(model_error)[:1000],
        "sampled_frames": len(frames),
        "successful_frames": len(saved_frames),
        "frames_with_objects": sum(bool(frame["objects"]) for frame in saved_frames),
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


def unique_objects_from_frames(
    frames: list[dict],
) -> list[dict]:
    """
    Собирает уникальные типы объектов по всем кадрам.

    Модель размечает классы, а не отдельные экземпляры, поэтому
    «уникальный объект» здесь — тип объекта. Для каждого типа
    сохраняются число кадров, лучший кадр и все таймкоды.
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


def _build_observations(
    frames: list[dict],
    unique_objects: list[dict],
    method: str,
    model: str | None,
) -> list[dict]:
    """Складывает все кадры объектов в одно наблюдение-сводку."""

    segments = []

    for frame in frames:
        objects = frame.get("objects") or []

        if not objects:
            continue

        readable = ", ".join(
            f"{entry['label_ru']} "
            f"({entry['area_percent']}%)"
            for entry in objects[:6]
        )

        segments.append({
            "start": round(float(frame["timestamp"]), 3),
            "end": round(float(frame["timestamp"]), 3),
            "text": "В кадре: " + readable,
            "artifact": frame.get("artifact"),
        })

    if not segments:
        return []

    categories = {
        item["category"]
        for item in unique_objects
    }

    top = ", ".join(
        f"{item['label_ru']} "
        f"({item['frame_count']} кадр.)"
        for item in unique_objects[:8]
    )

    text = (
        f"В видео найдено {len(unique_objects)} типов "
        f"объектов в {len(categories)} категориях."
    )

    if top:
        text += " " + top + "."

    return [
        observation(
            source="scene_objects",
            start=segments[0]["start"],
            end=segments[-1]["end"],
            text=text,
            extractor=(
                model
                or "pillow-numpy-scene-heuristics"
            ),
            data={
                "kind": "scene_objects_summary",
                "method": method,
                "scene_model": model,
                "segment_count": len(segments),
                "segments": segments,
                "object_count": len(unique_objects),
                "category_count": len(categories),
                "machine_generated": True,
                "requires_review": True,
                "time_is_approximate": True,
            },
        )
    ]


def _objects_from_descriptors(
    descriptors: dict,
    metrics: dict,
) -> list[dict]:
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
