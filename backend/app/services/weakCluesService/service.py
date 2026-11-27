"""Сбор слабых гео-улик из результатов стадий.

Фасад для location_evidence и summarize: берёт уже посчитанные
результаты visual_analysis и audio_structure, добавляет
фенологию, BirdNET, километровые столбы, дорожный шум и
(если есть) солнце/тени. Ничего не считает заново и не ходит в
сеть.
"""

from __future__ import annotations

from app.services.weakCluesService import (
    aggregation,
    birdnet,
    infrastructure,
    phenology,
)


STACK_READING_KEYS = (
    "stacked_readings",
    "km_posts",
    "ocr_stack",
)


def collect_weak_clues(
    stages: dict,
    duration: float = 0.0,
) -> list[dict]:
    """Все слабые улики из готовых стадий."""

    visual = (
        stages.get("visual_analysis", {})
        .get("result", {})
    )
    audio = (
        stages.get("audio_structure", {})
        .get("result", {})
    )
    metadata = stages.get("metadata", {}).get("result", {})
    created_at = metadata.get("created_at")

    clues: list[dict] = []

    clues.extend(_phenology_clues(visual, created_at, duration))
    clues.extend(_bird_clues(audio, duration))
    clues.extend(_km_post_clues(visual, duration))
    clues.extend(_road_noise_clues(audio, duration))
    clues.extend(_sun_clues(visual, duration))

    return [
        item
        for item in clues
        if isinstance(item, dict) and item.get("kind")
    ]


def _phenology_clues(
    visual: dict,
    created_at,
    duration: float,
) -> list[dict]:
    result = visual.get("phenology")

    if isinstance(result, dict) and result.get("clue"):
        clue = dict(result["clue"])
        window = (clue.get("details") or {}).get(
            "date_window",
        ) or [None, None]

        clues = [clue]
        conflict = phenology.temporal_conflict_clue(
            {
                "start": window[0],
                "end": window[1],
            },
            created_at,
            duration,
        )

        if conflict:
            clues.append(conflict)

        return clues

    frames = visual.get("frames") or []

    if not frames:
        return []

    latitude = _latitude_hint(visual)
    analyzed = phenology.analyze_frames(
        frames,
        created_at=created_at,
        latitude=latitude,
    )
    clue = analyzed.get("clue")

    if not clue:
        return []

    clues = [clue]
    window = clue["details"].get("date_window") or [None, None]
    conflict = phenology.temporal_conflict_clue(
        {
            "start": window[0],
            "end": window[1],
        },
        created_at,
        duration,
    )

    if conflict:
        clues.append(conflict)

    return clues


def _latitude_hint(visual: dict) -> float | None:
    sun = visual.get("sun") or {}

    for key in ("latitude", "latitude_hint", "lat"):
        value = sun.get(key)

        if value is not None:
            try:
                return float(value)

            except (TypeError, ValueError):
                continue

    return None


def _bird_clues(
    audio: dict,
    duration: float,
) -> list[dict]:
    if audio.get("bird_clues"):
        return list(audio["bird_clues"])

    detections = audio.get("bird_species") or []

    if not detections:
        return []

    return birdnet.species_clues(detections, duration)


def _km_post_clues(
    visual: dict,
    duration: float,
) -> list[dict]:
    clues = []

    if visual.get("km_post_clues"):
        return list(visual["km_post_clues"])

    for key in STACK_READING_KEYS:
        for item in visual.get(key) or []:
            if not isinstance(item, dict):
                continue

            text = item.get("text") or item.get("value")

            if not text:
                continue

            clue = infrastructure.km_post_clue(
                text,
                confidence=float(item.get("confidence") or 0.7),
                timestamp=float(item.get("timestamp") or 0.0),
                artifact=item.get("artifact"),
                frame_artifact=item.get("frame_artifact"),
            )

            if clue:
                clues.append(clue)

    return clues


def _road_noise_clues(
    audio: dict,
    duration: float,
) -> list[dict]:
    profile = audio.get("profile") or {}
    clue = infrastructure.road_noise_clue(
        profile,
        duration=duration,
    )

    return [clue] if clue else []


def _sun_clues(
    visual: dict,
    duration: float,
) -> list[dict]:
    sun = visual.get("sun") or {}

    if not sun:
        return []

    azimuth = sun.get("azimuth_deg")
    altitude = sun.get("altitude_deg")

    if azimuth is None and altitude is None:
        return []

    latitude = sun.get("latitude_hint")
    text = "Солнце/тени:"

    if azimuth is not None:
        text += f" азимут {float(azimuth):.0f}°"

    if altitude is not None:
        text += f", высота {float(altitude):.0f}°"

    if latitude is not None:
        text += f", широта ≈{float(latitude):.1f}°"

    return [{
        "kind": "sun",
        "label": "Положение солнца",
        "text": text,
        "confidence": float(sun.get("confidence") or 0.4),
        "country_hints": {},
        "start": 0.0,
        "end": float(duration),
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "azimuth_deg": azimuth,
            "altitude_deg": altitude,
            "latitude_hint": latitude,
            "origin": "sun",
        },
    }]


def aggregate(
    evidence: list[dict],
    duration: float = 0.0,
) -> dict:
    return aggregation.aggregate(evidence, duration)


def readiness(aggregation_result: dict) -> dict:
    """Критерий готовности: ≥3 канала и ≤5 дорожных кандидатов."""

    channels = int(
        aggregation_result.get("orthogonal_channels") or 0
    )
    candidates = int(
        aggregation_result.get("road_candidate_count") or 0
    )

    return {
        "orthogonal_channels": channels,
        "road_candidate_count": candidates,
        "ready": channels >= 3 and 0 < candidates <= 5,
    }


__all__ = [
    "aggregate",
    "collect_weak_clues",
    "readiness",
]
