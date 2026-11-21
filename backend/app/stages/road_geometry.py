"""
Геометрия дороги.

Находит дорожный коридор и его границы через OpenCV, оценивает
линию схода, направление, изгиб, ширину и разметку.

Важное отличие от покадрового анализа: дорога может быть видна
лишь частично. Поэтому наблюдения с соседних кадров связываются
в общую картину: если на одном кадре видна только левая граница,
на следующем — только правая, а ещё через кадр — центральная
разметка, они складываются в один дорожный участок.

Перед геометрией проверяется семантическая маска: если модель
не видит дорогу, тропинку или мост, линии от зданий, деревьев
и приборной панели отбрасываются.

Результат — не координаты и не маршрут, а геометрическая
сигнатура участка для последующего сопоставления с картой.
"""


import math
from collections import Counter
from pathlib import Path


import cv2
import numpy as np


from app.errors import SkipStage
from app.media.frames import analysis_frame_count, stage_frames
from app.observations import observation


ROAD_SEMANTIC_LABELS = {"road", "path", "bridge"}
SEMANTIC_ROAD_MIN_PERCENT = 1.0
EVIDENCE_TOLERANCE_SECONDS = 0.2
CONTEXT_TOLERANCE_SECONDS = 0.75


MIN_TRACK_FRAMES = 2
MAX_TRACK_GAP_SECONDS = 1.5
HEADING_TOLERANCE_DEG = 22.0
BOTTOM_SHIFT_TOLERANCE = 0.22
CURVATURE_TOLERANCE = 0.035

MIN_BOUNDARY_LINES = 2
MIN_MARKING_PERCENT = 1.0

STRAIGHT_MAX_CURVATURE = 0.012
GENTLE_MAX_CURVATURE = 0.035
MODERATE_MAX_CURVATURE = 0.080

JUNCTION_HEADING_SPREAD_DEG = 55.0
JUNCTION_MIN_FRAMES = 3


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
        count=analysis_frame_count(options),
        prefix="road",
    )


    if not frames:
        raise SkipStage(
            "Нет кадров для анализа геометрии дороги."
        )


    road_evidence = _scene_road_evidence(stages)
    visual_metrics = _visual_metrics(stages)
    scene_context = _scene_context(stages)


    tracker = RoadCorridorTracker()
    detections = []
    errors = []

    rejected_without_road = 0
    rejected_weak = 0
    partial_frames = 0


    for index, frame in enumerate(frames):
        progress(
            (index + 1) / len(frames) * 100,
            f"Анализ дороги: кадр {index + 1}/{len(frames)}",
        )


        try:
            image = _load_image(frame["path"])


            if image is None:
                continue


            timestamp = float(frame["timestamp"])


            corridor = detect_road_corridor(
                image,
                previous=tracker.last_corridor(),
            )


            if corridor is None:
                continue


            evidence = _nearest_evidence(
                road_evidence,
                timestamp,
            )


            # Семантическая маска — основной фильтр.
            # Если дороги нет, линии от фасадов, деревьев
            # и приборной панели не должны стать дорогой.
            if road_evidence is not None and (
                evidence is None
                or evidence < SEMANTIC_ROAD_MIN_PERCENT
            ):
                rejected_without_road += 1
                tracker.close_current()
                continue


            if evidence is None:
                metrics = _nearest_evidence(
                    visual_metrics,
                    timestamp,
                )


                if not _heuristic_road_ok(
                    corridor,
                    metrics,
                ):
                    rejected_weak += 1
                    continue


                evidence_source = "heuristic"
                semantic_road_percent = None


            else:
                evidence_source = "segformer"
                semantic_road_percent = round(
                    float(evidence),
                    2,
                )


            corridor["timestamp"] = round(timestamp, 3)
            corridor["evidence_source"] = evidence_source
            corridor["semantic_road_percent"] = (
                semantic_road_percent
            )
            corridor["surroundings"] = _nearest_objects(
                scene_context,
                timestamp,
            )


            if not corridor.get("both_sides_visible"):
                partial_frames += 1


            tracker.update(timestamp, corridor)


            detections.append({
                "timestamp": round(timestamp, 3),
                "artifact": frame["artifact"],
                "corridor": corridor,
            })


        except Exception as error:
            errors.append({
                "timestamp": frame.get("timestamp"),
                "error": str(error)[:1000],
            })


    tracker.close_current()


    segments = tracker.segments
    summary = _summarize(
        segments,
        len(frames),
        partial_frames,
    )


    observations = _build_observations(
        detections,
        segments,
        summary,
    )


    progress(100, "Анализ геометрии дороги завершён")


    note = (
        "Оценены направление, изгиб и ширина видимого "
        "дорожного коридора, разметка и объекты рядом. "
        "Это не координаты, не маршрут и не подтверждённое "
        "местоположение."
    )


    if not observations:
        note = (
            "На выбранных кадрах дорога не обнаружена "
            "или её геометрия недостаточно надёжна."
        )


        if rejected_without_road:
            note += (
                " Семантическая маска не подтвердила дорогу "
                f"на {rejected_without_road} кадрах."
            )


    elif summary.get("weak_support"):
        note = (
            "Дорожный коридор найден лишь на части кадров "
            "или геометрия противоречива. Это слабое "
            "основание, его нельзя считать подтверждённой "
            "дорогой."
        )


    return {
        "summary": summary,
        "observations": observations,
        "errors": errors,
        "sampled_frames": len(frames),
        "detected_frames": len(detections),
        "rejected_without_road": rejected_without_road,
        "rejected_weak": rejected_weak,
        "partial_visibility_frames": partial_frames,
        "note": note,
    }


def analyse_road(image) -> dict | None:
    """
    Обратная совместимость: анализ одного кадра.

    Для геолокации предпочтительнее использовать
    extract_road_geometry(): она связывает частичные
    наблюдения с соседних кадров в общую картину.
    """


    corridor = detect_road_corridor(image, None)


    if corridor is None:
        return None


    return {
        "direction": corridor["turn_direction"],
        "curve_label": corridor["curve_label"],
        "curvature": corridor["curvature"],
        "width_ratio": corridor["width_ratio"],
        "width_label": corridor["width_label"],
        "vanishing_ratio": corridor["vanishing_ratio"],
        "markings": corridor["markings"],
        "confidence": corridor["confidence"],
    }


def detect_road_corridor(
    image,
    previous: dict | None = None,
) -> dict | None:
    """
    Находит дорожный коридор на одном кадре.

    Коридор может быть виден частично:
    - только левая граница;
    - только правая граница;
    - только разметка;
    - узкая полоса асфальта между объектами.

    previous помогает сузить область поиска, если дорога
    уже была найдена на предыдущем кадре.
    """


    height, width = image.shape[:2]


    edges = _edge_image(image)
    lines = _hough_lines(
        edges,
        previous,
        height,
        width,
    )


    if lines is None or not len(lines):
        return None


    line_items = _prepare_lines(
        lines,
        height,
        width,
    )


    if not line_items:
        return None


    vanishing_point = _estimate_vanishing_point(
        line_items,
        width,
        height,
    )


    left_items, right_items = _split_boundary_lines(
        line_items,
        vanishing_point,
        width,
    )


    left_fit = _fit_boundary(left_items)
    right_fit = _fit_boundary(right_items)


    if left_fit is None and right_fit is None:
        return None


    corridor = _corridor_metrics(
        image=image,
        left_fit=left_fit,
        right_fit=right_fit,
        left_items=left_items,
        right_items=right_items,
        vanishing_point=vanishing_point,
        height=height,
        width=width,
        previous=previous,
    )


    if corridor is None:
        return None


    return corridor


def _load_image(path: Path):
    try:
        return cv2.imdecode(
            np.fromfile(
                str(path),
                dtype=np.uint8,
            ),
            cv2.IMREAD_COLOR,
        )


    except Exception:
        return None


def _edge_image(image):
    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY,
    )


    blurred = cv2.GaussianBlur(
        gray,
        (5, 5),
        0,
    )


    return cv2.Canny(
        blurred,
        45,
        140,
    )


def _hough_lines(
    edges,
    previous: dict | None,
    height: int,
    width: int,
):
    mask = np.zeros_like(edges)


    if previous:
        polygon = _previous_corridor_polygon(
            previous,
            height,
            width,
        )


    else:
        polygon = np.array([[
            (
                int(width * 0.02),
                int(height * 0.98),
            ),
            (
                int(width * 0.40),
                int(height * 0.52),
            ),
            (
                int(width * 0.60),
                int(height * 0.52),
            ),
            (
                int(width * 0.98),
                int(height * 0.98),
            ),
        ]], dtype=np.int32)


    cv2.fillPoly(mask, polygon, 255)
    edges = cv2.bitwise_and(edges, mask)


    return cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=30,
        minLineLength=max(
            35,
            int(height * 0.10),
        ),
        maxLineGap=45,
    )


def _previous_corridor_polygon(
    previous: dict,
    height: int,
    width: int,
) -> np.ndarray:
    """
    Расширяет предыдущий коридор, чтобы дорога могла
    смещаться в кадре из-за движения камеры.
    """


    left = previous.get("left_bottom_x")
    right = previous.get("right_bottom_x")


    if left is None and right is None:
        return _default_polygon(height, width)


    if left is None:
        left = right - width * 0.25


    if right is None:
        right = left + width * 0.25


    left = max(0.0, left - width * 0.18)
    right = min(
        float(width - 1),
        right + width * 0.18,
    )


    vanishing = previous.get("vanishing_point")


    if vanishing:
        top_left_x = vanishing[0] - width * 0.18
        top_right_x = vanishing[0] + width * 0.18


    else:
        center = (left + right) / 2
        top_left_x = center - width * 0.16
        top_right_x = center + width * 0.16


    top_y = height * 0.48


    return np.array([[
        (int(left), int(height * 0.98)),
        (
            int(max(0, top_left_x)),
            int(top_y),
        ),
        (
            int(min(width - 1, top_right_x)),
            int(top_y),
        ),
        (int(right), int(height * 0.98)),
    ]], dtype=np.int32)


def _default_polygon(
    height: int,
    width: int,
) -> np.ndarray:
    return np.array([[
        (
            int(width * 0.02),
            int(height * 0.98),
        ),
        (
            int(width * 0.40),
            int(height * 0.52),
        ),
        (
            int(width * 0.60),
            int(height * 0.52),
        ),
        (
            int(width * 0.98),
            int(height * 0.98),
        ),
    ]], dtype=np.int32)


def _prepare_lines(
    lines,
    height: int,
    width: int,
) -> list[dict]:
    items = []


    for raw in np.asarray(lines).reshape(-1, 4):
        x1, y1, x2, y2 = (
            int(value) for value in raw
        )


        if y1 == y2:
            continue


        if abs(x2 - x1) < 1:
            continue


        length = math.hypot(
            x2 - x1,
            y2 - y1,
        )


        if length < max(
            30,
            height * 0.08,
        ):
            continue


        slope = (y2 - y1) / (x2 - x1)


        if abs(slope) < 0.18:
            continue


        items.append({
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "slope": slope,
            "length": length,
            "mid_x": (x1 + x2) / 2,
            "mid_y": (y1 + y2) / 2,
        })


    return items


def _estimate_vanishing_point(
    line_items: list[dict],
    width: int,
    height: int,
):
    """
    Ищет общую точку схода почти параллельных линий.

    Это не точная калибровка камеры, а устойчивая
    геометрическая опора для направления дороги.
    """


    intersections = []


    for i in range(len(line_items)):
        for j in range(i + 1, len(line_items)):
            point = _line_intersection(
                line_items[i],
                line_items[j],
            )


            if point is None:
                continue


            x, y = point


            if (
                -width <= x <= 2 * width
                and -height <= y <= 2 * height
            ):
                intersections.append((x, y))


    if len(intersections) < 6:
        return None


    points = np.asarray(
        intersections,
        dtype=np.float64,
    )


    center = points.mean(axis=0)
    distances = np.linalg.norm(
        points - center,
        axis=1,
    )


    keep = distances <= np.percentile(
        distances,
        70,
    )


    if keep.sum() < 4:
        return None


    x, y = points[keep].mean(axis=0)


    return (
        float(x),
        float(y),
    )


def _line_intersection(
    first: dict,
    second: dict,
):
    x1, y1, x2, y2 = (
        first["x1"],
        first["y1"],
        first["x2"],
        first["y2"],
    )


    x3, y3, x4, y4 = (
        second["x1"],
        second["y1"],
        second["x2"],
        second["y2"],
    )


    denominator = (
        (x1 - x2) * (y3 - y4)
        - (y1 - y2) * (x3 - x4)
    )


    if abs(denominator) < 1e-9:
        return None


    px = (
        (x1 * y2 - y1 * x2) * (x3 - x4)
        - (x1 - x2) * (x3 * y4 - y3 * x4)
    ) / denominator


    py = (
        (x1 * y2 - y1 * x2) * (y3 - y4)
        - (y1 - y2) * (x3 * y4 - y3 * x4)
    ) / denominator


    return (
        float(px),
        float(py),
    )


def _split_boundary_lines(
    line_items: list[dict],
    vanishing_point,
    width: int,
) -> tuple[list[dict], list[dict]]:
    """
    Делит линии на левую и правую границы коридора.

    Если есть точка схода, сторона определяется по
    положению линии относительно луча из нижней части
    кадра в точку схода. Если точки схода нет — по
    положению середины линии.
    """


    left = []
    right = []


    center_x = width / 2


    for item in line_items:
        if vanishing_point:
            side = _side_relative_to_vanishing(
                item,
                vanishing_point,
                width,
            )


        else:
            side = (
                "left"
                if item["mid_x"] < center_x
                else "right"
            )


        if side == "left":
            left.append(item)


        elif side == "right":
            right.append(item)


    return left, right


def _side_relative_to_vanishing(
    item: dict,
    vanishing_point: tuple[float, float],
    width: int,
) -> str | None:
    vx, vy = vanishing_point


    bottom_x = _line_x_at_y(
        item,
        0.95,
    )


    if bottom_x is None:
        return None


    if abs(bottom_x - vx) < width * 0.03:
        return None


    return (
        "left"
        if bottom_x < vx
        else "right"
    )


def _line_x_at_y(
    item: dict,
    y_ratio: float,
):
    x1, y1, x2, y2 = (
        item["x1"],
        item["y1"],
        item["x2"],
        item["y2"],
    )


    if y1 == y2:
        return None


    t = (y_ratio - y1) / (y2 - y1)


    if t < 0 or t > 1:
        return None


    return x1 + t * (x2 - x1)


def _fit_boundary(items: list[dict]):
    """
    Аппроксимирует границу дороги полиномом x(y).

    Используются середины линий, взвешенные по длине.
    Даже двух линий достаточно, если они согласованы.
    """


    if len(items) < MIN_BOUNDARY_LINES:
        return None


    ys = []
    xs = []
    weights = []


    for item in items:
        ys.append(item["mid_y"])
        xs.append(item["mid_x"])
        weights.append(item["length"])


    ys = np.asarray(ys, dtype=np.float64)
    xs = np.asarray(xs, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)


    weights = weights / max(
        weights.sum(),
        1e-9,
    )


    try:
        return np.polyfit(
            ys,
            xs,
            2,
            w=np.sqrt(weights),
        )


    except Exception:
        return None


def _corridor_metrics(
    image,
    left_fit,
    right_fit,
    left_items,
    right_items,
    vanishing_point,
    height: int,
    width: int,
    previous: dict | None,
) -> dict | None:
    both_sides = (
        left_fit is not None
        and right_fit is not None
    )


    if not both_sides and not (
        left_fit is not None
        or right_fit is not None
    ):
        return None


    bottom_y = height - 1
    near_y = height * 0.88
    far_y = height * 0.60


    left_bottom = _poly_x(
        left_fit,
        bottom_y,
    )
    right_bottom = _poly_x(
        right_fit,
        bottom_y,
    )


    left_near = _poly_x(
        left_fit,
        near_y,
    )
    right_near = _poly_x(
        right_fit,
        near_y,
    )


    left_far = _poly_x(
        left_fit,
        far_y,
    )
    right_far = _poly_x(
        right_fit,
        far_y,
    )


    if both_sides and (
        left_bottom is None
        or right_bottom is None
        or right_bottom <= left_bottom
    ):
        return None


    center_bottom = _center_x(
        left_bottom,
        right_bottom,
    )
    center_near = _center_x(
        left_near,
        right_near,
    )
    center_far = _center_x(
        left_far,
        right_far,
    )


    heading_deg = _heading_deg(
        center_bottom,
        center_near,
        height,
    )


    if heading_deg is None:
        heading_deg = _heading_from_side(
            left_bottom,
            left_near,
            right_bottom,
            right_near,
            height,
        )


    if heading_deg is None:
        return None


    curvature, turn_direction = _turn_metrics(
        center_bottom,
        center_near,
        center_far,
    )


    if curvature is None:
        curvature, turn_direction = _turn_metrics(
            left_bottom,
            left_near,
            left_far,
        )


    if curvature is None:
        curvature, turn_direction = _turn_metrics(
            right_bottom,
            right_near,
            right_far,
        )


    if curvature is None:
        return None


    width_ratio = None
    width_meters = None


    if both_sides:
        width_ratio = (
            right_bottom - left_bottom
        ) / width


        width_meters = _estimate_width_meters(
            width_ratio,
            vanishing_point,
            height,
        )


    markings = _marking_ratio(
        image=image,
        left_fit=left_fit,
        right_fit=right_fit,
        height=height,
        width=width,
    )


    confidence = _corridor_confidence(
        left_items=left_items,
        right_items=right_items,
        both_sides=both_sides,
        markings=markings,
        vanishing_point=vanishing_point,
        curvature=curvature,
    )


    curve_label = _curve_label(
        curvature,
        turn_direction,
    )


    width_label = _width_label(
        width_ratio,
        both_sides,
    )


    vanishing_ratio = None


    if vanishing_point:
        vanishing_ratio = max(
            0.0,
            min(
                1.0,
                vanishing_point[1] / height,
            ),
        )


    return {
        "left_visible": left_fit is not None,
        "right_visible": right_fit is not None,
        "both_sides_visible": both_sides,
        "left_bottom_x": left_bottom,
        "right_bottom_x": right_bottom,
        "center_bottom_x": center_bottom,
        "heading_deg": round(heading_deg, 2),
        "curvature": round(float(curvature), 6),
        "turn_direction": turn_direction,
        "curve_label": curve_label,
        "width_ratio": (
            round(float(width_ratio), 3)
            if width_ratio is not None
            else None
        ),
        "width_meters_estimate": width_meters,
        "width_label": width_label,
        "vanishing_point": vanishing_point,
        "vanishing_ratio": (
            round(float(vanishing_ratio), 3)
            if vanishing_ratio is not None
            else None
        ),
        "markings": markings,
        "confidence": round(float(confidence), 2),
        "left_line_count": len(left_items),
        "right_line_count": len(right_items),
    }


def _poly_x(fit, y: float):
    if fit is None:
        return None


    try:
        return float(np.polyval(fit, y))


    except Exception:
        return None


def _center_x(left, right):
    if left is not None and right is not None:
        return (left + right) / 2


    return None


def _heading_deg(
    bottom_x,
    near_x,
    height: int,
):
    if bottom_x is None or near_x is None:
        return None


    dx = near_x - bottom_x
    dy = abs(near_y - bottom_y) if False else height * 0.28


    if dy <= 0:
        return None


    return math.degrees(
        math.atan2(dx, dy)
    )


def _heading_from_side(
    left_bottom,
    left_near,
    right_bottom,
    right_near,
    height: int,
):
    if left_bottom is not None and left_near is not None:
        return _heading_deg(
            left_bottom,
            left_near,
            height,
        )


    if right_bottom is not None and right_near is not None:
        return _heading_deg(
            right_bottom,
            right_near,
            height,
        )


    return None


def _turn_metrics(
    bottom_x,
    near_x,
    far_x,
):
    if (
        bottom_x is None
        or near_x is None
        or far_x is None
    ):
        return None, "unknown"


    # Дорога уходит от нижней части кадра вверх.
    # Если дальняя часть смещена вправо относительно
    # ближней, это поворот вправо относительно камеры.
    shift = far_x - bottom_x
    curvature = abs(shift)


    if curvature < STRAIGHT_MAX_CURVATURE:
        return curvature, "straight"


    if shift > 0:
        return curvature, "right"


    return curvature, "left"


def _estimate_width_meters(
    width_ratio: float,
    vanishing_point,
    height: int,
) -> list[float] | None:
    """
    Очень грубая оценка ширины в метрах.

    Без калибровки камеры это диапазон, а не измерение.
    Оценка основана на типичной ширине полосы 3–3.75 м.
    """


    if width_ratio is None:
        return None


    if vanishing_point is None:
        return None


    lane_count = _lane_count_estimate(width_ratio)


    if lane_count is None:
        return None


    low = lane_count * 3.0
    high = lane_count * 3.75


    return [
        round(low, 1),
        round(high, 1),
    ]


def _lane_count_estimate(width_ratio: float):
    if width_ratio < 0.18:
        return 1


    if width_ratio < 0.38:
        return 2


    if width_ratio < 0.58:
        return 3


    if width_ratio < 0.78:
        return 4


    return None


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


    for y in range(
        int(height * 0.50),
        height,
    ):
        left = _poly_x(left_fit, y)
        right = _poly_x(right_fit, y)


        if left is None and right is None:
            continue


        if left is None:
            left = right - width * 0.18


        if right is None:
            right = left + width * 0.18


        left = max(
            0,
            min(width - 1, int(left)),
        )
        right = max(
            0,
            min(width, int(right)),
        )


        if right > left:
            mask[y, left:right] = 255


    selected = mask > 0


    if not selected.any():
        return {
            "white": 0.0,
            "yellow": 0.0,
        }


    hsv = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2HSV,
    )


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


def _corridor_confidence(
    left_items,
    right_items,
    both_sides: bool,
    markings: dict,
    vanishing_point,
    curvature: float,
) -> float:
    score = 0.20


    score += 0.04 * min(
        len(left_items) + len(right_items),
        8,
    )


    if both_sides:
        score += 0.18


    if vanishing_point is not None:
        score += 0.12


    if markings.get("white", 0) > MIN_MARKING_PERCENT:
        score += 0.10


    if markings.get("yellow", 0) > MIN_MARKING_PERCENT:
        score += 0.08


    if curvature < STRAIGHT_MAX_CURVATURE:
        score += 0.05


    return min(
        0.92,
        score,
    )


def _curve_label(
    curvature: float,
    turn_direction: str,
) -> str:
    if turn_direction == "straight":
        return "прямой участок"


    if curvature < GENTLE_MAX_CURVATURE:
        return "плавный изгиб"


    if curvature < MODERATE_MAX_CURVATURE:
        return "заметный изгиб"


    return "крутой изгиб"


def _width_label(
    width_ratio,
    both_sides: bool,
) -> str:
    if not both_sides or width_ratio is None:
        return "ширина не определена: видна только часть дороги"


    if width_ratio >= 0.75:
        return "широкая дорога, возможно 3+ полосы"


    if width_ratio >= 0.35:
        return "дорога средней ширины, возможно 2 полосы"


    return "узкая дорога или одна полоса"


class RoadCorridorTracker:
    """
    Связывает частичные дорожные наблюдения с соседних
    кадров в устойчивые участки.

    Кадр с одной видимой границей не отбрасывается:
    он может продолжить уже начатый коридор или стать
    началом нового участка.
    """


    def __init__(self):
        self.segments = []
        self._current = None


    def last_corridor(self):
        if not self._current:
            return None


        frames = self._current["frames"]


        if not frames:
            return None


        return frames[-1]["corridor"]


    def update(
        self,
        timestamp: float,
        corridor: dict,
    ):
        if self._current is None:
            self._start(timestamp, corridor)
            return


        if (
            timestamp - self._current["end"]
            > MAX_TRACK_GAP_SECONDS
        ):
            self.close_current()
            self._start(timestamp, corridor)
            return


        if not self._compatible(
            self._current,
            corridor,
        ):
            self.close_current()
            self._start(timestamp, corridor)
            return


        self._extend(timestamp, corridor)


    def close_current(self):
        if not self._current:
            return


        frames = self._current["frames"]


        if len(frames) >= MIN_TRACK_FRAMES:
            self.segments.append(
                self._finalize_segment(self._current)
            )


        self._current = None


    def _start(
        self,
        timestamp: float,
        corridor: dict,
    ):
        self._current = {
            "start": timestamp,
            "end": timestamp,
            "frames": [
                {
                    "timestamp": timestamp,
                    "corridor": corridor,
                }
            ],
        }


    def _extend(
        self,
        timestamp: float,
        corridor: dict,
    ):
        self._current["end"] = timestamp
        self._current["frames"].append({
            "timestamp": timestamp,
            "corridor": corridor,
        })


    def _compatible(
        self,
        segment: dict,
        corridor: dict,
    ) -> bool:
        frames = segment["frames"]


        if not frames:
            return False


        last = frames[-1]["corridor"]


        heading_a = last.get("heading_deg")
        heading_b = corridor.get("heading_deg")


        if (
            heading_a is not None
            and heading_b is not None
            and abs(heading_a - heading_b)
            > HEADING_TOLERANCE_DEG
        ):
            return False


        if self._bottom_shift_too_large(
            last,
            corridor,
        ):
            return False


        return True


    def _bottom_shift_too_large(
        self,
        previous: dict,
        current: dict,
    ) -> bool:
        pairs = [
            (
                previous.get("left_bottom_x"),
                current.get("left_bottom_x"),
            ),
            (
                previous.get("right_bottom_x"),
                current.get("right_bottom_x"),
            ),
            (
                previous.get("center_bottom_x"),
                current.get("center_bottom_x"),
            ),
        ]


        for old, new in pairs:
            if old is None or new is None:
                continue


            if abs(new - old) > BOTTOM_SHIFT_TOLERANCE:
                return True


        return False


    def _finalize_segment(
        self,
        segment: dict,
    ) -> dict:
        frames = segment["frames"]
        corridors = [
            item["corridor"]
            for item in frames
        ]


        headings = [
            corridor["heading_deg"]
            for corridor in corridors
            if corridor.get("heading_deg") is not None
        ]


        curvatures = [
            corridor["curvature"]
            for corridor in corridors
            if corridor.get("curvature") is not None
        ]


        turn_directions = [
            corridor["turn_direction"]
            for corridor in corridors
            if corridor.get("turn_direction")
        ]


        turn_direction = Counter(
            turn_directions
        ).most_common(1)[0][0]


        width_ratios = [
            corridor["width_ratio"]
            for corridor in corridors
            if corridor.get("width_ratio") is not None
        ]


        markings = {
            "white": round(
                float(np.mean([
                    corridor["markings"]["white"]
                    for corridor in corridors
                ])),
                2,
            ),
            "yellow": round(
                float(np.mean([
                    corridor["markings"]["yellow"]
                    for corridor in corridors
                ])),
                2,
            ),
        }


        both_sides = any(
            corridor.get("both_sides_visible")
            for corridor in corridors
        )


        partial_only = all(
            not corridor.get("both_sides_visible")
            for corridor in corridors
        )


        confidence = float(np.mean([
            corridor["confidence"]
            for corridor in corridors
        ]))


        if partial_only:
            confidence *= 0.75


        if len(frames) < MIN_TRACK_FRAMES:
            confidence *= 0.65


        return {
            "start": round(segment["start"], 3),
            "end": round(segment["end"], 3),
            "frames": len(frames),
            "timestamps": [
                item["timestamp"]
                for item in frames
            ],
            "heading_deg": (
                round(float(np.median(headings)), 2)
                if headings
                else None
            ),
            "heading_std": (
                round(float(np.std(headings)), 2)
                if len(headings) > 1
                else 0.0
            ),
            "turn_direction": turn_direction,
            "mean_curvature": (
                round(float(np.mean(curvatures)), 6)
                if curvatures
                else 0.0
            ),
            "max_curvature": (
                round(float(np.max(curvatures)), 6)
                if curvatures
                else 0.0
            ),
            "curve_label": _curve_label(
                float(np.mean(curvatures))
                if curvatures
                else 0.0,
                turn_direction,
            ),
            "width_ratio": (
                round(float(np.median(width_ratios)), 3)
                if width_ratios
                else None
            ),
            "width_meters_estimate": _first_width_estimate(
                corridors
            ),
            "both_sides_visible": both_sides,
            "partial_only": partial_only,
            "markings": markings,
            "confidence": round(confidence, 2),
            "surroundings": _segment_surroundings(
                corridors
            ),
            "evidence_sources": dict(Counter(
                corridor.get("evidence_source")
                for corridor in corridors
                if corridor.get("evidence_source")
            )),
        }


def _first_width_estimate(corridors: list[dict]):
    for corridor in corridors:
        estimate = corridor.get(
            "width_meters_estimate"
        )


        if estimate:
            return estimate


    return None


def _segment_surroundings(
    corridors: list[dict],
) -> list[dict]:
    collected = {}


    for corridor in corridors:
        for item in corridor.get("surroundings") or []:
            label = (
                item.get("label_ru")
                or item.get("label")
            )


            if not label:
                continue


            entry = collected.setdefault(label, {
                "label": label,
                "frame_count": 0,
                "max_area_percent": 0.0,
            })


            entry["frame_count"] += 1
            entry["max_area_percent"] = max(
                entry["max_area_percent"],
                float(item.get("area_percent") or 0),
            )


    result = list(collected.values())


    for item in result:
        item["max_area_percent"] = round(
            item["max_area_percent"],
            1,
        )


    result.sort(
        key=lambda item: (
            -item["frame_count"],
            -item["max_area_percent"],
            item["label"],
        )
    )


    return result[:10]


def _summarize(
    segments: list[dict],
    sampled_frames: int,
    partial_frames: int,
) -> dict:
    if not segments:
        return {
            "road_detected": False,
            "weak_support": True,
            "confidence": 0.0,
            "segment_count": 0,
            "sampled_frames": sampled_frames,
            "partial_visibility_frames": partial_frames,
            "direction": "не определено",
            "total_turns": 0,
            "s_curve": False,
            "intersection_candidates": 0,
            "sequence": {
                "text": "Дорога не обнаружена.",
                "directions": [],
                "segments": [],
            },
            "surroundings": [],
        }


    turn_directions = [
        segment["turn_direction"]
        for segment in segments
    ]


    dominant = Counter(
        turn_directions
    ).most_common(1)[0][0]


    total_frames = sum(
        segment["frames"]
        for segment in segments
    )


    detection_ratio = (
        total_frames / sampled_frames
        if sampled_frames
        else 0.0
    )


    has_left = "left" in turn_directions
    has_right = "right" in turn_directions


    s_curve = has_left and has_right


    total_turns = max(
        0,
        len(
            [
                direction
                for direction in turn_directions
                if direction in ("left", "right")
            ]
        )
        - 1,
    )


    junction_candidates = _junction_candidates(
        segments
    )


    confidence = float(np.mean([
        segment["confidence"]
        for segment in segments
    ]))


    confidence *= min(
        1.0,
        detection_ratio * 1.4,
    )


    road_detected = (
        len(segments) >= 1
        and total_frames >= MIN_TRACK_FRAMES
        and detection_ratio >= 0.30
        and confidence >= 0.45
    )


    return {
        "road_detected": road_detected,
        "weak_support": not road_detected,
        "confidence": round(confidence, 2),
        "segment_count": len(segments),
        "detected_frames": total_frames,
        "sampled_frames": sampled_frames,
        "detection_ratio": round(detection_ratio, 3),
        "partial_visibility_frames": partial_frames,
        "direction": _direction_name(dominant),
        "total_turns": total_turns,
        "s_curve": s_curve,
        "intersection_candidates": junction_candidates,
        "sequence": _sequence_text(
            segments,
            s_curve,
        ),
        "surroundings": _global_surroundings(
            segments
        ),
    }


def _direction_name(direction: str) -> str:
    return {
        "left": "поворот влево",
        "right": "поворот вправо",
        "straight": "прямая дорога",
    }.get(
        direction,
        "неоднозначная геометрия дороги",
    )


def _junction_candidates(
    segments: list[dict],
) -> int:
    candidates = 0


    for segment in segments:
        if segment["frames"] < JUNCTION_MIN_FRAMES:
            continue


        if (
            segment.get("heading_std", 0.0)
            > JUNCTION_HEADING_SPREAD_DEG / 2
        ):
            candidates += 1


            continue


        if (
            segment.get("width_ratio")
            is not None
            and segment["width_ratio"] > 0.70
        ):
            candidates += 1


    return candidates


def _sequence_text(
    segments: list[dict],
    s_curve: bool,
) -> dict:
    directions = [
        _direction_name(
            segment["turn_direction"]
        )
        for segment in segments
    ]


    if s_curve:
        text = (
            "Встречаются повороты в обе стороны — "
            "возможен S-образный или комбинированный "
            "участок."
        )


    elif len(segments) > 1:
        text = (
            "Направление меняется: "
            + " → ".join(directions)
            + "."
        )


    elif directions:
        text = (
            "На доступных кадрах: "
            + directions[0].lower()
            + "."
        )


    else:
        text = (
            "Последовательность направлений "
            "не определена."
        )


    return {
        "text": text,
        "directions": directions,
        "segments": segments[:24],
    }


def _global_surroundings(
    segments: list[dict],
) -> list[dict]:
    collected = {}


    for segment in segments:
        for item in segment.get("surroundings") or []:
            label = item["label"]


            entry = collected.setdefault(label, {
                "label": label,
                "frame_count": 0,
                "max_area_percent": 0.0,
            })


            entry["frame_count"] += item["frame_count"]
            entry["max_area_percent"] = max(
                entry["max_area_percent"],
                item["max_area_percent"],
            )


    result = list(collected.values())


    result.sort(
        key=lambda item: (
            -item["frame_count"],
            -item["max_area_percent"],
            item["label"],
        )
    )


    return result[:10]


def _geometry_text(corridor: dict) -> str:
    parts = [
        "Дорога: "
        + _direction_name(
            corridor["turn_direction"]
        )
    ]


    if corridor.get("curve_label"):
        parts.append(corridor["curve_label"])


    if corridor.get("both_sides_visible"):
        parts.append("видны обе границы")


    else:
        visible = []


        if corridor.get("left_visible"):
            visible.append("левая граница")


        if corridor.get("right_visible"):
            visible.append("правая граница")


        if visible:
            parts.append(
                "частично видна: "
                + ", ".join(visible)
            )


    if corridor.get("width_label"):
        parts.append(corridor["width_label"])


    markings = corridor.get("markings") or {}


    if markings.get("white", 0) > MIN_MARKING_PERCENT:
        parts.append("белая разметка")


    if markings.get("yellow", 0) > MIN_MARKING_PERCENT:
        parts.append("жёлтая разметка")


    if corridor.get("vanishing_ratio") is not None:
        parts.append(
            "линия схода на "
            f"{corridor['vanishing_ratio'] * 100:.0f}% "
            "высоты"
        )


    surroundings = [
        item.get("label_ru") or item.get("label")
        for item in (
            corridor.get("surroundings") or []
        )[:4]
        if item.get("label_ru") or item.get("label")
    ]


    if surroundings:
        parts.append(
            "рядом: " + ", ".join(surroundings)
        )


    return "; ".join(parts) + "."


def _build_observations(
    detections: list[dict],
    segments: list[dict],
    summary: dict,
) -> list[dict]:
    if not detections or not segments:
        return []


    segment_items = []


    for segment in segments:
        segment_items.append({
            "start": segment["start"],
            "end": segment["end"],
            "text": _segment_text(segment),
            "timestamps": segment["timestamps"],
            "heading_deg": segment["heading_deg"],
            "turn_direction": segment["turn_direction"],
            "curve_label": segment["curve_label"],
            "width_ratio": segment["width_ratio"],
            "width_meters_estimate": segment[
                "width_meters_estimate"
            ],
            "markings": segment["markings"],
            "confidence": segment["confidence"],
            "surroundings": segment["surroundings"],
            "partial_only": segment["partial_only"],
            "evidence_sources": segment[
                "evidence_sources"
            ],
        })


    text = (
        f"Дорожный коридор: {summary['direction']}; "
        f"участков: {len(segments)}; "
        f"кадров с признаками дороги: "
        f"{summary['detected_frames']} "
        f"из {summary['sampled_frames']}."
    )


    if summary.get("partial_visibility_frames"):
        text += (
            " Дорога частично видна на "
            f"{summary['partial_visibility_frames']} кадрах; "
            "наблюдения сшиты в общую геометрию."
        )


    if summary.get("s_curve"):
        text += " Возможен S-образный участок."


    if summary.get("intersection_candidates"):
        text += (
            " Есть "
            f"{summary['intersection_candidates']} "
            "кандидат(ов) на перекрёсток или примыкание."
        )


    surroundings = summary.get("surroundings") or []


    if surroundings:
        text += (
            " Рядом с дорогой: "
            + ", ".join(
                f"{item['label']} "
                f"({item['frame_count']} кадр.)"
                for item in surroundings[:6]
            )
            + "."
        )


    return [
        observation(
            source="road_geometry",
            start=segment_items[0]["start"],
            end=segment_items[-1]["end"],
            text=text,
            extractor="opencv-road-corridor-tracker",
            data={
                "kind": "road_geometry_summary",
                "segment_count": len(segment_items),
                "segments": segment_items,
                "summary": summary,
                "requires_review": True,
                "map_match_ready": False,
                "time_is_approximate": True,
                "partial_road_supported": True,
            },
        )
    ]


def _segment_text(segment: dict) -> str:
    parts = [
        "Участок дороги: "
        + _direction_name(
            segment["turn_direction"]
        )
    ]


    if segment.get("curve_label"):
        parts.append(segment["curve_label"])


    if segment.get("width_label"):
        parts.append(segment["width_label"])


    if segment.get("partial_only"):
        parts.append(
            "видна только часть дорожного коридора"
        )


    markings = segment.get("markings") or {}


    if markings.get("white", 0) > MIN_MARKING_PERCENT:
        parts.append("белая разметка")


    if markings.get("yellow", 0) > MIN_MARKING_PERCENT:
        parts.append("жёлтая разметка")


    return "; ".join(parts) + "."


def _scene_road_evidence(
    stages: dict,
) -> list[tuple[float, float]] | None:
    result = stages.get("scene_objects", {}).get(
        "result"
    ) or {}


    method = result.get("method")


    if method and method != "segformer":
        return None


    frames = result.get("frames")


    if not isinstance(frames, list) or not frames:
        return None


    evidence = []


    for frame in frames:
        if not isinstance(frame, dict):
            continue


        timestamp = frame.get("timestamp")


        if timestamp is None:
            continue


        percent = 0.0


        for item in frame.get("objects", []):
            if not isinstance(item, dict):
                continue


            if item.get("label") in ROAD_SEMANTIC_LABELS:
                percent += float(
                    item.get("area_percent") or 0
                )


        evidence.append((
            float(timestamp),
            percent,
        ))


    evidence.sort(key=lambda item: item[0])


    return evidence or None


def _scene_context(
    stages: dict,
) -> list[tuple[float, list[dict]]] | None:
    result = stages.get("scene_objects", {}).get(
        "result"
    ) or {}


    frames = result.get("frames")


    if not isinstance(frames, list) or not frames:
        return None


    context = []
    skipped = {
        "road",
        "path",
        "bridge",
        "sky",
    }


    for frame in frames:
        if not isinstance(frame, dict):
            continue


        timestamp = frame.get("timestamp")


        if timestamp is None:
            continue


        objects = []


        for item in frame.get("objects") or []:
            if not isinstance(item, dict):
                continue


            if item.get("label") in skipped:
                continue


            objects.append({
                "label": item.get("label"),
                "label_ru": (
                    item.get("label_ru")
                    or item.get("label")
                ),
                "area_percent": round(
                    float(item.get("area_percent") or 0),
                    2,
                ),
            })


        objects.sort(
            key=lambda item: -item["area_percent"]
        )


        context.append((
            float(timestamp),
            objects[:5],
        ))


    context.sort(key=lambda item: item[0])


    return context or None


def _nearest_objects(
    context: list[tuple[float, list[dict]]] | None,
    timestamp: float,
) -> list[dict]:
    if not context:
        return []


    nearest = min(
        context,
        key=lambda item: abs(item[0] - timestamp),
    )


    if (
        abs(nearest[0] - timestamp)
        > CONTEXT_TOLERANCE_SECONDS
    ):
        return []


    return nearest[1]


def _visual_metrics(
    stages: dict,
) -> list[tuple[float, dict]] | None:
    result = stages.get("visual_profile", {}).get(
        "result"
    ) or {}


    frames = result.get("frames")


    if not isinstance(frames, list) or not frames:
        return None


    metrics = []


    for frame in frames:
        if not isinstance(frame, dict):
            continue


        timestamp = frame.get("timestamp")


        if timestamp is None:
            continue


        values = frame.get("metrics")


        if isinstance(values, dict):
            metrics.append((
                float(timestamp),
                values,
            ))


    metrics.sort(key=lambda item: item[0])


    return metrics or None


def _nearest_evidence(
    evidence: list[tuple[float, float]] | None,
    timestamp: float,
):
    if not evidence:
        return None


    nearest = min(
        evidence,
        key=lambda item: abs(item[0] - timestamp),
    )


    if (
        abs(nearest[0] - timestamp)
        > EVIDENCE_TOLERANCE_SECONDS
    ):
        return None


    return nearest[1]


def _heuristic_road_ok(
    corridor: dict,
    metrics: dict | None,
) -> bool:
    """
    Запасная проверка без семантической модели.

    Частичная видимость допустима, но нужны хотя бы
    разметка, линия схода и признаки асфальта.
    """


    if not metrics:
        return False


    markings = corridor.get("markings") or {}


    marking_share = (
        float(markings.get("white") or 0)
        + float(markings.get("yellow") or 0)
    )


    if marking_share < MIN_MARKING_PERCENT:
        return False


    if corridor.get("vanishing_ratio") is None:
        return False


    if float(
        corridor.get("confidence") or 0
    ) < 0.55:
        return False


    asphalt = float(metrics.get("asphalt") or 0)
    gray_lower = float(metrics.get("gray_lower") or 0)
    smooth_lower = float(
        metrics.get("smooth_lower") or 0
    )
    vegetation = float(
        metrics.get("vegetation") or 0
    )


    if vegetation > 35:
        return False


    return (
        asphalt >= 8.0
        and gray_lower >= 20.0
        and smooth_lower >= 20.0
    )