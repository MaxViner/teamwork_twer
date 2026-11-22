"""Геосцены: проверяемые утверждения + кадры, без выдуманных координат.

Динамический анализ поверх текущих результатов (включая ручные правки).
Геосцена — окно речи, а не доказанная физическая локация. Модель
«building» не способна установить «усадьба», а «near» не задаёт метры.
"""

from __future__ import annotations

import math

from app.services.geoInspectService.geo_claims import extract_geo_claims
from app.services.mapService.map_query import generate_map_queries

SCHEMA_VERSION = 1
WINDOW_BEFORE = 15.0
WINDOW_AFTER = 20.0
MAX_FRAME_REFS = 5
MAX_SCENES = 12
MAP_LIMITS = [
    "Сцены сгруппированы по времени; разные сцены не считаются одной локацией.",
    "'Рядом' в речи не определяет расстояние, направление или сторону света.",
    "Класс объекта или близость кадра к реплике не подтверждают личность здания.",
    "Число домов на исторической карте и историческое название не проверены.",
    "Координаты камеры, взаимная ориентация объектов и масштаб неизвестны.",
]


def _records(value):
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _num(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _result(stages, key):
    stage = stages.get(key) if isinstance(stages, dict) else None
    if not isinstance(stage, dict) or stage.get("status") not in ("completed", "partial"):
        return {}
    return stage.get("result") if isinstance(stage.get("result"), dict) else {}


def _visual_frames(stages):
    """Deduplicate frames; exclude source observations rejected by user."""
    by_time = {}
    for stage_name in ("ocr", "scene_objects", "landmarks"):
        stage = stages.get(stage_name) or {}
        if not isinstance(stage, dict) or stage.get("status") not in ("completed", "partial"):
            continue
        if stage_name != "ocr" and any(
            isinstance(item, dict) and item.get("review") == "rejected"
            for item in _records(stage.get("observations"))
        ):
            continue
        for frame in _records(_result(stages, stage_name).get("frames")):
            t = _num(frame.get("timestamp"))
            if t is None:
                continue
            artifact = frame.get("artifact")
            if not isinstance(artifact, str) or not artifact.startswith("runs/"):
                continue
            key = round(t, 3)
            entry = by_time.setdefault(key, {"timestamp": t, "artifact": artifact,
                                             "visual_candidates": []})
            for obj in _records(frame.get("objects") or frame.get("landmarks")):
                label = obj.get("label")
                if label not in {"building", "house", "church", "temple", "river", "water",
                                 "road", "bridge", "tower", "column", "wall", "tree"}:
                    continue
                confidence = _num(obj.get("confidence"))
                if stage_name == "scene_objects" and _result(stages, stage_name).get("method") != "segformer":
                    continue
                entry["visual_candidates"].append({
                    "label": label, "model_score": confidence,
                    "claim": "unverified_class_label",
                })
    return sorted(by_time.values(), key=lambda item: item["timestamp"])


def _anchor(claim):
    times = [t for t in (_num(s.get("start")) for s in _records(claim.get("support")))
             if t is not None]
    return min(times) if times else None


def _scene_seed(claim):
    return claim.get("subject") in ("manor", "settlement") or claim.get("predicate") in (
        "near_according_to_speaker", "possibly_near_according_to_speaker",
        "co_mentioned_in_utterance",
    )


def _scene_frames(frames, start, end, anchor):
    nearby = [f for f in frames if start <= f["timestamp"] <= end]
    if not nearby:
        return []
    # Preserve the first/last viewpoint and take visually informative centers.
    chosen = {0, len(nearby) - 1}
    ranked = sorted(range(len(nearby)), key=lambda i: (
        -len(nearby[i]["visual_candidates"]),
        abs(nearby[i]["timestamp"] - anchor), i,
    ))
    chosen.update(ranked[:MAX_FRAME_REFS - len(chosen)])
    return [nearby[i] for i in sorted(chosen)]


def _map_mask(claims, scene_claim_ids, region_claims):
    local = [c for c in claims if c["id"] in scene_claim_ids]
    region = next((c["value"] for c in region_claims
                   if c.get("predicate") == "mentioned_as_region"), None)
    required = []  # Until a specific place is verified there are no hard filters.
    optional = []
    if region:
        optional.append({"entity": "region", "value": region,
                         "source": "mentioned_in_video_not_scene_verified",
                         "claim_ids": [c["id"] for c in region_claims
                                       if c.get("value") == region]})
    for subject, target in (("manor", "manor_or_estate_site"),
                            ("church", "church_or_church_site"),
                            ("settlement", "former_settlement_site"),
                            ("river", "river_or_stream"),
                            ("road", "old_or_present_road")):
        ids = [c["id"] for c in local if c.get("subject") == subject]
        if ids:
            optional.append({"entity": target, "claim_ids": ids,
                             "source": "mentioned_in_video_not_map_verified"})
    count_ids = [c["id"] for c in local
                 if c.get("predicate") == "house_count_on_old_map_mentioned"]
    if count_ids:
        optional.append({"entity": "historical_house_count", "approximate": True,
                         "value": next(c["value"] for c in local if c["id"] == count_ids[0]),
                         "claim_ids": count_ids, "needs_historical_map": True})
    relations = []
    for c in local:
        if c["predicate"] in ("near_according_to_speaker", "possibly_near_according_to_speaker"):
            relations.append({"subject": c["subject"], "predicate": "near_claimed",
                              "object": c["value"], "claim_id": c["id"],
                              "distance_m": None, "azimuth_degrees": None,
                              "verification": "check_independent_georeferenced_sources"})
        elif c["predicate"] == "co_mentioned_in_utterance":
            relations.append({"subject": c["subject"], "predicate": "co_mentioned_only",
                              "object": c["value"], "claim_id": c["id"],
                              "distance_m": None, "azimuth_degrees": None})
    return {"region": region, "required_filters": required,
            "candidate_features": optional, "relations": relations,
            "geometry_type": "topological_claims_only", "metric_mask_ready": False}


def build_geo_scenes(stages: dict) -> dict:
    """Create bounded scene windows; NEVER merge disjoint locations.

    Manual edits are read on each call, not cached in the location dossier.
    """
    stages = stages if isinstance(stages, dict) else {}
    claim_data = extract_geo_claims(stages)
    claims = claim_data["claims"]
    region = [c for c in claims if c["subject"] == "region"]
    frames = _visual_frames(stages)
    seeds = [c for c in claims if _scene_seed(c) and _anchor(c) is not None]
    seeds.sort(key=_anchor)
    windows = []
    for claim in seeds:
        time = _anchor(claim)
        start, end = max(0, time - WINDOW_BEFORE), time + WINDOW_AFTER
        # Merge only overlapping windows (never the entire video by shared
        # classes). An edit with unknown time is never used to bridge scenes.
        if windows and start <= windows[-1]["end"]:
            windows[-1]["end"] = max(windows[-1]["end"], end)
            windows[-1]["anchors"].append(time)
        else:
            windows.append({"start": start, "end": end, "anchors": [time]})
    scenes = []
    for window in windows[:MAX_SCENES]:
        local = [c for c in claims
                 if c["subject"] != "region" and _anchor(c) is not None
                 and window["start"] <= _anchor(c) <= window["end"]]
        ids = list(dict.fromkeys(c["id"] for c in local))
        if not ids:
            continue
        anchor = min(window["anchors"])
        refs = _scene_frames(frames, window["start"], window["end"], anchor)
        scene = {"id": f"geo-scene-{len(scenes)+1:03d}",
                 "start": round(window["start"], 3), "end": round(window["end"], 3),
                 "kind": "temporal_search_hypothesis", "claim_ids": ids,
                 "region_claim_ids": [c["id"] for c in region],
                 "frame_candidates": refs,
                 "frame_relation": "temporal_proximity_only",
                 "church_visually_confirmed": False,
                 "manor_visually_confirmed": False,
                 "map_query_mask": _map_mask(claims, ids, region),
                 "limits": ["Кадр рядом с репликой не доказывает, что объект виден на кадре.",
                            "Несколько кадров не подтверждают взаимное положение объектов."]}
        scenes.append(scene)
    payload = {"schema_version": SCHEMA_VERSION, "status": "hypotheses_not_geolocation",
               "claims": claims, "scenes": scenes,
               "unlocated_claim_ids": [c["id"] for c in claims if _anchor(c) is None],
               "limits": MAP_LIMITS}
    payload["map_queries"] = generate_map_queries(payload)
    return payload
