"""Байесовская агрегация слабых улик.

Средний confidence заменён на лог-правдоподобие по совокупности
ортогональных каналов. Коррелирующие улики (ландшафт/фенология,
шум дороги/геометрия дороги) не суммируются как независимые:
внутри группы учитывается только сильнейшая, остальные получают
понижающий вес.

Перед агрегацией наблюдения кластеризуются по времени: улики из
разных фрагментов ролика не смешиваются, фенология не переносится
между кластерами.
"""

from __future__ import annotations

import math
from collections import defaultdict


# kind -> (группа, надёжность канала 0..1)
CHANNELS: dict[str, tuple[str, float]] = {
    "coordinates": ("geo", 0.97),
    "address": ("text", 0.6),
    "place_mention": ("text", 0.55),
    "business": ("text", 0.4),
    "transport": ("text", 0.35),
    "language": ("text", 0.35),
    "phone": ("text", 0.45),
    "link": ("text", 0.45),
    "units": ("text", 0.25),
    "repetition": ("text", 0.3),
    "phenology": ("season", 0.55),
    "bird_species": ("fauna", 0.6),
    "sun": ("sun", 0.5),
    "km_post": ("infrastructure", 0.75),
    "road_noise": ("infrastructure", 0.4),
    "road_geometry": ("infrastructure", 0.4),
    "visual_profile": ("landscape", 0.35),
    "scene_profile": ("landscape", 0.35),
    "terrain": ("landscape", 0.4),
    "sound_event": ("audio", 0.55),
    "audio_profile": ("audio", 0.3),
    "created_at": ("meta", 0.4),
    "temporal_conflict": ("meta", 0.5),
}

GROUP_LABELS = {
    "geo": "координаты",
    "text": "текст и топонимы",
    "season": "фенология",
    "fauna": "птицы",
    "sun": "солнце и тени",
    "infrastructure": "инфраструктура",
    "landscape": "ландшафт",
    "audio": "акустика",
    "meta": "метаданные",
    "other": "прочее",
}

# Корреляция групп: 1.0 — одна и та же улика, 0.0 — независимы.
ORTHOGONALITY: dict[tuple[str, str], float] = {
    ("season", "landscape"): 0.45,
    ("season", "fauna"): 0.2,
    ("fauna", "landscape"): 0.25,
    ("audio", "infrastructure"): 0.35,
    ("audio", "fauna"): 0.2,
    ("text", "meta"): 0.3,
    ("text", "landscape"): 0.15,
    ("infrastructure", "landscape"): 0.2,
    ("sun", "season"): 0.1,
}

INTRA_GROUP_CORRELATION = 0.6
META_GROUPS = {"meta"}
LOCALIZED_MIN_SECONDS = 3.0


def _pair(left: str, right: str) -> float:
    if left == right:
        return 1.0

    return ORTHOGONALITY.get(
        (left, right),
        ORTHOGONALITY.get((right, left), 0.1),
    )


def _channel(kind: str) -> tuple[str, float]:
    return CHANNELS.get(kind, ("other", 0.3))


def _llr(probability: float) -> float:
    value = max(0.01, min(0.99, probability))

    return math.log(value / (1.0 - value))


def _strength(item: dict) -> float:
    group, reliability = _channel(item.get("kind", ""))
    confidence = float(item.get("confidence") or 0.0)

    return max(0.01, reliability * max(0.05, confidence))


def _dedupe(evidence: list[dict]) -> list[dict]:
    """Убрать буквальные повторы, оставив максимальную уверенность."""

    seen: dict[tuple, dict] = {}

    for item in evidence:
        kind = item.get("kind") or "other"
        text = " ".join(str(item.get("text") or "").casefold().split())
        key = (kind, text[:160])
        current = seen.get(key)

        if current is None:
            seen[key] = item
            continue

        if float(item.get("confidence") or 0) > float(
            current.get("confidence") or 0
        ):
            seen[key] = item

    return list(seen.values())


def _is_localized(item: dict, duration: float) -> bool:
    start = float(item.get("start") or 0.0)
    end = float(item.get("end") or 0.0)

    if end - start >= LOCALIZED_MIN_SECONDS:
        return True

    if duration and end >= duration * 0.8:
        return False

    return start > 0.0


def cluster_evidence(
    evidence: list[dict],
    duration: float = 0.0,
    window: float = 12.0,
) -> list[dict]:
    """Сгруппировать локализованные улики по времени.

    Улики «на всё видео» (фенология, профиль) остаются в отдельном
    глобальном кластере и не переносятся в локальные.
    """

    localized = []
    global_items = []

    for item in evidence:
        if _is_localized(item, duration):
            start = float(item.get("start") or 0.0)
            end = float(item.get("end") or 0.0)
            localized.append((start, end, item))
        else:
            global_items.append(item)

    localized.sort(key=lambda entry: entry[0])

    clusters: list[list[tuple[float, float, dict]]] = []

    for entry in localized:
        if not clusters:
            clusters.append([entry])
            continue

        previous_end = max(
            item[1] for item in clusters[-1]
        )

        if entry[0] - previous_end <= window:
            clusters[-1].append(entry)
        else:
            clusters.append([entry])

    result = []

    for index, cluster in enumerate(clusters):
        start = min(item[0] for item in cluster)
        end = max(item[1] for item in cluster)
        items = [item[2] for item in cluster]

        result.append(_cluster_payload(
            index,
            start,
            end,
            items,
            global_items,
        ))

    if not clusters:
        result.append(_cluster_payload(
            0,
            0.0,
            float(duration),
            [],
            global_items,
        ))

    return result[:8]


def _cluster_payload(
    index: int,
    start: float,
    end: float,
    items: list[dict],
    global_items: list[dict],
) -> dict:
    # Глобальные улики показываем в каждом кластере как контекст,
    # но в счёт ортогональности кластера они не идут: иначе
    # фенология «переедет» в чужие фрагменты.
    combined = items + global_items
    groups = sorted({
        _channel(item.get("kind", ""))[0]
        for item in combined
    } - META_GROUPS)

    return {
        "index": index,
        "start": round(start, 3),
        "end": round(end, 3),
        "channels": groups,
        "kinds": sorted({
            item.get("kind", "other") for item in items
        }),
        "local_items": len(items),
        "global_items": len(global_items),
        "score": _score(combined),
        "phenology_transfer_blocked": True,
    }


def _score(evidence: list[dict]) -> dict:
    """Лог-правдоподобие по группам с штрафом за корреляцию."""

    by_group: dict[str, list[dict]] = defaultdict(list)

    for item in evidence:
        group, _ = _channel(item.get("kind", ""))
        by_group[group].append(item)

    contributions = []
    total = 0.0

    for group, items in by_group.items():
        items = sorted(items, key=_strength, reverse=True)
        kinds = []
        group_total = 0.0

        for position, item in enumerate(items):
            kind = item.get("kind", "other")

            if kind in kinds:
                continue

            kinds.append(kind)
            strength = _strength(item)
            weight = 1.0 if position == 0 else (
                1.0 - INTRA_GROUP_CORRELATION
            )
            llr = _llr(strength) * weight
            group_total += llr

        total += group_total
        contributions.append({
            "group": group,
            "label": GROUP_LABELS.get(group, group),
            "kinds": kinds,
            "llr": round(group_total, 3),
        })

    contributions.sort(key=lambda item: -item["llr"])

    combined = 1.0 / (1.0 + math.exp(-0.6 * total))

    return {
        "combined_confidence": round(combined, 3),
        "log_likelihood": round(total, 3),
        "orthogonal_channels": len([
            item
            for item in contributions
            if item["group"] not in META_GROUPS
            and item["group"] != "other"
        ]),
        "channels": [
            {
                "group": item["group"],
                "label": item["label"],
                "kinds": item["kinds"],
                "llr": item["llr"],
            }
            for item in contributions
        ],
    }


def aggregate(
    evidence: list[dict],
    duration: float = 0.0,
    *,
    cluster_window: float = 12.0,
    road_limit: int = 5,
) -> dict:
    """Свести все улики в одну гипотезу и дорожные кандидаты."""

    from app.services.weakCluesService.infrastructure import (
        road_candidates,
    )

    items = _dedupe([
        item
        for item in evidence
        if isinstance(item, dict)
    ])

    score = _score(items)
    clusters = cluster_evidence(
        items,
        duration=duration,
        window=cluster_window,
    )
    candidates = road_candidates(items, limit=road_limit)

    channels = [
        item["group"]
        for item in score["channels"]
        if item["group"] not in META_GROUPS
        and item["group"] != "other"
    ]

    return {
        **score,
        "orthogonal_channels": len(channels),
        "channels": score["channels"],
        "orthogonal_channel_names": channels,
        "clusters": clusters,
        "road_candidates": candidates,
        "road_candidate_count": len(candidates),
        "note": (
            "Улики агрегированы как слабые независимые сигналы. "
            "Коррелирующие каналы не суммируются полностью; "
            "фенология не переносится между кластерами. "
            "Это гипотеза для проверки, не координаты."
        ),
    }


__all__ = [
    "CHANNELS",
    "GROUP_LABELS",
    "ORTHOGONALITY",
    "aggregate",
    "cluster_evidence",
]
