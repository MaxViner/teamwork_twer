"""Объекты и типы сцен.

Модель SegFormer размечает кадр по категориям (дорога, здание, вода,
деревья и т.д.). Если модель недоступна, используется быстрая
эвристика по цветам и текстурам. Итог — преобладающие объекты
и подсказки о типе местности.
"""

import json
from pathlib import Path

import numpy as np

from app.media.frames import stage_frames
from app.observations import observation
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


def extract_scene_objects(
    folder: Path,
    run_folder: Path,
    video: Path,
    duration: float,
    stages: dict,
    options: dict,
    progress,
) -> dict:
    count = max(1, min(12, int(options.get("max_frames", 12))))

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
        return _extract_with_model(
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

        return _extract_with_heuristics(
            folder,
            frames,
            progress,
            error,
        )


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

    observations = []
    saved_frames = []
    errors = []

    try:
        for index, frame in enumerate(frames):
            progress(
                (index + 1) / len(frames) * 100,
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

                if not found:
                    continue

                readable = ", ".join(
                    f"{entry['label_ru']} "
                    f"({entry['area_percent']}%)"
                    for entry in found[:6]
                )

                observations.append(
                    observation(
                        source="scene_objects",
                        start=frame["timestamp"],
                        end=frame["timestamp"],
                        text=(
                            "В кадре обнаружены: "
                            + readable
                        ),
                        artifact=frame["artifact"],
                        frame_artifact=frame["artifact"],
                        extractor=SCENE_MODEL,
                        data={
                            "kind": "scene_objects",
                            "objects": found,
                            "scene_model": SCENE_MODEL,
                            "method": "segformer",
                            "machine_generated": True,
                            "requires_review": True,
                            "time_is_approximate": True,
                        },
                    )
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

        return {
            "frames": saved_frames,
            "observations": observations,
            "errors": errors,
            "model": SCENE_MODEL,
            "method": "segformer",
            "sampled_frames": len(frames),
            "successful_frames": len(saved_frames),
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

        if area_percent < 1.0:
            continue

        ys, xs = np.where(mask)

        if not len(xs):
            continue

        bbox = [
            float(xs.min() / width),
            float(ys.min() / height),
            float(xs.max() / width),
            float(ys.max() / height),
        ]

        confidence = float(
            probabilities[
                int(label_id),
                ys,
                xs,
            ].mean()
        )

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
    observations = []
    saved_frames = []
    errors = []

    for index, frame in enumerate(frames):
        progress(
            (index + 1) / len(frames) * 100,
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

        readable = ", ".join(
            f"{entry['label_ru']} "
            f"({entry['area_percent']}%)"
            for entry in objects
        )

        observations.append(
            observation(
                source="scene_objects",
                start=frame["timestamp"],
                end=frame["timestamp"],
                text=(
                    "В кадре приближённо видны: "
                    + readable
                ),
                artifact=frame["artifact"],
                frame_artifact=frame["artifact"],
                extractor="pillow-numpy-scene-heuristics",
                data={
                    "kind": "scene_objects",
                    "objects": objects,
                    "method": "heuristic-fallback",
                    "machine_generated": True,
                    "requires_review": True,
                    "time_is_approximate": True,
                },
            )
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

    return {
        "frames": saved_frames,
        "observations": observations,
        "errors": errors,
        "model": None,
        "method": "heuristic-fallback",
        "model_error": str(model_error)[:1000],
        "sampled_frames": len(frames),
        "successful_frames": len(saved_frames),
        "note": (
            "Семантическая модель недоступна без загрузки. "
            "Типы поверхностей оценены по цвету и текстуре; "
            "это не координаты и не подтверждённый адрес."
        ),
    }


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
