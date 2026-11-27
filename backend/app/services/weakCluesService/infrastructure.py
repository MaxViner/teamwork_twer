"""Инфраструктурные улики: километровые столбы и дорожные классы.

Километровый столб — самая сильная из «слабых» улик: если OCR
читает номер дороги и километр, кандидатов на местность остаётся
единицы. Модуль разбирает текст, собранный со стека кадров, и
строит не больше пяти дорожных кандидатов.

Никаких сетевых запросов: это чистый разбор и ранжирование.
"""

from __future__ import annotations

import re


# «М-10», «Р-132», «А-108», «1Р-132», «М10», «Р 132».
ROAD_REF_RE = re.compile(
    r"\b(?:([12])\s*)?([АМР])[\s-]?(\d{1,3})\b",
    re.IGNORECASE,
)

# «12 км», «км 12», «12,5 км», «12+500», «12.500».
KM_RE = re.compile(
    r"(?:\b(\d{1,3})[.,](\d{1,3})\s*(?:км|km)\b)"
    r"|(?:\b(\d{1,3})\s*(?:км|km)\b)"
    r"|(?:\bкм\.?\s*(\d{1,3})(?:[.,](\d{1,3}))?\b)"
    r"|(?:\b(\d{1,3})\s*\+\s*(\d{1,3})\b)",
    re.IGNORECASE,
)

# Километровый столб часто подписан «12» и «км» отдельно.
BARE_KM_RE = re.compile(r"^\s*(\d{1,3})\s*$")

ROAD_CLASSES = (
    "федеральная трасса",
    "региональная дорога",
    "местная дорога",
    "грунтовая дорога",
)


def parse_km_post(text: str) -> dict | None:
    """Разобрать OCR-текст столба в номер дороги и километр."""

    raw = " ".join(str(text or "").split())

    if not raw:
        return None

    road_ref = None
    match = ROAD_REF_RE.search(raw)

    if match:
        prefix = f"{match.group(1)}" if match.group(1) else ""
        letters = match.group(2).upper()
        digits = match.group(3)

        road_ref = f"{prefix}{letters}-{digits}"

    km = None
    match = KM_RE.search(raw)

    if match:
        if match.group(1):
            km = float(match.group(1))

            if match.group(2):
                km += float(f"0.{match.group(2)}")

        elif match.group(3):
            km = float(match.group(3))

        elif match.group(4):
            km = float(match.group(4))

            if match.group(5):
                km += float(f"0.{match.group(5)}")

        elif match.group(6):
            km = float(match.group(6)) + float(
                match.group(7)
            ) / 1000.0

    else:
        match = BARE_KM_RE.match(raw)

        if match:
            km = float(match.group(1))

    if road_ref is None and km is None:
        return None

    return {
        "road_ref": road_ref,
        "km": round(km, 3) if km is not None else None,
        "raw": raw[:200],
    }


def km_post_clue(
    text: str,
    *,
    confidence: float = 0.7,
    timestamp: float = 0.0,
    artifact: str | None = None,
    frame_artifact: str | None = None,
) -> dict | None:
    """Улика «километровый столб» из распознанного текста."""

    parsed = parse_km_post(text)

    if parsed is None:
        return None

    parts = []

    if parsed["road_ref"]:
        parts.append(f"дорога {parsed['road_ref']}")

    if parsed["km"] is not None:
        parts.append(f"{parsed['km']:g} км")

    return {
        "kind": "km_post",
        "label": "Километровый столб",
        "text": "Километровый столб: " + ", ".join(parts),
        "confidence": round(float(confidence), 3),
        "country_hints": {"RU": 0.2},
        "start": float(timestamp),
        "end": float(timestamp),
        "artifact": artifact,
        "frame_artifact": frame_artifact,
        "details": {
            "road_ref": parsed["road_ref"],
            "km": parsed["km"],
            "raw_text": parsed["raw"],
            "origin": "km_post",
        },
    }


def road_noise_clue(
    profile: dict,
    *,
    duration: float = 0.0,
) -> dict | None:
    """Класс дорожного шума по акустическому профилю."""

    if not profile:
        return None

    road_class = classify_road_noise(profile)

    if road_class is None:
        return None

    return {
        "kind": "road_noise",
        "label": "Дорожный шум",
        "text": f"Акустический класс дороги: {road_class}",
        "confidence": 0.3,
        "country_hints": {},
        "start": 0.0,
        "end": float(duration),
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "road_class": road_class,
            "mean_rms": profile.get("mean_rms"),
            "loud_ratio": profile.get("loud_ratio"),
            "mean_centroid_hz": profile.get("mean_centroid_hz"),
            "origin": "road_noise",
        },
    }


def classify_road_noise(profile: dict) -> str | None:
    """«трасса / местная / дачная» по громкости и спектру."""

    loud = float(profile.get("loud_ratio") or 0.0)
    rms = float(profile.get("mean_rms") or 0.0)
    centroid = float(profile.get("mean_centroid_hz") or 0.0)

    if loud >= 0.35 or rms >= 0.05:
        return "трасса"

    if loud >= 0.12 or rms >= 0.02:
        return "местная дорога"

    if centroid >= 1200 and rms >= 0.008:
        return "дачная дорога"

    return None


def road_candidates(
    evidence: list[dict],
    limit: int = 5,
) -> list[dict]:
    """До пяти дорожных кандидатов из всех инфраструктурных улик."""

    candidates: dict[tuple, dict] = {}

    for item in evidence:
        kind = item.get("kind")
        details = item.get("details") or {}
        confidence = float(item.get("confidence") or 0.0)

        if kind == "km_post":
            road_ref = details.get("road_ref")
            km = details.get("km")

            if road_ref:
                key = ("ref", road_ref)
                entry = candidates.setdefault(key, {
                    "road_ref": road_ref,
                    "km": [],
                    "road_class": None,
                    "confidence": 0.0,
                    "sources": [],
                })
                entry["confidence"] = max(
                    entry["confidence"],
                    confidence,
                )

                if km is not None and km not in entry["km"]:
                    entry["km"].append(km)

                if "km_post" not in entry["sources"]:
                    entry["sources"].append("km_post")

        elif kind == "road_noise":
            road_class = details.get("road_class")

            if road_class:
                key = ("class", road_class)
                entry = candidates.setdefault(key, {
                    "road_ref": None,
                    "km": [],
                    "road_class": road_class,
                    "confidence": 0.0,
                    "sources": [],
                })
                entry["confidence"] = max(
                    entry["confidence"],
                    confidence,
                )

                if "road_noise" not in entry["sources"]:
                    entry["sources"].append("road_noise")

        elif kind in ("place_mention", "address", "text"):
            text = str(item.get("text") or "")

            for match in ROAD_REF_RE.finditer(text):
                prefix = (
                    f"{match.group(1)}"
                    if match.group(1)
                    else ""
                )
                road_ref = (
                    f"{prefix}{match.group(2).upper()}"
                    f"-{match.group(3)}"
                )
                key = ("ref", road_ref)
                entry = candidates.setdefault(key, {
                    "road_ref": road_ref,
                    "km": [],
                    "road_class": None,
                    "confidence": 0.0,
                    "sources": [],
                })
                entry["confidence"] = max(
                    entry["confidence"],
                    confidence * 0.6,
                )

                if kind not in entry["sources"]:
                    entry["sources"].append(kind)

    result = []

    for entry in candidates.values():
        result.append({
            "road_ref": entry["road_ref"],
            "km": sorted(entry["km"]),
            "km_range": (
                [min(entry["km"]), max(entry["km"])]
                if entry["km"]
                else None
            ),
            "road_class": entry["road_class"],
            "confidence": round(
                min(0.95, entry["confidence"] + 0.1 * (len(entry["km"]) - 1)),
                3,
            ) if entry["km"] else round(entry["confidence"], 3),
            "sources": entry["sources"],
        })

    result.sort(
        key=lambda item: (
            -item["confidence"],
            item["road_ref"] or "я",
        ),
    )

    return result[:max(1, int(limit))]


def pole_subtype(text: str) -> str | None:
    """Подтип опоры по маркировке (СВ-95, СВ-105, дерево)."""

    normalized = str(text or "").casefold()

    if "св-95" in normalized or "св 95" in normalized:
        return "ЖБ СВ-95"

    if "св-105" in normalized or "св 105" in normalized:
        return "ЖБ СВ-105"

    if "жб" in normalized or "железобетон" in normalized:
        return "железобетон"

    if "дерев" in normalized:
        return "деревянная"

    return None


__all__ = [
    "KM_RE",
    "ROAD_CLASSES",
    "ROAD_REF_RE",
    "classify_road_noise",
    "km_post_clue",
    "parse_km_post",
    "pole_subtype",
    "road_candidates",
    "road_noise_clue",
]
