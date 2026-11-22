"""Generate a portable map-search brief from a geo-scene.

No external geocoder or map is queried. Normalized boxes remain image-space
references; this module never invents map coordinates, distances, bearings,
or confidence scores.
"""
from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1


def _rows(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _region_claims(claims: list[dict]) -> list[dict]:
    return [item for item in claims
            if item.get("subject") == "region"
            and item.get("predicate") == "mentioned_as_region"]


def _requirements(claims: list[dict]) -> list[dict]:
    specs = (
        ("settlement", "described_as", "former_or_abandoned_settlement"),
        ("manor", "mentioned", "manor_or_estate_site_mentioned"),
        ("church", "mentioned", "church_or_church_site_mentioned"),
        ("river", "mentioned", "river_or_stream_mentioned"),
        ("road", "mentioned", "road_mentioned"),
        ("historic_map", "mentioned", "historic_map_mentioned"),
        ("settlement", "house_count_on_old_map_mentioned", "historical_house_count_claim"),
        ("settlement", "house_count_mentioned", "house_count_claim_unlinked_to_map"),
    )
    output = []
    for subject, predicate, key in specs:
        matched = [item for item in claims
                   if item.get("subject") == subject and item.get("predicate") == predicate]
        if not matched:
            continue
        output.append({
            "key": key,
            "values": list(dict.fromkeys(item.get("value") for item in matched)),
            "claim_ids": [item.get("id") for item in matched if item.get("id")],
            "evidence_status": "mentioned_not_externally_verified",
            "modality": "uncertain" if all(item.get("modality") == "uncertain" for item in matched) else "asserted_or_mixed",
        })
    return output


def _relations(claims: list[dict]) -> list[dict]:
    output = []
    for item in claims:
        predicate = item.get("predicate")
        if predicate not in {
            "near_according_to_speaker",
            "possibly_near_according_to_speaker",
            "co_mentioned_in_utterance",
        }:
            continue
        output.append({
            "subject": item.get("subject"),
            "relation": {
                "near_according_to_speaker": "near_claimed_by_speaker",
                "possibly_near_according_to_speaker": "possibly_near_claimed_by_speaker",
                "co_mentioned_in_utterance": "co_mentioned_only",
            }[predicate],
            "object": item.get("value"),
            "claim_id": item.get("id"),
            "distance_m": None,
            "bearing_degrees": None,
            "evidence_status": "speech_claim_not_map_verified",
        })
    return output


def _visual_signature(geo_scene: dict) -> list[dict]:
    """Return real frame-local model boxes, never fake map geometry."""
    visual = geo_scene.get("visual_verification")
    if not isinstance(visual, dict):
        return []
    signatures = []
    for scene in _rows(visual.get("scenes")):
        for candidate in _rows(scene.get("candidates")):
            box = candidate.get("bbox")
            if not (isinstance(box, (list, tuple)) and len(box) == 4):
                continue
            try:
                coords = [float(value) for value in box]
            except (TypeError, ValueError, OverflowError):
                continue
            if any(not 0 <= value <= 1 for value in coords):
                continue
            signatures.append({
                "label": candidate.get("label"),
                "timestamp": candidate.get("timestamp"),
                "artifact": candidate.get("artifact"),
                "bbox": coords,
                "coordinate_space": "normalized_video_frame_not_map",
                "model_score": candidate.get("model_score"),
                "claim": "unverified_model_class_candidate",
                "geo_scene_id": scene.get("scene_id"),
            })
            if len(signatures) >= 20:
                return signatures
    return signatures


def generate_map_queries(geo_scene: dict | None) -> dict:
    """Create a compact, source-linked search recipe. No geocoding is done."""
    geo_scene = geo_scene if isinstance(geo_scene, dict) else {}
    claims = _rows(geo_scene.get("claims"))
    regions = _region_claims(claims)
    region_values = list(dict.fromkeys(item.get("value") for item in regions if item.get("value")))
    region = region_values[0] if len(region_values) == 1 else None
    requirements = _requirements(claims)
    relations = _relations(claims)
    features = _visual_signature(geo_scene)

    terms = []
    if any(item["key"] == "former_or_abandoned_settlement" for item in requirements):
        terms.append("исчезнувшая или заброшенная деревня / урочище")
    if any(item["key"] == "manor_or_estate_site_mentioned" for item in requirements):
        terms.append("усадьба или усадебный дом")
    if any(item["key"] == "church_or_church_site_mentioned" for item in requirements):
        terms.append("церковь или бывшее церковное место")
    if any(item["key"] == "historical_house_count_claim" for item in requirements):
        terms.append("проверить указанное число домов по датированной исторической карте")
    if any(item["key"] == "river_or_stream_mentioned" for item in requirements):
        terms.append("река или ручей поблизости — расстояние не установлено")
    if any(item["key"] == "road_mentioned" for item in requirements):
        terms.append("старая/современная дорога; сопоставить по отдельным источникам")

    search_phrases = []
    if region and terms:
        search_phrases.append(region + ": " + "; ".join(terms))

    if len(region_values) > 1:
        region_status = "conflicting_region_mentions"
    elif region:
        region_status = "mentioned_in_video_not_verified"
    else:
        region_status = "not_found"

    has_information = bool(claims or features)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "search_hypothesis_only" if has_information else "no_geographic_evidence",
        "region": region,
        "region_status": region_status,
        "conflicting_region_mentions": region_values if len(region_values) > 1 else [],
        "requirements": requirements,
        "relations": relations,
        "visual_signature": features,
        "geometry": {
            "map_coordinates": None,
            "map_bbox": None,
            "metric_mask_ready": False,
            "image_boxes_are_map_geometry": False,
        },
        "search_phrases": search_phrases,
        "external_sources_checked": False,
        "notes": [
            "Кандидатные условия сформированы из речи/OCR и не подтверждены внешними картами.",
            "Отношение «рядом» сохраняет слова автора; дистанция и направление неизвестны.",
            "Визуальные bbox — только нормализованные координаты кадра, не карта.",
            "Класс модели не устанавливает, что здание является названной усадьбой или церковью.",
        ],
    }
