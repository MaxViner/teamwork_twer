"""Локационное досье.

Собирает признаки из всех этапов: адреса, топонимы, телефоны,
домены, бренды, номера, валюту, язык, GPS, аудио и объекты сцены.
geo.py оценивает и объединяет их, после чего этап сохраняет
кандидатов по странам и местам и готовые поисковые запросы.

Файловые операции идут через StorageService: досье пишется в
runs/<run_id>/location_evidence.json, а в result["artifact"]
сохраняется путь относительно folder (storage.relative).
"""

import json
import re
from collections import Counter

from app.storage import StorageService
from app.utils.errors import SkipStage
from app.services.geoInspectService.geo import (
    device_evidence,
    extract_text_evidence,
    summarize,
)
from app.services.weakCluesService import collect_weak_clues
from app.utils.observations import observation


MAX_OBSERVATIONS = 300


def extract_location_evidence(
    storage: StorageService,
    stages: dict,
    progress,
) -> dict:
    prepared = stages.get("prepare", {}).get(
        "result",
        {},
    )
    duration = float(prepared.get("duration", 0.0))

    progress(0, "Собираю текстовые географические признаки")

    evidence = []
    origins = _text_origins(stages)

    for index, (item, source_name) in enumerate(origins):
        if index % 20 == 0:
            progress(
                min(35, index / max(1, len(origins)) * 35),
                "Разбираю текст и метаданные: "
                f"{index + 1}/{len(origins)}",
            )

        for found in extract_text_evidence(
            item.get("text", ""),
            source_name,
        ):
            found["start"] = float(item.get("start", 0.0))
            found["end"] = float(item.get("end", 0.0))
            found["artifact"] = item.get("artifact")
            found["frame_artifact"] = item.get(
                "frame_artifact"
            )
            found["origin_observation_id"] = item.get("id")
            evidence.append(found)

    progress(40, "Добавляю GPS и сведения об устройстве")

    evidence.extend(
        _metadata_coordinates(stages, duration)
    )
    evidence.extend(
        _metadata_context(stages, duration)
    )

    progress(55, "Добавляю визуальный и звуковой профиль")

    evidence.extend(_visual_evidence(stages, duration))
    evidence.extend(_road_evidence(stages, duration))
    evidence.extend(_audio_evidence(stages, duration))
    evidence.extend(_scene_evidence(stages, duration))
    evidence.extend(_structure_evidence(stages, duration))

    progress(65, "Добавляю слабые улики: фенология, птицы, столбы")

    evidence.extend(collect_weak_clues(stages, duration))

    evidence = _merge(evidence)
    evidence = _limit(evidence)

    if not evidence:
        raise SkipStage(
            "Географических признаков не найдено: "
            "нет GPS, адресов, упоминаний места, ссылок, "
            "телефонов, профиля сцены или дороги."
        )

    progress(75, "Формирую локационное досье")

    profile = _profile(stages)
    dossier = summarize(evidence, profile, duration)

    observations = _build_observations(
        evidence,
        duration,
    )

    dossier_path = storage.run_path("location_evidence.json")
    dossier_path.write_text(
        json.dumps(
            {
                "dossier": dossier,
                "evidence": evidence,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    progress(100, "Локационное досье готово")

    return {
        "dossier": dossier,
        "artifact": storage.relative(dossier_path),
        "observations": observations,
        "note": (
            "Это признаки и гипотезы для поиска места, "
            "а не подтверждённый адрес. Проверьте находки "
            "вручную и сопоставьте с картой."
        ),
    }


def _text_origins(stages: dict) -> list[tuple[dict, str]]:
    origins = []

    for stage_name in (
        "metadata",
        "speech",
        "ocr",
    ):
        for item in _completed_observations(
            stages,
            stage_name,
        ):
            text = item.get("corrected_text")

            if text is None:
                text = item.get("text", "")

            text = str(text).strip()

            if text:
                entry = dict(item)
                entry["text"] = text
                origins.append((entry, stage_name))

    return origins


def _completed_observations(
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


def _metadata_coordinates(
    stages: dict,
    duration: float,
) -> list[dict]:
    result = stages.get("metadata", {}).get(
        "result",
        {},
    )

    evidence = []

    for item in result.get("gps", []):
        try:
            latitude = float(item["latitude"])
            longitude = float(item["longitude"])

        except (KeyError, TypeError, ValueError):
            continue

        evidence.append({
            "kind": "coordinates",
            "label": "GPS-координаты файла",
            "text": f"{latitude:.6f}, {longitude:.6f}",
            "confidence": 0.95,
            "country_hints": {},
            "start": 0.0,
            "end": duration,
            "artifact": None,
            "frame_artifact": None,
            "origin_observation_id": None,
            "details": {
                "latitude": latitude,
                "longitude": longitude,
                "origin": "metadata",
            },
        })

    return evidence


def _metadata_context(
    stages: dict,
    duration: float,
) -> list[dict]:
    result = stages.get("metadata", {}).get(
        "result",
        {},
    )
    evidence = []

    for item in device_evidence(result.get("device")):
        item.update({
            "start": 0.0,
            "end": duration,
            "artifact": None,
            "frame_artifact": None,
        })
        evidence.append(item)

    created_at = result.get("created_at")

    if created_at:
        season = _season_from_date(created_at)

        text = f"Дата создания файла: {created_at}"

        if season:
            text += f"; сезон: {season}"

        evidence.append({
            "kind": "created_at",
            "label": "Дата и сезон съёмки",
            "text": text,
            "confidence": 0.5,
            "country_hints": {},
            "start": 0.0,
            "end": duration,
            "artifact": None,
            "frame_artifact": None,
            "details": {
                "created_at": created_at,
                "season": season,
            },
        })

    return evidence


def _visual_evidence(
    stages: dict,
    duration: float,
) -> list[dict]:
    result = stages.get("visual_analysis", {}).get(
        "result",
        {},
    )
    if not result:
        result = stages.get("visual_profile", {}).get(
            "result",
            {},
        )
    profile = result.get("profile") or {}

    if not profile:
        return []

    landscape = ", ".join(
        profile.get("landscape", [])
    ) or "признаки не выражены"

    text = (
        f"Визуальный профиль: "
        f"{profile.get('lighting')}; "
        f"{profile.get('weather')}; "
        f"{profile.get('season')}; "
        f"ландшафт: {landscape}"
    )

    return [{
        "kind": "visual_profile",
        "label": "Визуальный профиль места",
        "text": text,
        "confidence": 0.35,
        "country_hints": {},
        "start": 0.0,
        "end": duration,
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "profile": profile,
        },
    }]


def _road_evidence(
    stages: dict,
    duration: float,
) -> list[dict]:
    result = (
        stages.get("place_profile", {})
        .get("result", {})
        .get("road")
        or {}
    )
    if not result:
        result = stages.get("road_geometry", {}).get(
            "result",
            {},
        )
    summary = result.get("summary") or {}

    if not summary.get("road_detected"):
        return []

    text = (
        f"Дорога: {summary.get('direction')}; "
        f"линия схода: {summary.get('vanishing_ratio')}; "
        f"кадров с разметкой: {summary.get('marking_frames')}"
    )

    return [{
        "kind": "road_geometry",
        "label": "Геометрия видимой дороги",
        "text": text,
        "confidence": float(
            summary.get("confidence", 0.3)
        ),
        "country_hints": {},
        "start": 0.0,
        "end": duration,
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "summary": summary,
        },
    }]


def _audio_evidence(
    stages: dict,
    duration: float,
) -> list[dict]:
    result = stages.get("audio_structure", {}).get(
        "result",
        {},
    )
    summary = result.get("sound_summary") or []
    profile = result.get("profile") or {}

    evidence = []

    # 1. Семантические звуки — приоритет (поезд, колокол, сирена…)
    for item in summary[:6]:
        evidence.append({
            "kind": "sound_event",
            "label": (
                f"Идентифицированный звук: "
                f"{item['label_ru']}"
            ),
            "text": (
                f"«{item['label_ru']}» — "
                f"{item['count']} участк., "
                f"суммарно {item['total_seconds']} с"
            ),
            "confidence": min(
                0.85,
                float(item.get("max_confidence") or 0.3),
            ),
            "country_hints": {},
            "start": 0.0,
            "end": duration,
            "artifact": None,
            "frame_artifact": None,
            "details": {
                "sound_kind": item.get("kind"),
                "importance": item.get("importance"),
                "intervals": item.get("intervals", [])[:5],
                "origin": "audio_semantic",
            },
        })

    # 2. Общий профиль — низкий приоритет
    if profile:
        evidence.append({
            "kind": "audio_profile",
            "label": "Акустическая обстановка",
            "text": (
                f"Фон: {profile.get('environment')}; "
                f"тишина "
                f"{profile.get('silence_ratio', 0) * 100:.0f}%"
            ),
            "confidence": 0.2,
            "country_hints": {},
            "start": 0.0,
            "end": duration,
            "artifact": None,
            "frame_artifact": None,
            "details": {
                "environment": profile.get("environment"),
                "silence_ratio": profile.get("silence_ratio"),
                "loud_ratio": profile.get("loud_ratio"),
            },
        })

    return evidence

def _scene_evidence(
    stages: dict,
    duration: float,
) -> list[dict]:
    result = stages.get("visual_analysis", {}).get(
        "result",
        {},
    )
    if not result:
        result = stages.get("scene_objects", {}).get(
            "result",
            {},
        )
    frames = result.get("frames", [])

    if not frames:
        return []

    counts = Counter()

    for frame in frames:
        for item in frame.get("objects", []):
            label = item.get("label_ru") or item.get(
                "label"
            )

            if label:
                counts[str(label)] += 1

    if not counts:
        return []

    readable = ", ".join(
        f"{label} ({count} кадр.)"
        for label, count in counts.most_common(8)
    )

    return [{
        "kind": "scene_profile",
        "label": "Визуальные объекты сцены",
        "text": f"В кадрах видны: {readable}",
        "confidence": 0.35,
        "country_hints": {},
        "start": 0.0,
        "end": duration,
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "method": result.get("method"),
            "objects": dict(counts),
        },
    }]


def _structure_evidence(
    stages: dict,
    duration: float,
) -> list[dict]:
    result = stages.get("structure", {}).get(
        "result",
        {},
    )
    groups = result.get("text_groups") or []

    if not groups:
        return []

    readable = "; ".join(
        f"{item['text'][:60]} ×{item['count']}"
        for item in groups[:5]
    )

    return [{
        "kind": "repetition",
        "label": "Повторяющиеся надписи",
        "text": f"Повторы в кадре: {readable}",
        "confidence": 0.3,
        "country_hints": {},
        "start": 0.0,
        "end": duration,
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "groups": len(groups),
        },
    }]


def _merge(evidence: list[dict]) -> list[dict]:
    merged = {}

    for item in evidence:
        key = (
            item["kind"],
            " ".join(str(item["text"]).casefold().split()),
        )

        if key not in merged:
            item["occurrences"] = 1
            merged[key] = item
            continue

        existing = merged[key]
        existing["occurrences"] += 1
        existing["start"] = min(
            float(existing.get("start", 0.0)),
            float(item.get("start", 0.0)),
        )
        existing["end"] = max(
            float(existing.get("end", 0.0)),
            float(item.get("end", 0.0)),
        )

        if not existing.get("artifact") and item.get(
            "artifact"
        ):
            existing["artifact"] = item["artifact"]

        if not existing.get("frame_artifact") and item.get(
            "frame_artifact"
        ):
            existing["frame_artifact"] = item[
                "frame_artifact"
            ]

    return sorted(
        merged.values(),
        key=lambda item: (
            float(item.get("start", 0.0)),
            item["kind"],
        ),
    )


def _limit(evidence: list[dict]) -> list[dict]:
    limits = {
        "place_mention": 40,
        "address": 40,
        "phone": 30,
        "link": 30,
        "business": 40,
        "transport": 25,
        "units": 15,
        "language": 5,
        "coordinates": 20,
    }

    counts = Counter()
    result = []

    for item in evidence:
        kind = item["kind"]
        limit = limits.get(kind, 20)

        if counts[kind] >= limit:
            continue

        counts[kind] += 1
        result.append(item)

    return result


def _profile(stages: dict) -> dict:
    visual_result = stages.get("visual_analysis", {}).get(
        "result",
        {},
    )
    if not visual_result:
        visual_result = stages.get("visual_profile", {}).get(
            "result",
            {},
        )
    visual = visual_result.get("profile") or {}

    road_result = (
        stages.get("place_profile", {})
        .get("result", {})
        .get("road")
        or {}
    )
    if not road_result:
        road_result = stages.get("road_geometry", {}).get(
            "result",
            {},
        )
    road = road_result.get("summary") or {}

    audio = stages.get("audio_structure", {}).get(
        "result",
        {},
    ).get("profile") or {}

    scene = visual_result or stages.get("scene_objects", {}).get(
        "result",
        {},
    )

    metadata = stages.get("metadata", {}).get(
        "result",
        {},
    )

    structure = stages.get("structure", {}).get(
        "result",
        {},
    )

    return {
        "visual": visual,
        "road": road,
        "audio": audio,
        "scene": {
            "method": scene.get("method"),
            "sampled_frames": scene.get(
                "sampled_frames"
            ),
            "successful_frames": scene.get(
                "successful_frames"
            ),
        },
        "structure": {
            "text_groups": len(
                structure.get("text_groups") or []
            ),
            "compared_frames": structure.get(
                "compared_frames"
            ),
        },
        "device": metadata.get("device"),
        "created_at": metadata.get("created_at"),
        "season": _season_from_date(
            metadata.get("created_at")
        ),
    }


def _build_observations(
    evidence: list[dict],
    duration: float,
) -> list[dict]:
    observations = []

    for item in evidence[:MAX_OBSERVATIONS]:
        start = float(item.get("start", 0.0))
        end = float(item.get("end", 0.0))

        observations.append(
            observation(
                source="location_evidence",
                start=max(0.0, min(start, duration or start)),
                end=max(
                    start,
                    min(end, duration or end),
                ),
                text=(
                    f"{item['label']}: {item['text']}"
                )[:2000],
                artifact=item.get("artifact"),
                frame_artifact=item.get("frame_artifact"),
                extractor=(
                    f"location-fusion:{item['kind']}"
                ),
                data={
                    "kind": item["kind"],
                    "origin": item.get("details", {}).get(
                        "origin",
                    ),
                    "confidence": item.get("confidence"),
                    "country_hints": item.get(
                        "country_hints",
                        {},
                    ),
                    "occurrences": item.get(
                        "occurrences",
                        1,
                    ),
                    "requires_review": item["kind"] not in (
                        "coordinates",
                    ),
                    **item.get("details", {}),
                },
            )
        )

    return observations


def _season_from_date(value) -> str | None:
    text = str(value or "")

    match = re.search(
        r"(?<!\d)(\d{4})[-:.](\d{1,2})[-:.](\d{1,2})",
        text,
    )

    if match:
        month = int(match.group(2))

    else:
        match = re.search(
            r"(\d{1,2})[-:.](\d{1,2})[-:.](\d{4})",
            text,
        )

        if not match:
            return None

        month = int(match.group(2))

    if month in (12, 1, 2):
        return "зима (северное полушарие)"

    if month in (3, 4, 5):
        return "весна (северное полушарие)"

    if month in (6, 7, 8):
        return "лето (северное полушарие)"

    return "осень (северное полушарие)"