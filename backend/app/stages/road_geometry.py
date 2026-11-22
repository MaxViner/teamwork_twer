"""Дорожные признаки по отдельным кадрам и временным эпизодам.

Кривые и положения объектов выражены в координатах изображения. Эпизод
объединяет близкие наблюдения, но не доказывает, что это одна дорога или
что разные ракурсы пространственно совмещены.
"""

import math
from bisect import bisect_right
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from app.errors import SkipStage
from app.media.frames import stage_frames
from app.observations import observation
from app.stages.visual_profile import analyze_frame

ROAD_SEMANTIC_LABELS = {"road", "path", "bridge"}
SEMANTIC_ROAD_MIN_PERCENT = 1.0
DEFAULT_ROAD_FRAMES = 12
MAX_ROAD_FRAMES = 1500
EPISODE_MAX_GAP = 5.0
EPISODE_MAX_DURATION = 30.0
BEND_LABELS = {
    "left": "поворот влево",
    "right": "поворот вправо",
    "straight": "похоже на прямую дорогу",
    "uncertain": "неоднозначная геометрия дороги",
}
BEND_CLASSES = {label: code for code, label in BEND_LABELS.items()}
CONTEXT_LABELS = {
    "building", "house", "tower", "bridge", "fence", "wall", "pole",
    "signboard", "path", "sidewalk", "water", "river", "traffic light",
}


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

    if video is None or not math.isfinite(duration) or duration <= 0:
        raise SkipStage(
            "Нет подготовленного видео для анализа дороги."
        )

    requested = max(1, min(MAX_ROAD_FRAMES, int(
        options.get("max_frames", DEFAULT_ROAD_FRAMES),
    )))
    frames = stage_frames(
        folder=folder,
        run_folder=run_folder,
        video=video,
        duration=duration,
        stages=stages,
        count=requested,
        prefix="road",
    )

    if not frames:
        raise SkipStage(
            "Нет кадров для анализа геометрии дороги."
        )

    detections = []
    errors = []
    read_frames = 0
    rejected_without_road = 0
    rejected_weak = 0
    object_frames = _frames_by_time(stages, "scene_objects", method="segformer")
    visual_frames = _frames_by_time(stages, "visual_profile")

    for index, frame in enumerate(frames):
        timestamp = float(frame["timestamp"])
        tick = _time_key(timestamp)
        try:
            image = cv2.imdecode(
                np.fromfile(frame["path"], dtype=np.uint8), cv2.IMREAD_COLOR,
            )
            if image is None:
                raise ValueError("Не удалось декодировать кадр.")
            read_frames += 1

            objects = object_frames.get(tick)
            # Чужой ракурс не подтверждает и не опровергает этот кадр.
            evidence = None if objects is None else sum(
                float(item.get("area_percent") or 0)
                for item in objects.get("objects", [])
                if item.get("label") in ROAD_SEMANTIC_LABELS
            )
            if evidence is not None and evidence < SEMANTIC_ROAD_MIN_PERCENT:
                rejected_without_road += 1
                continue

            geometry = analyse_road(image)
            if geometry is None:
                rejected_weak += 1
                continue

            if evidence is None:
                cached_metrics = visual_frames.get(tick, {}).get("metrics")
                metrics = cached_metrics or analyze_frame(frame["path"])
                if not _heuristic_road_ok(geometry, metrics):
                    rejected_weak += 1
                    continue

            geometry["evidence_source"] = "heuristic" if evidence is None else "segformer"
            geometry["semantic_road_percent"] = None if evidence is None else round(evidence, 2)
            detections.append({
                "timestamp": timestamp,
                "artifact": frame["artifact"],
                "sample_index": index,
                "geometry": geometry,
                "context": _road_context(objects, geometry["image_geometry"]),
            })
        except Exception as error:
            errors.append({"timestamp": timestamp, "error": str(error)[:500]})
        finally:
            progress(
                (index + 1) / len(frames) * 99,
                f"Анализ дороги: кадр {index + 1}/{len(frames)}",
            )

    if not read_frames:
        raise RuntimeError("Не удалось прочитать ни одного кадра для анализа дороги.")

    summary = _summarize([item["geometry"] for item in detections], len(frames))
    episodes = _build_episodes(detections, stages, duration / len(frames))
    summary["episode_count"] = len(episodes)
    observations = _build_observations(detections, summary)

    progress(100, "Анализ геометрии дороги завершён")

    return {
        "summary": summary,
        "observations": observations,
        "episodes": episodes,
        "episode_schema_version": 1,
        "errors": errors[:20],
        "error_count": len(errors),
        "requested_frames": requested,
        "sampled_frames": len(frames),
        "read_frames": read_frames,
        "detected_frames": len(detections),
        "rejected_without_road": rejected_without_road,
        "rejected_weak": rejected_weak,
        "note": (
            "Эпизоды объединяют близкие по времени находки, а не подтверждённые локации. "
            "Изгибы и положение объектов даны в перспективе камеры. "
            "Примыкания, расстояния, азимут и тождество дороги между ракурсами не установлены."
            if episodes else
            "Достаточных признаков дороги в выборке не найдено; это не доказывает её отсутствия."
        ),
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

    if len(left) < 3 or len(right) < 3:
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

    image_geometry = _image_geometry(left_fit, right_fit, left, right, width, height)
    if image_geometry is None:
        return None

    direction = BEND_LABELS[image_geometry["bend_class"]]
    near = image_geometry["rows"][-1]
    spacing_ratio = near["right_x"] - near["left_x"]
    if spacing_ratio >= 0.75:
        width_label = "широкий видимый коридор в кадре"
    elif spacing_ratio >= 0.35:
        width_label = "средняя видимая ширина в кадре"
    else:
        width_label = "узкий видимый коридор в кадре"

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
        "image_geometry": image_geometry,
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
    if len(np.unique(ys)) < 3:
        return None

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

    ambiguous = BEND_CLASSES[direction] == "uncertain"

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
        parts.append("светлые участки, возможная белая разметка")

    if markings["yellow"] > 1:
        parts.append("жёлтые участки, возможная разметка")

    if geometry["vanishing_ratio"] is not None:
        parts.append(
            "линия схода на "
            f"{geometry['vanishing_ratio'] * 100:.0f}% высоты"
        )

    return "; ".join(parts) + "."


def _time_key(timestamp: float) -> int:
    return round(float(timestamp) * 1_000_000)


def _frames_by_time(stages: dict, name: str, method: str | None = None) -> dict:
    stage = stages.get(name) or {}
    if stage.get("status") != "completed":
        return {}
    result = stage.get("result") or {}
    if method is not None and result.get("method") != method:
        return {}
    return {_time_key(frame["timestamp"]): frame for frame in result.get("frames", [])}


def _image_geometry(left_fit, right_fit, left, right, width, height) -> dict | None:
    # Не экстраполируем коридор за общий вертикальный диапазон опор линий.
    far_y = max(min(y for _, y in left), min(y for _, y in right))
    near_y = min(max(y for _, y in left), max(y for _, y in right))
    if near_y - far_y < 0.10 * height:
        return None
    rows = []
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = far_y + (near_y - far_y) * fraction
        lx = _fit_x(left_fit, y) / width
        rx = _fit_x(right_fit, y) / width
        if not (0 <= lx < rx <= 1) or rx - lx < 0.025:
            return None
        rows.append({"y": round(y / height, 4), "left_x": round(lx, 4),
                     "right_x": round(rx, 4), "center_x": round((lx + rx) / 2, 4)})

    # Отклонение середины от хорды: отдельно для обеих границ.
    # Для визуального изгиба вправо середина лежит левее хорды.
    offsets = [rows[2][key] - (rows[0][key] + rows[-1][key]) / 2
               for key in ("left_x", "right_x")]
    threshold = 0.012
    if max(abs(value) for value in offsets) < threshold:
        bend = "straight"
    elif min(offsets) >= threshold:
        bend = "left"
    elif max(offsets) <= -threshold:
        bend = "right"
    else:
        bend = "uncertain"
    return {"space": "image_normalized_top_left", "rows": rows,
            "bend_class": bend, "edge_chord_offsets": [round(v, 4) for v in offsets]}


def _road_context(frame: dict | None, geometry: dict) -> list[dict]:
    if frame is None:
        return []
    rows = geometry["rows"]
    clues = []
    for obj in frame.get("objects", []):
        label = obj.get("label")
        bbox = obj.get("bbox")
        score = float(obj.get("confidence") or 0)
        if label not in CONTEXT_LABELS or not bbox or len(bbox) != 4 or score < 0.45:
            continue
        x1, y1, x2, y2 = bbox
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            continue
        side = "unknown"
        if rows[0]["y"] <= y2 <= rows[-1]["y"]:
            grid = [row["y"] for row in rows]
            left = float(np.interp(y2, grid, [row["left_x"] for row in rows]))
            right = float(np.interp(y2, grid, [row["right_x"] for row in rows]))
            if x2 <= left:
                side = "left"
            elif x1 >= right:
                side = "right"
            else:
                side = "image_overlap"
        clues.append({"label": label, "label_ru": obj.get("label_ru") or label,
                      "image_side": side, "bbox": bbox, "model_score": score,
                      "evidence_source": "segformer", "artifact": frame["artifact"]})
    return sorted(clues, key=lambda item: -item["model_score"])[:6]


def _build_episodes(detections: list[dict], stages: dict, sample_step: float) -> list[dict]:
    scene_stage = stages.get("scenes") or {}
    intervals = (scene_stage.get("result") or {}).get("intervals", [])
    cuts = sorted(float(start) for start, _ in intervals) if scene_stage.get("status") == "completed" else []
    max_gap = min(EPISODE_MAX_GAP, max(0.4, 2.5 * sample_step))
    groups = []
    for detection in detections:
        timestamp = detection["timestamp"]
        if not groups:
            groups.append([detection])
            continue
        group = groups[-1]
        previous = group[-1]
        if (
            timestamp - previous["timestamp"] > max_gap
            or timestamp - group[0]["timestamp"] > EPISODE_MAX_DURATION
            or bisect_right(cuts, timestamp) != bisect_right(cuts, previous["timestamp"])
            or detection["sample_index"] - previous["sample_index"] > 1
        ):
            groups.append([detection])
        else:
            group.append(detection)

    episodes = []
    offset = 0
    for group in groups:
        counts = Counter(item["geometry"]["image_geometry"]["bend_class"] for item in group)
        dominant, support = counts.most_common(1)[0]
        classification = dominant if support >= 2 and support / len(group) >= 0.6 else "uncertain"
        references = {0, len(group) - 1}
        references.add(max(range(len(group)), key=lambda i: (
            bool(group[i]["context"]),
            group[i]["geometry"]["evidence_source"] == "segformer",
            group[i]["geometry"]["confidence"],
        )))
        # По одному примеру каждого вида изгиба помимо первого/последнего кадра.
        for bend in counts:
            references.add(next(i for i, item in enumerate(group)
                                if item["geometry"]["image_geometry"]["bend_class"] == bend))
        clues = {}
        for item in group:
            for obj in item["context"]:
                key = obj["label"], obj["image_side"]
                before = clues.get(key)
                if before is None or before["model_score"] < obj["model_score"]:
                    clues[key] = {**obj, "timestamp": item["timestamp"]}
        episodes.append({
            "id": f"road-{len(episodes) + 1:04d}",
            "start": group[0]["timestamp"], "end": group[-1]["timestamp"],
            "frame_count": len(group), "segment_offset": offset,
            "segment_end_index": offset + len(group),  # исключающая правая граница
            "bend_class": classification, "bend_label": BEND_LABELS[classification],
            "bend_counts": dict(counts),
            "reference_frames": [
                {"timestamp": group[i]["timestamp"], "artifact": group[i]["artifact"],
                 "segment_index": offset + i}
                for i in sorted(references)
            ],
            "context_clues": sorted(clues.values(), key=lambda item: -item["model_score"])[:6],
            "segformer_frames": sum(item["geometry"]["evidence_source"] == "segformer" for item in group),
            "requires_review": True, "map_match_ready": False,
        })
        offset += len(group)
    return episodes


def _heuristic_road_ok(
    geometry: dict,
    metrics: dict | None,
) -> bool:
    """
    Запасная проверка без семантической модели.

    Линии сами по себе слишком часто приходят от зданий,
    деревьев и приборной панели. Поэтому нужны и разметка,
    и признаки асфальта в нижней части кадра.
    """

    if not metrics:
        return False

    markings = geometry.get("markings") or {}

    marking_share = (
        float(markings.get("white") or 0)
        + float(markings.get("yellow") or 0)
    )

    if marking_share < 1.0:
        return False

    if geometry.get("vanishing_ratio") is None:
        return False

    if float(geometry.get("confidence") or 0) < 0.6:
        return False

    asphalt = float(metrics.get("asphalt") or 0)
    gray_lower = float(metrics.get("gray_lower") or 0)
    smooth_lower = float(metrics.get("smooth_lower") or 0)
    vegetation = float(metrics.get("vegetation") or 0)

    if vegetation > 35:
        return False

    return (
        asphalt >= 8.0
        and gray_lower >= 20.0
        and smooth_lower >= 20.0
    )


def _build_observations(
    detections: list[dict],
    summary: dict,
) -> list[dict]:
    """
    Складывает все кадры с дорогой в одно наблюдение-сводку.

    Список сегментов хранит таймкод каждого кадра, поэтому
    карточка занимает одну строку интерфейса, а переходы
    к отдельным кадрам остаются доступны.
    """

    if not detections:
        return []

    segments = []

    for detection in detections:
        geometry = detection["geometry"]

        segments.append({
            "start": detection["timestamp"],
            "end": detection["timestamp"],
            "text": _geometry_text(geometry),
            "artifact": detection["artifact"],
            "direction": geometry["direction"],
            "image_geometry": geometry["image_geometry"],
            "width_label": geometry["width_label"],
            "markings": geometry["markings"],
            "confidence": geometry["confidence"],
            "evidence_source": geometry.get(
                "evidence_source"
            ),
            "semantic_road_percent": geometry.get(
                "semantic_road_percent"
            ),
        })

    widths = Counter(
        segment["width_label"]
        for segment in segments
    )

    width_label = widths.most_common(1)[0][0]

    evidence_sources = Counter(
        segment["evidence_source"]
        for segment in segments
        if segment["evidence_source"]
    )

    text = (
        f"Дорога: {summary['direction']}; "
        f"{width_label}; кадров с признаками дороги: "
        f"{len(segments)} из {summary['sampled_frames']}."
    )

    if evidence_sources:
        source_names = {
            "segformer": "семантическая маска",
            "heuristic": "визуальная проверка",
        }

        text += " Основание: " + ", ".join(
            f"{source_names.get(name, name)} "
            f"({count} кадр.)"
            for name, count in evidence_sources.items()
        ) + "."

    return [
        observation(
            source="road_geometry",
            start=segments[0]["start"],
            end=segments[-1]["end"],
            text=text,
            extractor="opencv-hough-road-geometry",
            data={
                "kind": "road_geometry_summary",
                "segment_count": len(segments),
                "segments": segments,
                "summary": summary,
                "requires_review": True,
                "map_match_ready": False,
                "time_is_approximate": True,
            },
        )
    ]
