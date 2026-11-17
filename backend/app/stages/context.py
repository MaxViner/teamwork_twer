"""Повторы в видео.

Ищет одинаковые надписи и визуально похожие кадры, которые
встречаются несколько раз. Повторяющиеся вывески, номера и виды
помогают подтвердить место и отсеять случайные совпадения OCR.
"""

import unicodedata
from pathlib import Path

from app.errors import SkipStage
from app.observations import observation


def extract_structure(
    folder: Path,
    run_folder: Path,
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

    text_observations, text_groups = _text_repetitions(
        folder,
        ocr_items,
    )

    frames = _unique_frames(
        folder,
        stages,
        ocr_items,
    )

    frame_observations, errors = _frame_similarity(
        folder,
        frames,
        progress,
    )

    observations = text_observations + frame_observations

    progress(100, "Поиск повторов завершён")

    note = (
        "Повтор надписи или похожий кадр не доказывает, "
        "что это один и тот же объект, улица или место."
    )

    if not observations:
        note = (
            "Повторяющихся надписей и визуально похожих "
            "кадров не найдено."
        )

    return {
        "text_groups": text_groups,
        "compared_frames": len(frames),
        "observations": observations,
        "errors": errors,
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


def _text_repetitions(
    folder: Path,
    items: list[dict],
) -> tuple[list[dict], list[dict]]:
    groups = {}

    for item in items:
        text = str(item.get("text", "")).strip()

        if len(text) < 4:
            continue

        key = normalized_text(text)
        groups.setdefault(key, []).append(item)

    observations = []
    text_groups = []

    for key, group in groups.items():
        if len(group) < 2:
            continue

        group = sorted(
            group,
            key=lambda entry: float(
                entry.get("start", 0.0)
            ),
        )

        first = group[0]
        last = group[-1]

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

        observations.append(
            observation(
                source="reappearance",
                start=float(first.get("start", 0.0)),
                end=float(last.get("start", 0.0)),
                text=(
                    f"Надпись повторяется {len(group)} раз: "
                    f"{text[:200]}"
                ),
                artifact=last.get("artifact"),
                frame_artifact=last.get("frame_artifact"),
                extractor="text-repetition",
                data={
                    "kind": "text_repetition",
                    "text": text,
                    "count": len(group),
                    "observation_ids": [
                        item.get("id")
                        for item in group
                    ],
                    "same_object_is_confirmed": False,
                    "requires_review": True,
                },
            )
        )

    observations.sort(
        key=lambda item: float(item.get("start", 0.0)),
    )

    return observations, text_groups


def _unique_frames(
    folder: Path,
    stages: dict,
    items: list[dict],
) -> list[dict]:
    frames = []
    seen = set()

    result = stages.get("ocr", {}).get("result", {})

    for entry in result.get("frames", []):
        artifact = entry.get("artifact")

        if not artifact or artifact in seen:
            continue

        path = folder / artifact

        if not path.is_file():
            continue

        seen.add(artifact)
        frames.append({
            "timestamp": float(
                entry.get("timestamp", 0.0)
            ),
            "artifact": artifact,
            "path": path,
        })

    for item in items:
        artifact = item.get("frame_artifact")

        if not artifact or artifact in seen:
            continue

        path = folder / artifact

        if not path.is_file():
            continue

        seen.add(artifact)
        frames.append({
            "timestamp": float(item.get("start", 0.0)),
            "artifact": artifact,
            "path": path,
        })

    frames.sort(key=lambda entry: entry["timestamp"])

    return frames[:24]


def _frame_similarity(
    folder: Path,
    frames: list[dict],
    progress,
) -> tuple[list[dict], list[dict]]:
    if len(frames) < 2:
        return [], []

    try:
        import cv2

        detector = cv2.ORB_create(nfeatures=1500)

    except Exception as error:
        return [], [{
            "kind": "opencv_unavailable",
            "error": str(error)[:1000],
        }]

    features = {}
    errors = []

    for index, frame in enumerate(frames):
        progress(
            index / max(1, len(frames)) * 30,
            f"Извлекаю признаки кадров: "
            f"{index + 1}/{len(frames)}",
        )

        try:
            features[frame["artifact"]] = _image_features(
                frame["path"],
                detector,
            )

        except Exception as error:
            errors.append({
                "artifact": frame["artifact"],
                "error": str(error)[:1000],
            })

    usable = [
        frame
        for frame in frames
        if features.get(frame["artifact"]) is not None
    ]

    pairs = [
        (first, second)
        for index, first in enumerate(usable)
        for second in usable[index + 1:]
    ]

    observations = []

    for index, (first, second) in enumerate(pairs):
        progress(
            30 + index / max(1, len(pairs)) * 70,
            f"Сравниваю кадры: {index + 1}/{len(pairs)}",
        )

        try:
            match = _compare_features(
                features[first["artifact"]],
                features[second["artifact"]],
            )

        except Exception as error:
            errors.append({
                "artifact": second["artifact"],
                "error": str(error)[:1000],
            })
            continue

        if match is None:
            continue

        observations.append(
            observation(
                source="reappearance",
                start=float(first["timestamp"]),
                end=float(second["timestamp"]),
                text=(
                    "Визуальное сходство кадров: "
                    f"{_timestamp(first['timestamp'])} и "
                    f"{_timestamp(second['timestamp'])} "
                    f"({match['inliers']} устойчивых совпадений)."
                ),
                artifact=second["artifact"],
                frame_artifact=second["artifact"],
                extractor="ORB+RANSAC",
                data={
                    "kind": "frame_similarity",
                    "first_artifact": first["artifact"],
                    "second_artifact": second["artifact"],
                    "first_time": first["timestamp"],
                    "second_time": second["timestamp"],
                    "match": match,
                    "same_object_is_confirmed": False,
                    "requires_review": True,
                },
            )
        )

    return observations, errors


def _image_features(path: Path, detector):
    import numpy as np

    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("L")
        image.thumbnail((512, 512))
        gray = np.array(image)

    return detector.detectAndCompute(gray, None)


def _compare_features(first, second):
    import cv2
    import numpy as np

    keypoints_a, descriptors_a = first
    keypoints_b, descriptors_b = second

    if (
        descriptors_a is None
        or descriptors_b is None
        or len(descriptors_a) < 12
        or len(descriptors_b) < 12
    ):
        return None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    pairs = matcher.knnMatch(
        descriptors_a,
        descriptors_b,
        k=2,
    )

    good = [
        pair[0]
        for pair in pairs
        if len(pair) == 2
        and pair[0].distance < 0.7 * pair[1].distance
    ]

    if len(good) < 12:
        return None

    source_points = np.float32([
        keypoints_a[item.queryIdx].pt
        for item in good
    ]).reshape(-1, 1, 2)

    target_points = np.float32([
        keypoints_b[item.trainIdx].pt
        for item in good
    ]).reshape(-1, 1, 2)

    matrix, mask = cv2.findHomography(
        source_points,
        target_points,
        cv2.RANSAC,
        4.0,
    )

    if matrix is None or mask is None:
        return None

    inliers = int(mask.sum())
    ratio = inliers / len(good)

    if inliers < 12 or ratio < 0.6:
        return None

    return {
        "good_matches": len(good),
        "inliers": inliers,
        "inlier_ratio": round(ratio, 3),
    }


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value))

    return " ".join(text.casefold().split())


def _timestamp(seconds: float) -> str:
    milliseconds = round(float(seconds) * 1000)
    minutes, remainder = divmod(
        milliseconds,
        60_000,
    )
    seconds_part, milliseconds = divmod(
        remainder,
        1000,
    )

    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)

        return (
            f"{hours:02d}:{minutes:02d}:"
            f"{seconds_part:02d}.{milliseconds:03d}"
        )

    return (
        f"{minutes:02d}:{seconds_part:02d}."
        f"{milliseconds:03d}"
    )
