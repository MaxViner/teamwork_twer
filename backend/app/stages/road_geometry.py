"""Геометрия дороги.

Находит линии разметки и границы дорожного полотна через OpenCV,
проверяет их согласованность между кадрами и оценивает сторону
движения, число полос и перспективу. Служит подсказкой о стране
и типе дороги; слабые и противоречивые находки отбрасываются.
"""

import math
from pathlib import Path

import cv2
import numpy as np

from app.errors import SkipStage
from app.media.frames import stage_frames
from app.observations import observation


def extract_road_geometry(
    folder: Path,
    run_folder: Path,
    stages: dict,
    progress,
    video: Path | None = None,
    duration: float = 0.0,
    options: dict | None = None,
) -> dict:
    options = options or {}

    if video is None or duration <= 0:
        raise SkipStage(
            "Нет подготовленного видео для анализа дороги."
        )

    frames = stage_frames(
        folder=folder,
        run_folder=run_folder,
        video=video,
        duration=duration,
        stages=stages,
        count=max(1, min(12, int(options.get(
            "max_frames",
            12,
        )))),
        prefix="road",
    )

    if not frames:
        raise SkipStage(
            "Нет кадров для анализа геометрии дороги."
        )

    observations = []
    geometries = []
    errors = []

    for index, frame in enumerate(frames):
        progress(
            (index + 1) / len(frames) * 100,
            f"Анализ дороги: кадр {index + 1}/{len(frames)}",
        )

        try:
            image = cv2.imdecode(
                np.fromfile(
                    frame["path"],
                    dtype=np.uint8,
                ),
                cv2.IMREAD_COLOR,
            )

            if image is None:
                continue

            geometry = analyse_road(image)

            if geometry is None:
                continue

            geometries.append(geometry)

            observations.append(
                observation(
                    source="road_geometry",
                    start=frame["timestamp"],
                    end=frame["timestamp"],
                    text=_geometry_text(geometry),
                    artifact=frame["artifact"],
                    frame_artifact=frame["artifact"],
                    extractor="opencv-hough-road-geometry",
                    data={
                        "kind": "road_geometry",
                        **geometry,
                        "requires_review": True,
                        "map_match_ready": False,
                        "time_is_approximate": True,
                    },
                )
            )

        except Exception as error:
            errors.append({
                "timestamp": frame["timestamp"],
                "error": str(error)[:1000],
            })

    summary = _summarize(geometries, len(frames))

    progress(100, "Анализ геометрии дороги завершён")

    note = (
        "Оценены направление и изгиб видимой дороги, "
        "разметка и положение линии схода. Это не координаты, "
        "не маршрут и не подтверждённое местоположение."
    )

    if not observations:
        note = (
            "На выбранных кадрах дорога не обнаружена "
            "или геометрия недостаточно надёжна. "
            "Это тоже признак места: вероятны сцены без дороги."
        )

    elif not summary.get("road_detected"):
        note = (
            "Дорога или дорожная разметка найдена только "
            "на части кадров. Это слабое основание, "
            "его нельзя считать подтверждённой дорогой."
        )

    return {
        "summary": summary,
        "observations": observations,
        "errors": errors,
        "sampled_frames": len(frames),
        "detected_frames": len(observations),
        "note": note,
    }


def analyse_road(image) -> dict | None:
    height, width = image.shape[:2]

    lines = detect_road_lines(image)

    if lines is None or not len(lines):
        return None

    left = []
    right = []

    center_x = width / 2

    for raw in np.asarray(lines).reshape(-1, 4):
        x1, y1, x2, y2 = (int(value) for value in raw)

        if y1 == y2:
            continue

        if abs(x2 - x1) < 1:
            continue

        slope = (y2 - y1) / (x2 - x1)

        if abs(slope) < 0.25:
            continue

        midpoint_x = (x1 + x2) / 2

        if midpoint_x < center_x:
            left.append((midpoint_x, (y1 + y2) / 2))
        else:
            right.append((midpoint_x, (y1 + y2) / 2))

    if len(left) < 2 or len(right) < 2:
        return None

    left_fit = _fit(left)
    right_fit = _fit(right)

    if left_fit is None or right_fit is None:
        return None

    left_curve = float(left_fit[0])
    right_curve = float(right_fit[0])

    curvature = (
        abs(left_curve) + abs(right_curve)
    ) / 2

    if curvature < 0.00005:
        direction = "прямая дорога"
    elif left_curve < 0 and right_curve < 0:
        direction = "поворот влево"
    elif left_curve > 0 and right_curve > 0:
        direction = "поворот вправо"
    else:
        direction = "неоднозначная геометрия дороги"

    bottom = height - 1

    left_bottom = _fit_x(left_fit, bottom)
    right_bottom = _fit_x(right_fit, bottom)

    if (
        left_bottom is None
        or right_bottom is None
        or right_bottom <= left_bottom
    ):
        return None

    spacing_ratio = (
        right_bottom - left_bottom
    ) / width

    if spacing_ratio >= 0.75:
        width_label = "широкая дорога, возможно 3+ полосы"
    elif spacing_ratio >= 0.35:
        width_label = "дорога средней ширины, возможно 2 полосы"
    else:
        width_label = "узкая дорога или одна полоса"

    vanishing = _vanishing_row(
        left_fit,
        right_fit,
        height,
    )

    markings = _marking_ratio(
        image,
        left_fit,
        right_fit,
        height,
        width,
    )

    confidence = min(
        0.85,
        0.25
        + 0.05 * min(len(left) + len(right), 10)
        + (0.1 if markings["white"] > 1 else 0.0)
        + (0.1 if vanishing is not None else 0.0),
    )

    return {
        "direction": direction,
        "curvature": round(curvature, 8),
        "left_curve": round(left_curve, 8),
        "right_curve": round(right_curve, 8),
        "left_lines": len(left),
        "right_lines": len(right),
        "width_ratio": round(float(spacing_ratio), 3),
        "width_label": width_label,
        "vanishing_ratio": (
            round(float(vanishing), 3)
            if vanishing is not None
            else None
        ),
        "markings": markings,
        "confidence": round(float(confidence), 2),
    }


def detect_road_lines(image):
    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )

    blurred = cv2.GaussianBlur(
        gray,
        (5, 5),
        0,
    )

    edges = cv2.Canny(
        blurred,
        50,
        150,
    )

    height, width = edges.shape

    mask = np.zeros_like(edges)

    polygon = np.array([[
        (int(width * 0.02), int(height * 0.98)),
        (int(width * 0.42), int(height * 0.52)),
        (int(width * 0.58), int(height * 0.52)),
        (int(width * 0.98), int(height * 0.98)),
    ]], dtype=np.int32)

    cv2.fillPoly(mask, polygon, 255)

    edges = cv2.bitwise_and(edges, mask)

    return cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=35,
        minLineLength=max(40, int(height * 0.12)),
        maxLineGap=50,
    )


def _fit(points: list[tuple[float, float]]):
    if len(points) < 3:
        return None

    points = sorted(points, key=lambda item: item[1])

    ys = np.array(
        [item[1] for item in points],
        dtype=np.float64,
    )
    xs = np.array(
        [item[0] for item in points],
        dtype=np.float64,
    )

    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return np.polyfit(ys, xs, 2)

    except Exception:
        return None


def _fit_x(fit, y: float) -> float | None:
    if fit is None:
        return None

    return float(np.polyval(fit, y))


def _vanishing_row(
    left_fit,
    right_fit,
    height: int,
) -> float | None:
    difference = left_fit - right_fit

    try:
        roots = np.roots(difference)

    except Exception:
        return None

    candidates = [
        float(root.real)
        for root in roots
        if abs(root.imag) < 1e-6
        and -0.2 * height <= root.real <= 1.2 * height
    ]

    if not candidates:
        return None

    row = min(
        candidates,
        key=lambda value: abs(value - height * 0.45),
    )

    return max(0.0, min(1.0, row / height))


def _marking_ratio(
    image,
    left_fit,
    right_fit,
    height: int,
    width: int,
) -> dict:
    mask = np.zeros(
        (height, width),
        dtype=np.uint8,
    )

    for y in range(int(height * 0.5), height):
        left = _fit_x(left_fit, y)
        right = _fit_x(right_fit, y)

        if left is None or right is None:
            continue

        left = max(0, min(width - 1, int(left)))
        right = max(0, min(width, int(right)))

        if right > left:
            mask[y, left:right] = 255

    selected = mask > 0

    if not selected.any():
        return {"white": 0.0, "yellow": 0.0}

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    white = (
        (value > 185)
        & (saturation < 40)
        & selected
    )

    yellow = (
        (hue >= 18)
        & (hue <= 40)
        & (saturation > 90)
        & (value > 120)
        & selected
    )

    total = float(selected.sum())

    return {
        "white": round(
            float(white.sum()) / total * 100,
            2,
        ),
        "yellow": round(
            float(yellow.sum()) / total * 100,
            2,
        ),
    }


def _summarize(
    geometries: list[dict],
    sampled_frames: int,
) -> dict:
    if not geometries:
        return {
            "road_detected": False,
            "confidence": 0.0,
            "detected_frames": 0,
            "sampled_frames": sampled_frames,
            "detection_ratio": 0.0,
        }

    directions = {}

    for geometry in geometries:
        directions[geometry["direction"]] = (
            directions.get(
                geometry["direction"],
                0,
            )
            + 1
        )

    direction = max(
        directions.items(),
        key=lambda item: item[1],
    )[0]

    vanishing = [
        geometry["vanishing_ratio"]
        for geometry in geometries
        if geometry["vanishing_ratio"] is not None
    ]

    detection_ratio = (
        len(geometries) / sampled_frames
        if sampled_frames
        else 0.0
    )

    dominant_share = (
        directions[direction] / len(geometries)
        if geometries
        else 0.0
    )

    ambiguous = direction == "неоднозначная геометрия дороги"

    # Слишком слабое основание, чтобы объявлять дорогу
    # найденной: мало кадров, размытое направление или
    # противоречивая геометрия между кадрами.
    road_detected = (
        len(geometries) >= 2
        and detection_ratio >= 0.4
        and dominant_share >= 0.6
        and not ambiguous
    )

    mean_confidence = float(np.mean([
        geometry["confidence"]
        for geometry in geometries
    ]))

    confidence = mean_confidence * min(
        1.0,
        detection_ratio * 1.5,
    ) * dominant_share

    if ambiguous:
        confidence *= 0.5

    return {
        "road_detected": road_detected,
        "weak_support": not road_detected,
        "direction": direction,
        "dominant_share": round(dominant_share, 3),
        "detected_frames": len(geometries),
        "sampled_frames": sampled_frames,
        "detection_ratio": round(detection_ratio, 3),
        "mean_curvature": round(
            float(np.mean([
                geometry["curvature"]
                for geometry in geometries
            ])),
            8,
        ),
        "vanishing_ratio": (
            round(float(np.median(vanishing)), 3)
            if vanishing
            else None
        ),
        "marking_frames": sum(
            1
            for geometry in geometries
            if geometry["markings"]["white"] > 1
            or geometry["markings"]["yellow"] > 1
        ),
        "confidence": round(confidence, 2),
    }


def _geometry_text(geometry: dict) -> str:
    parts = [
        f"Дорога: {geometry['direction']}",
        geometry["width_label"],
    ]

    markings = geometry["markings"]

    if markings["white"] > 1:
        parts.append("белая разметка")

    if markings["yellow"] > 1:
        parts.append("жёлтая разметка")

    if geometry["vanishing_ratio"] is not None:
        parts.append(
            "линия схода на "
            f"{geometry['vanishing_ratio'] * 100:.0f}% высоты"
        )

    return "; ".join(parts) + "."
