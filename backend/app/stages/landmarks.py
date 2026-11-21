"""Ориентиры и геометрия кадра.

Для ключевых кадров оценивает линию горизонта, точку схода,
вертикальные доминанты, симметрию и силуэт застройки. Отдельно
собирает узнаваемые ориентиры (церковь, памятник, башня, дом,
мост) и надписи. Эти признаки помогают сопоставить кадр с картой
или со справочным снимком.
"""

import math
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from app.errors import SkipStage
from app.keyframes import collect_frames
from app.observations import observation
from app.utils.timecodes import numeric_time, timestamp


LANDMARK_LABELS = {
    "church",
    "temple",
    "monument",
    "tower",
    "skyscraper",
    "castle",
    "building",
    "house",
    "bridge",
    "fountain",
    "column",
    "pier",
    "stadium",
    "arch",
}

LANDMARK_MIN_AREA = 1.0
MAX_REPORTED_FRAMES = 160


def extract_landmarks(
    folder: Path,
    run_folder: Path,
    stages: dict,
    progress,
) -> dict:
    frames = collect_frames(stages)

    if not frames:
        raise SkipStage(
            "Нет кадров для поиска ориентиров: визуальные "
            "этапы не завершены."
        )

    ocr = _ocr_by_time(stages)
    objects = _objects_by_time(stages)

    analyzed = []

    for index, frame in enumerate(frames):
        if index % 10 == 0:
            progress(
                index / max(len(frames), 1) * 95,
                f"Геометрия кадров: {index + 1} "
                f"из {len(frames)}",
            )

        artifact = frame.get("artifact")

        if not artifact:
            continue

        path = folder / artifact

        if not path.is_file():
            continue

        moment = round(float(frame["timestamp"]), 3)
        geometry = _geometry(path)

        if geometry is None:
            continue

        labels = objects.get(moment, [])
        landmarks = [
            item
            for item in labels
            if item["label"] in LANDMARK_LABELS
            and item["area_percent"] >= LANDMARK_MIN_AREA
        ]
        landmarks.sort(
            key=lambda item: -item["area_percent"]
        )

        analyzed.append({
            "timestamp": moment,
            "artifact": artifact,
            "landmarks": landmarks[:4],
            "signs": ocr.get(moment, [])[:4],
            **geometry,
        })

    if not analyzed:
        raise SkipStage(
            "Не удалось прочитать ни одного кадра."
        )

    progress(100, "Ориентиры и геометрия готовы")

    summary = _summary(analyzed)

    text = _summary_text(summary)

    return {
        "frames": analyzed[:MAX_REPORTED_FRAMES],
        "frame_count_total": len(analyzed),
        "landmarks": summary["landmarks"],
        "geometry": summary["geometry"],
        "landmark_count": len(summary["landmarks"]),
        "observations": [
            observation(
                source="landmarks",
                start=analyzed[0]["timestamp"],
                end=analyzed[-1]["timestamp"],
                text=text,
                extractor="opencv-geometry",
                data={
                    "landmarks": summary["landmarks"],
                    "geometry": summary["geometry"],
                    "frame_count": len(analyzed),
                },
            )
        ],
        "note": (
            "Геометрия и ориентиры оценены по кадрам. Это "
            "признаки для сопоставления с картой и снимками, "
            "а не координаты."
        ),
    }


def _objects_by_time(stages: dict) -> dict:
    result = stages.get("scene_objects", {}).get("result") or {}
    collected = {}

    for frame in result.get("frames") or []:
        if not isinstance(frame, dict):
            continue

        moment = numeric_time(frame.get("timestamp"))

        if moment is None:
            continue

        collected[round(moment, 3)] = [
            {
                "label": item.get("label"),
                "label_ru": (
                    item.get("label_ru") or item.get("label")
                ),
                "area_percent": round(
                    float(item.get("area_percent") or 0),
                    2,
                ),
            }
            for item in frame.get("objects") or []
            if isinstance(item, dict)
        ]

    return collected


def _ocr_by_time(stages: dict) -> dict:
    stage = stages.get("ocr", {})

    if stage.get("status") != "completed":
        return {}

    collected = {}

    for item in stage.get("observations") or []:
        if item.get("review") == "rejected":
            continue

        text = item.get("corrected_text") or item.get("text")

        if not text:
            continue

        moment = numeric_time(item.get("start"))

        if moment is None:
            continue

        collected.setdefault(round(moment, 3), []).append(
            " ".join(str(text).split())
        )

    return collected


def _geometry(path: Path):
    image = cv2.imread(str(path))

    if image is None:
        return None

    image = cv2.resize(image, (640, 360))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    edges = cv2.Canny(gray, 60, 160)
    lines = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180,
        threshold=55,
        minLineLength=max(40, width // 6),
        maxLineGap=14,
    )

    vertical = []
    horizontal = []
    perspective = []

    for line in (lines if lines is not None else []):
        values = np.asarray(line).reshape(-1).tolist()

        if len(values) < 4:
            continue

        x1, y1, x2, y2 = [
            int(value) for value in values[:4]
        ]
        dx = x2 - x1
        dy = y2 - y1

        if abs(dx) < abs(dy) * 0.3:
            vertical.append((x1, y1, x2, y2))
        elif abs(dy) < abs(dx) * 0.3:
            horizontal.append((x1, y1, x2, y2))
        else:
            perspective.append((x1, y1, x2, y2))

    horizon = _horizon(horizontal, gray, height)
    vanishing = _vanishing(perspective, width, height)
    symmetry = _symmetry(gray)
    skyline = _skyline(gray)
    texture = float(np.std(skyline)) if skyline else 0.0

    return {
        "horizon_ratio": round(horizon, 3),
        "vanishing_point": vanishing,
        "vertical_lines": len(vertical),
        "horizontal_lines": len(horizontal),
        "perspective_lines": len(perspective),
        "symmetry": round(symmetry, 3),
        "skyline": [round(value, 3) for value in skyline],
        "skyline_roughness": round(texture, 3),
        "geometry_text": _geometry_text(
            horizon,
            vanishing,
            len(vertical),
            symmetry,
            texture,
        ),
    }


def _horizon(horizontal, gray, height):
    if horizontal:
        return float(np.median([
            (y1 + y2) / 2 / height
            for _, y1, _, y2 in horizontal
        ]))

    gradient = np.abs(
        np.diff(gray.astype(np.float32), axis=0)
    ).sum(axis=1)
    band = gradient[
        int(height * 0.2):int(height * 0.8)
    ]

    if band.size:
        return float(
            (int(np.argmax(band)) + int(height * 0.2))
            / height
        )

    return 0.5


def _vanishing(perspective, width, height):
    if len(perspective) < 2:
        return None

    ordered = sorted(
        perspective,
        key=lambda item: -(
            (item[2] - item[0]) ** 2
            + (item[3] - item[1]) ** 2
        ),
    )[:10]

    points = []

    for first in range(len(ordered)):
        for second in range(first + 1, len(ordered)):
            point = _intersection(
                ordered[first],
                ordered[second],
            )

            if point is None:
                continue

            x, y = point

            if (
                -width <= x <= width * 2
                and -height <= y <= height * 2
            ):
                points.append((x, y))

    if not points:
        return None

    x = float(np.median([point[0] for point in points]))
    y = float(np.median([point[1] for point in points]))

    return [
        round(x / width, 3),
        round(y / height, 3),
    ]


def _intersection(first, second):
    x1, y1, x2, y2 = first
    x3, y3, x4, y4 = second

    denominator = (
        (x1 - x2) * (y3 - y4)
        - (y1 - y2) * (x3 - x4)
    )

    if abs(denominator) < 1e-6:
        return None

    px = (
        (x1 * y2 - y1 * x2) * (x3 - x4)
        - (x1 - x2) * (x3 * y4 - y3 * x4)
    ) / denominator
    py = (
        (x1 * y2 - y1 * x2) * (y3 - y4)
        - (y1 - y2) * (x3 * y4 - y3 * x4)
    ) / denominator

    return px, py


def _symmetry(gray):
    height, width = gray.shape
    half = width // 2
    left = gray[:, :half].astype(np.float32)
    right = cv2.flip(gray[:, half:half * 2], 1).astype(
        np.float32
    )

    if left.size == 0 or right.size == 0:
        return 0.0

    left = left - left.mean()
    right = right - right.mean()
    denominator = math.sqrt(
        float((left ** 2).sum()) * float((right ** 2).sum())
    )

    if denominator < 1e-6:
        return 0.0

    value = float((left * right).sum()) / denominator

    return max(0.0, min(1.0, (value + 1) / 2))


def _skyline(gray):
    height, width = gray.shape
    gradient = np.abs(
        np.diff(gray.astype(np.float32), axis=0)
    )
    values = []
    step = max(1, width // 16)

    for x in range(0, width, step):
        column = gradient[:, x]
        limit = int(height * 0.7)

        if column.size == 0:
            values.append(0.0)
            continue

        threshold = float(np.mean(column[:limit])) * 2.5
        candidates = np.where(column[:limit] > threshold)[0]

        if candidates.size:
            values.append(
                round(float(candidates[0]) / height, 3)
            )
        else:
            values.append(0.0)

    return values[:16]


def _geometry_text(
    horizon,
    vanishing,
    vertical_lines,
    symmetry,
    roughness,
):
    parts = [f"горизонт на {horizon * 100:.0f}% высоты"]

    if vanishing:
        x, y = vanishing
        side = (
            "слева"
            if x < 0.42
            else "справа"
            if x > 0.58
            else "по центру"
        )
        parts.append(
            f"точка схода {side} ({x * 100:.0f}% ширины, "
            f"{y * 100:.0f}% высоты)"
        )

    if vertical_lines >= 8:
        parts.append("много вертикальных доминант: застройка")
    elif vertical_lines >= 3:
        parts.append("есть вертикальные ориентиры")
    else:
        parts.append("выраженных вертикалей мало: открытое пространство")

    if symmetry >= 0.78:
        parts.append("симметричная композиция")
    elif symmetry <= 0.5:
        parts.append("асимметричная композиция")

    if roughness >= 0.16:
        parts.append("рваный силуэт застройки или рельефа")
    else:
        parts.append("относительно ровный силуэт")

    return "; ".join(parts) + "."


def _summary(frames):
    landmarks = {}

    for frame in frames:
        for item in frame["landmarks"]:
            label = item.get("label_ru") or item.get("label")
            entry = landmarks.setdefault(label, {
                "label": label,
                "frame_count": 0,
                "max_area_percent": 0.0,
                "timestamps": [],
            })

            entry["frame_count"] += 1
            entry["max_area_percent"] = max(
                entry["max_area_percent"],
                item["area_percent"],
            )
            entry["timestamps"].append(frame["timestamp"])

    result = []

    for entry in landmarks.values():
        entry["max_area_percent"] = round(
            entry["max_area_percent"],
            1,
        )
        entry["timestamps"] = sorted(set(entry["timestamps"]))[:20]
        result.append(entry)

    result.sort(
        key=lambda item: (
            -item["frame_count"],
            -item["max_area_percent"],
        )
    )

    horizons = [
        frame["horizon_ratio"]
        for frame in frames
    ]
    verticals = Counter(
        "много"
        if frame["vertical_lines"] >= 8
        else "средне"
        if frame["vertical_lines"] >= 3
        else "мало"
        for frame in frames
    )
    vanishings = [
        frame["vanishing_point"]
        for frame in frames
        if frame.get("vanishing_point")
    ]

    geometry = {
        "frame_count": len(frames),
        "median_horizon": round(
            float(np.median(horizons)),
            3,
        ) if horizons else None,
        "vertical_profile": dict(verticals),
        "vanishing_frames": len(vanishings),
        "median_vanishing_x": (
            round(float(np.median([
                item[0] for item in vanishings
            ])), 3)
            if vanishings
            else None
        ),
        "median_symmetry": round(
            float(np.median([
                frame["symmetry"] for frame in frames
            ])),
            3,
        ),
        "median_skyline_roughness": round(
            float(np.median([
                frame["skyline_roughness"]
                for frame in frames
            ])),
            3,
        ),
    }

    return {
        "landmarks": result[:12],
        "geometry": geometry,
    }


def _summary_text(summary):
    lines = []

    landmarks = summary["landmarks"]

    if landmarks:
        lines.append(
            "Ориентиры: " + ", ".join(
                f"{item['label']} "
                f"({item['frame_count']} кадр., "
                f"до {item['max_area_percent']}%)"
                for item in landmarks[:8]
            ) + "."
        )
    else:
        lines.append("Узнаваемые ориентиры не найдены.")

    geometry = summary["geometry"]
    parts = []

    if geometry.get("median_horizon") is not None:
        parts.append(
            "горизонт около "
            f"{geometry['median_horizon'] * 100:.0f}%"
        )

    if geometry.get("median_vanishing_x") is not None:
        parts.append(
            "точка схода по X около "
            f"{geometry['median_vanishing_x'] * 100:.0f}%"
        )

    vertical = geometry.get("vertical_profile") or {}

    if vertical:
        parts.append(
            "вертикали: "
            + ", ".join(
                f"{name} — {count}"
                for name, count in vertical.items()
            )
        )

    if parts:
        lines.append("Геометрия: " + "; ".join(parts) + ".")

    return " ".join(lines)
