"""Фенология как слабая гео-улика.

Канал независим от GPS: по стадии вегетации (листва, трава, снег)
строится окно даты и полоса широт. Таблица фаз — для ЦФО
(54–58° с.ш.); за пределами полосы окно расширяется и уверенность
падает.

Модуль не требует модели: стадия выводится из метрик кадра
(доля вегетации, снега) либо принимается явно. Это осознанно
слабая улика: она сужает сезон и широту, но не даёт координат.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta


LAT_BANDS: tuple[tuple[int, int], ...] = (
    (54, 55),
    (55, 56),
    (56, 57),
    (57, 58),
)

# phase -> (подпись, окно по полосам широт)
#
# Даты — типичные для ЦФО, а не строгие границы: у года бывает
# разброс 7–12 дней, поэтому уверенность канала невысокая.
PHASES: dict[str, dict] = {
    "snow": {
        "label": "снежный покров",
        "leaf_pct": (0, 0),
        "bands": {
            (54, 55): ("11-25", "03-20"),
            (55, 56): ("11-20", "03-25"),
            (56, 57): ("11-15", "03-31"),
            (57, 58): ("11-10", "04-05"),
        },
    },
    "bare": {
        "label": "без листвы",
        "leaf_pct": (0, 3),
        "bands": {
            (54, 55): ("10-20", "04-10"),
            (55, 56): ("10-18", "04-15"),
            (56, 57): ("10-15", "04-20"),
            (57, 58): ("10-12", "04-25"),
        },
    },
    "leaf_out": {
        "label": "распускание листвы",
        "leaf_pct": (3, 30),
        "bands": {
            (54, 55): ("04-15", "05-05"),
            (55, 56): ("04-20", "05-10"),
            (56, 57): ("04-25", "05-15"),
            (57, 58): ("05-01", "05-20"),
        },
    },
    "full_leaf": {
        "label": "полная листва",
        "leaf_pct": (30, 70),
        "bands": {
            (54, 55): ("05-01", "05-25"),
            (55, 56): ("05-05", "05-30"),
            (56, 57): ("05-10", "06-05"),
            (57, 58): ("05-15", "06-10"),
        },
    },
    "summer": {
        "label": "летняя вегетация",
        "leaf_pct": (70, 100),
        "bands": {
            (54, 55): ("06-01", "08-25"),
            (55, 56): ("06-05", "08-25"),
            (56, 57): ("06-10", "08-20"),
            (57, 58): ("06-15", "08-20"),
        },
    },
    "turning": {
        "label": "пожелтение листвы",
        "leaf_pct": (30, 70),
        "bands": {
            (54, 55): ("09-10", "10-10"),
            (55, 56): ("09-12", "10-12"),
            (56, 57): ("09-15", "10-15"),
            (57, 58): ("09-18", "10-18"),
        },
    },
}


def _parse_date(value) -> date | None:
    """Достать дату из ISO-строки или datetime."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value or "").strip()

    if not text:
        return None

    match = text[:10]

    try:
        return date.fromisoformat(match)

    except ValueError:
        return None


def _month_day(value: str) -> tuple[int, int]:
    month, day = value.split("-")

    return int(month), int(day)


def _candidate_windows(
    start_md: str,
    end_md: str,
    reference: date,
) -> list[tuple[date, date]]:
    """Окна за прошлый, текущий и следующий год."""

    start_month, start_day = _month_day(start_md)
    end_month, end_day = _month_day(end_md)
    windows = []

    for year in (reference.year - 1, reference.year, reference.year + 1):
        start = date(year, start_month, start_day)
        end = date(year, end_month, end_day)

        if end < start:
            end = date(year + 1, end_month, end_day)

        windows.append((start, end))

    return windows


def date_window(
    phase: str,
    latitude: float | None = None,
    reference=None,
) -> dict:
    """Окно даты для фазы и полосы широт.

    Без широты берётся объединение всех полос ЦФО — окно шире,
    уверенность ниже. Окно выбирается ближайшим к reference,
    поэтому зимний переход через год не ломается.
    """

    spec = PHASES.get(phase)

    if not spec:
        return {"start": None, "end": None, "band": None}

    ref = _parse_date(reference) or date.today()
    band = band_for(latitude)

    if band is not None:
        start_md, end_md = spec["bands"][band]
        candidates = _candidate_windows(start_md, end_md, ref)
    else:
        candidates = []

        for item_band, (start_md, end_md) in spec["bands"].items():
            candidates.extend(
                _candidate_windows(start_md, end_md, ref)
            )

    best = min(
        candidates,
        key=lambda pair: abs(
            (pair[0] + (pair[1] - pair[0]) / 2 - ref).days
        ),
    )

    return {
        "start": best[0].isoformat(),
        "end": best[1].isoformat(),
        "band": list(band) if band else None,
    }


def band_for(latitude: float | None) -> tuple[int, int] | None:
    if latitude is None:
        return None

    try:
        value = float(latitude)

    except (TypeError, ValueError):
        return None

    for band in LAT_BANDS:
        if band[0] <= value < band[1]:
            return band

    return None


def phase_from_metrics(metrics: dict) -> str:
    """Грубая стадия по доле вегетации и снега."""

    snow = float(metrics.get("snow") or 0.0)
    vegetation = float(metrics.get("vegetation") or 0.0)

    if snow >= 15:
        return "snow"

    if vegetation <= 2:
        return "bare"

    if vegetation <= 8:
        return "leaf_out"

    if vegetation <= 20:
        return "full_leaf"

    return "summer"


def leaf_pct_from_metrics(metrics: dict) -> int:
    """Оценка покрытия листвой по доле зелёных пикселей."""

    vegetation = float(metrics.get("vegetation") or 0.0)

    return int(round(max(0.0, min(100.0, vegetation * 3.0))))


def conflict_with_created_at(
    window: dict,
    created_at,
) -> bool | None:
    """Лежит ли дата файла вне фенологического окна."""

    created = _parse_date(created_at)
    start = _parse_date(window.get("start"))
    end = _parse_date(window.get("end"))

    if created is None or start is None or end is None:
        return None

    return not (start <= created <= end)


def build_clue(
    phase: str,
    *,
    leaf_pct: int | None = None,
    grass_h_cm: float | None = None,
    notes: str = "",
    latitude: float | None = None,
    created_at=None,
    timestamp: float = 0.0,
    confidence: float | None = None,
) -> dict:
    """Собрать улику в формате location_evidence."""

    spec = PHASES.get(phase) or PHASES["summer"]
    window = date_window(phase, latitude, created_at)
    conflict = conflict_with_created_at(window, created_at)

    if leaf_pct is None:
        leaf_pct = spec["leaf_pct"][0]

    if confidence is None:
        confidence = 0.45 if phase in ("snow", "bare") else 0.35

        if window.get("band") is None:
            confidence *= 0.7

        if conflict:
            confidence *= 0.6

    text = (
        f"Фенология: {spec['label']}; "
        f"листва ≈{leaf_pct}%"
        + (
            f", трава ≈{grass_h_cm:g} см"
            if grass_h_cm is not None
            else ""
        )
        + (
            f"; окно даты {window['start']}…{window['end']}"
            if window.get("start")
            else ""
        )
    )

    if conflict:
        text += "; дата файла вне окна — возможен конфликт"

    if notes:
        text += f"; {notes}"

    return {
        "kind": "phenology",
        "label": "Стадия вегетации",
        "text": text,
        "confidence": round(float(confidence), 3),
        "country_hints": {"RU": 0.12},
        "start": float(timestamp),
        "end": float(timestamp),
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "phase": phase,
            "phase_label": spec["label"],
            "leaf_pct": leaf_pct,
            "grass_h_cm": grass_h_cm,
            "notes": notes or None,
            "date_window": [window.get("start"), window.get("end")],
            "latitude_band": window.get("band"),
            "date_conflict": conflict,
            "origin": "phenology",
        },
    }


def analyze_frames(
    frames: list[dict],
    *,
    created_at=None,
    latitude: float | None = None,
) -> dict:
    """Свести метрики кадров в одну фенологическую улику."""

    phases: Counter = Counter()
    vegetation: list[float] = []
    last_timestamp = 0.0

    for frame in frames:
        metrics = frame.get("metrics") or {}

        if not metrics:
            continue

        phases[phase_from_metrics(metrics)] += 1
        vegetation.append(float(metrics.get("vegetation") or 0.0))
        last_timestamp = float(frame.get("timestamp") or 0.0)

    if not phases:
        return {"clue": None, "phase": None, "frames": 0}

    phase = phases.most_common(1)[0][0]
    mean_vegetation = sum(vegetation) / len(vegetation)
    leaf_pct = int(round(max(0.0, min(100.0, mean_vegetation * 3.0))))

    clue = build_clue(
        phase,
        leaf_pct=leaf_pct,
        created_at=created_at,
        latitude=latitude,
        timestamp=last_timestamp,
    )

    return {
        "clue": clue,
        "phase": phase,
        "phase_label": PHASES[phase]["label"],
        "frames": len(vegetation),
        "distribution": dict(phases),
    }


def temporal_conflict_clue(
    window: dict,
    created_at,
    duration: float = 0.0,
) -> dict | None:
    """Отдельная улика конфликта «дата файла vs сезон»."""

    if not conflict_with_created_at(window, created_at):
        return None

    return {
        "kind": "temporal_conflict",
        "label": "Конфликт даты и сезона",
        "text": (
            "Дата файла не попадает в фенологическое окно "
            f"{window.get('start')}…{window.get('end')}: "
            "дата создания файла ненадёжна."
        ),
        "confidence": 0.5,
        "country_hints": {},
        "start": 0.0,
        "end": float(duration),
        "artifact": None,
        "frame_artifact": None,
        "details": {
            "created_at": str(created_at),
            "date_window": [
                window.get("start"),
                window.get("end"),
            ],
            "origin": "phenology",
        },
    }


__all__ = [
    "LAT_BANDS",
    "PHASES",
    "analyze_frames",
    "band_for",
    "build_clue",
    "conflict_with_created_at",
    "date_window",
    "leaf_pct_from_metrics",
    "phase_from_metrics",
    "temporal_conflict_clue",
]
