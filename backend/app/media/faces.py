"""Обнаружение лиц и анонимная группировка людей.

Используется детектор YuNet из OpenCV (локальный ONNX-файл) и
простое описание внешности (HOG-признаки лица). Одинаковые лица
внутри одного видео получают метки «Человек 1», «Человек 2» и т. д.
Это не распознавание личности: сервис не знает, кто это, и не
сравнивает людей с внешними базами.
"""

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np


MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "face_detection_yunet_2023mar.onnx"
)

MAX_SIDE = 960
SCORE_THRESHOLD = 0.75
NMS_THRESHOLD = 0.3
TOP_K = 5000

# Порог косинусного расстояния между описаниями лиц. Подобран
# консервативно: лучше показать двух разных «людей», чем склеить
# разных людей в одного.
SAME_PERSON_DISTANCE = 0.30

HOG_CELLS = 4
HOG_BINS = 8
HOG_SIZE = 32


def model_available() -> bool:
    return MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 1000


@lru_cache(maxsize=1)
def detector():
    if not model_available():
        raise RuntimeError(
            "Модель YuNet не найдена: "
            f"{MODEL_PATH.name}."
        )

    return cv2.FaceDetectorYN_create(
        str(MODEL_PATH),
        "",
        (320, 320),
        SCORE_THRESHOLD,
        NMS_THRESHOLD,
        TOP_K,
    )


def detect_faces(path: Path) -> list[dict]:
    """
    Находит лица на кадре.

    Возвращает список с рамкой в долях кадра, оценкой и описанием
    внешности. Рамка нормализована, поэтому не зависит от размера
    исходного кадра.
    """
    data = np.fromfile(str(path), dtype=np.uint8) if Path(path).exists() else None

    if data is None or not data.size:
        return []

    image = cv2.imdecode(data, cv2.IMREAD_COLOR)

    if image is None:
        return []

    height, width = image.shape[:2]
    scale = min(1.0, MAX_SIDE / max(width, height))

    if scale < 1.0:
        image = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    height, width = image.shape[:2]
    handle = detector()
    handle.setInputSize((width, height))
    _, raw = handle.detect(image)

    if raw is None:
        return []

    faces = []

    for row in np.asarray(raw):
        values = np.asarray(row).reshape(-1)

        if values.size < 15:
            continue

        x, y, w, h = (float(value) for value in values[:4])
        score = float(values[14])

        if score < SCORE_THRESHOLD or w <= 0 or h <= 0:
            continue

        x1 = max(0.0, min(1.0, x / width))
        y1 = max(0.0, min(1.0, y / height))
        x2 = max(0.0, min(1.0, (x + w) / width))
        y2 = max(0.0, min(1.0, (y + h) / height))

        if x2 - x1 < 0.015 or y2 - y1 < 0.015:
            continue

        face = {
            "bbox": [
                round(x1, 4),
                round(y1, 4),
                round(x2, 4),
                round(y2, 4),
            ],
            "score": round(score, 3),
            "descriptor": _descriptor(image, (x, y, w, h)),
        }
        faces.append(face)

    return faces


def _descriptor(image, box) -> np.ndarray | None:
    """HOG-описание лица для сравнения лиц между кадрами."""
    x, y, w, h = (int(round(value)) for value in box)
    height, width = image.shape[:2]

    x1 = max(0, min(width - 1, x))
    y1 = max(0, min(height - 1, y))
    x2 = max(x1 + 1, min(width, x + w))
    y2 = max(y1 + 1, min(height, y + h))

    crop = image[y1:y2, x1:x2]

    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (HOG_SIZE, HOG_SIZE))
    gray = cv2.equalizeHist(gray)
    gray = gray.astype(np.float32) / 255.0

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    angle = (np.arctan2(gy, gx) % np.pi) / np.pi

    cell = HOG_SIZE // HOG_CELLS
    bins = np.minimum(
        (angle * HOG_BINS).astype(np.int32),
        HOG_BINS - 1,
    )

    features = np.zeros(
        (HOG_CELLS, HOG_CELLS, HOG_BINS),
        dtype=np.float32,
    )

    for cy in range(HOG_CELLS):
        for cx in range(HOG_CELLS):
            y0 = cy * cell
            x0 = cx * cell
            cell_bins = bins[y0:y0 + cell, x0:x0 + cell]
            cell_mag = magnitude[y0:y0 + cell, x0:x0 + cell]
            np.add.at(
                features[cy, cx],
                cell_bins.reshape(-1),
                cell_mag.reshape(-1),
            )

    vector = features.reshape(-1)
    norm = float(np.linalg.norm(vector))

    if norm < 1e-6:
        return None

    return vector / norm


def cluster_faces(frames: list[dict]) -> list[dict]:
    """
    Объединяет лица в анонимных «людей» по описанию внешности.

    frames — список кадров с полем faces. Каждому лицу добавляется
    person_id. Возвращает сводку по людям.
    """
    centroids: list[dict] = []

    for frame in frames:
        for face in frame.get("faces", []):
            descriptor = face.pop("descriptor", None)

            if descriptor is None:
                face["person"] = None
                continue

            best = None

            for index, centroid in enumerate(centroids):
                distance = float(
                    1.0 - np.dot(descriptor, centroid["vector"])
                )

                if (
                    distance <= SAME_PERSON_DISTANCE
                    and (best is None or distance < best[1])
                ):
                    best = index, distance

            if best is None:
                centroids.append({
                    "vector": descriptor,
                    "weight": 1.0,
                })
                person = len(centroids)
            else:
                index, _ = best
                person = index + 1
                centroid = centroids[index]
                weight = centroid["weight"] + 1.0
                merged = (
                    centroid["vector"] * centroid["weight"]
                    + descriptor
                ) / weight
                length = float(np.linalg.norm(merged))
                centroid["vector"] = (
                    merged / length if length > 1e-6 else merged
                )
                centroid["weight"] = weight

            face["person"] = f"Человек {person}"

    return _people(frames)


def _people(frames: list[dict]) -> list[dict]:
    collected = {}

    for frame in frames:
        for face in frame.get("faces", []):
            label = face.get("person")

            if not label:
                continue

            entry = collected.setdefault(label, {
                "label": label,
                "appearances": [],
            })

            entry["appearances"].append({
                "timestamp": frame["timestamp"],
                "artifact": frame.get("artifact"),
                "bbox": face.get("bbox"),
                "score": face.get("score"),
            })

    people = []

    for entry in collected.values():
        appearances = sorted(
            entry["appearances"],
            key=lambda item: item["timestamp"],
        )
        entries = []
        seen = set()

        # Один человек может попасть в несколько кадров подряд:
        # для интерфейса достаточно одного появления на кадр.
        for item in appearances:
            key = round(float(item["timestamp"]), 2)

            if key in seen:
                continue

            seen.add(key)
            entries.append(item)

        best = max(
            entries,
            key=lambda item: float(item.get("score") or 0),
        )

        people.append({
            "label": entry["label"],
            "frame_count": len(entries),
            "first_start": entries[0]["timestamp"],
            "last_end": entries[-1]["timestamp"],
            "timestamps": [item["timestamp"] for item in entries[:20]],
            "best_frame": {
                "timestamp": best["timestamp"],
                "artifact": best.get("artifact"),
                "bbox": best.get("bbox"),
                "score": best.get("score"),
            },
        })

    people.sort(
        key=lambda item: (-item["frame_count"], item["first_start"])
    )

    return people
