"""Визуальные кандидаты для геосцен, без вымышленных координат.

Использование: verify_scene_visuals(job_folder, stages, build_geo_scenes(stages)).
Вызывается поверх законченных этапов, не скачивает модели. Сопоставляет
ТОЛЬКО рамки зданий из SegFormer; совпадение не доказывает личность усадьбы,
а размер/положение рамок не превращаются в метры или стороны света.
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

BUILDING_LABELS = {"building", "house", "church", "temple"}
MIN_SCORE = 0.65
MIN_AREA = 1.0
MAX_IMAGES_PER_SCENE = 16
MAX_MATCHES_PER_SCENE = 5
MIN_INLIERS = 20
MIN_INLIER_RATIO = 0.50


def _rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _artifact(folder, value):
    if not isinstance(value, str) or not value.startswith("runs/"):
        return None
    parts = value.split("/")
    if any(not part or part in (".", "..") or "\\" in part for part in parts):
        return None
    root = Path(folder).resolve()
    path = root.joinpath(*parts).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path if path.is_file() else None


def _box(value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    coords = [_number(x) for x in value]
    if any(x is None or not 0 <= x <= 1 for x in coords):
        return None
    x1, y1, x2, y2 = coords
    if x2 - x1 < .03 or y2 - y1 < .03:
        return None
    return coords


def _candidates(stages):
    """Never reinterpret heuristic-fallback classes as model detections."""
    stage = (stages.get("scene_objects") or {}) if isinstance(stages, dict) else {}
    if stage.get("status") not in ("completed", "partial"):
        return []
    if any(row.get("review") == "rejected" for row in _rows(stage.get("observations"))):
        return []
    result = stage.get("result") or {}
    if not isinstance(result, dict) or result.get("method") != "segformer":
        return []
    found = []
    for frame in _rows(result.get("frames")):
        t = _number(frame.get("timestamp"))
        artifact = frame.get("artifact")
        if t is None or t < 0 or not isinstance(artifact, str):
            continue
        for obj in _rows(frame.get("objects")):
            label = obj.get("label")
            score = _number(obj.get("confidence"))
            area = _number(obj.get("area_percent"))
            bbox = _box(obj.get("bbox"))
            if (label in BUILDING_LABELS and score is not None and score >= MIN_SCORE
                    and area is not None and area >= MIN_AREA and bbox):
                found.append({"timestamp": t, "artifact": artifact, "label": label,
                              "model_score": round(score, 3), "bbox": bbox,
                              "area_percent": area, "status": "model_class_candidate"})
    return found


def _crop(path, box):
    raw = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE) if raw.size else None
    if image is None:
        return None
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    # No extra margin: keypoints in trees around a house are not evidence
    # that the house itself is the same.
    return image[max(0, int(y1 * height)):min(height, math.ceil(y2 * height)),
                 max(0, int(x1 * width)):min(width, math.ceil(x2 * width))]


def _features(path, box, orb):
    crop = _crop(path, box)
    if crop is None or min(crop.shape[:2]) < 45:
        return None
    keypoints, descriptors = orb.detectAndCompute(crop, None)
    if descriptors is None or len(keypoints) < MIN_INLIERS or len(descriptors) < MIN_INLIERS:
        return None
    return keypoints, descriptors


def _compare(first, second):
    """Symmetric Hamming matches + RANSAC in crop coordinates.

    Same labels or shared greenery are insufficient. This establishes only
    a *candidate* overlapping facade, never world geometry or identity.
    """
    ka, da = first
    kb, db = second
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(matcher.match(da, db), key=lambda item: item.distance)
    if len(matches) < MIN_INLIERS:
        return None
    best = [m for m in matches if m.distance <= 60][:120]
    if len(best) < MIN_INLIERS:
        return None
    left = np.float32([ka[m.queryIdx].pt for m in best]).reshape(-1, 1, 2)
    right = np.float32([kb[m.trainIdx].pt for m in best]).reshape(-1, 1, 2)
    transform, inlier_mask = cv2.findHomography(left, right, cv2.RANSAC, 3.0)
    if transform is None or inlier_mask is None:
        return None
    inliers = int(inlier_mask.sum())
    ratio = inliers / len(best)
    if inliers < MIN_INLIERS or ratio < MIN_INLIER_RATIO:
        return None
    in_left = left[inlier_mask.ravel() == 1, 0]
    if len(in_left) < 3 or np.linalg.matrix_rank(np.cov(in_left.T)) < 2:
        return None
    return {"inliers": inliers, "inlier_ratio": round(ratio, 3),
            "method": "ORB_crosscheck_RANSAC_on_model_building_boxes",
            "status": "candidate_shared_facade_not_identity"}


def verify_scene_visuals(job_folder, stages, geo_scene):
    """Assess each timed geo scene independently, bounded to 16 crops.

    If a candidate is missing, say 'not established', not 'absent'.
    Caption 'manor' and 'church' remain speech claims until independently
    verified. No geolocation, bearing, or physical distance is inferred.
    """
    scenes = _rows((geo_scene or {}).get("scenes"))
    candidates = _candidates(stages)
    orb = cv2.ORB_create(nfeatures=1200)
    outcome = []
    for scene in scenes:
        start, end = _number(scene.get("start")), _number(scene.get("end"))
        if start is None or end is None or end < start:
            continue
        subset = [entry for entry in candidates if start <= entry["timestamp"] <= end]
        subset.sort(key=lambda item: (-item["model_score"], item["timestamp"]))
        subset = subset[:MAX_IMAGES_PER_SCENE]
        readable = []
        loaded = []
        for item in subset:
            path = _artifact(job_folder, item["artifact"])
            if path is None:
                continue
            evidence = {**item}
            readable.append(evidence)
            try:
                feature = _features(path, item["bbox"], orb)
            except (OSError, cv2.error, ValueError):
                feature = None
            if feature is not None:
                loaded.append((evidence, feature))
        pairs = []
        for i, (left, a) in enumerate(loaded):
            for right, b in loaded[i + 1:]:
                if left["artifact"] == right["artifact"]:
                    continue
                if (left["label"] in {"church", "temple"}) != (right["label"] in {"church", "temple"}):
                    continue
                try:
                    comparison = _compare(a, b)
                except (cv2.error, ValueError):
                    comparison = None
                if comparison:
                    pairs.append({"first": {"timestamp": left["timestamp"],
                                            "artifact": left["artifact"], "bbox": left["bbox"]},
                                  "second": {"timestamp": right["timestamp"],
                                             "artifact": right["artifact"], "bbox": right["bbox"]},
                                  **comparison})
        pairs.sort(key=lambda pair: (-pair["inliers"], -pair["inlier_ratio"]))
        outcome.append({"scene_id": scene.get("id"), "frames_examined": len(readable),
                        "candidates": readable, "possible_shared_facades": pairs[:MAX_MATCHES_PER_SCENE],
                        "manor_visually_verified": False, "church_visually_verified": False,
                        "relation_visually_verified": False,
                        "note": ("Метки классов модели и совпадение локальных признаков внутри рамок — "
                                 "кандидаты для ручной сверки; назначение здания и соседство с церковью "
                                 "не подтверждены. Отсутствие метки не означает отсутствия объекта.")})
    return {"schema_version": 1, "method": "segformer_boxes_and_orb_optional",
            "scenes": outcome, "metric_mask_ready": False,
            "note": "Без сопоставления с геопривязанными источниками координаты не выводятся."}
