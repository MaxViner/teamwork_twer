"""Грубая оценка масштаба для визуальной одометрии.

Монокулярная одометрия даёт траекторию только в условных единицах.
Здесь подбирается приблизительный коэффициент перевода в метры:

1. высота камеры для известного типа устройства;
2. типовая ширина полосы из road_summary;
3. коэффициент 1.0, если данных нет.

Это не точная метрология: значение нужно только для сравнения
масштабов между эпизодами.
"""

from __future__ import annotations


DEFAULT_LANE_WIDTH_M = 3.5

DEVICE_HEIGHTS: dict[str, tuple[float, str]] = {
    "dashcam": (1.2, "dashcam_height"),
    "phone": (1.5, "phone_height"),
    "action_cam": (0.8, "action_cam_height"),
}

DEVICE_ALIASES = {
    "dash": "dashcam",
    "dash_cam": "dashcam",
    "dashcam": "dashcam",
    "car_camera": "dashcam",
    "phone": "phone",
    "smartphone": "phone",
    "mobile": "phone",
    "action": "action_cam",
    "actioncam": "action_cam",
    "action_cam": "action_cam",
    "gopro": "action_cam",
}


def estimate_scale(
    device: str | None,
    road_summary: dict | None,
) -> dict:
    """Подобрать коэффициент перевода условных единиц в метры."""

    normalized = _normalize_device(device)

    if normalized:
        height, source = DEVICE_HEIGHTS[normalized]
        return {
            "m_per_unit": height,
            "source": source,
            "confidence": 0.6,
        }

    lane_width = _lane_width(road_summary)

    if lane_width is not None:
        return {
            "m_per_unit": lane_width,
            "source": "lane_width",
            "confidence": 0.4,
        }

    return {
        "m_per_unit": 1.0,
        "source": "relative_units",
        "confidence": 0.0,
    }


def _normalize_device(device: str | None) -> str | None:
    """Привести название устройства к одному из известных типов."""

    if not device:
        return None

    key = str(device).strip().lower().replace("-", "_").replace(" ", "_")

    if key in DEVICE_ALIASES:
        return DEVICE_ALIASES[key]

    # Названия вроде "iPhone 13" или "GoPro Hero" тоже узнаём.
    if "gopro" in key or "action" in key:
        return "action_cam"

    if "phone" in key or "iphone" in key or "android" in key:
        return "phone"

    if "dash" in key:
        return "dashcam"

    return None


def _lane_width(road_summary: dict | None) -> float | None:
    """Достать ширину полосы из сводки о дороге, если она есть."""

    if not isinstance(road_summary, dict) or not road_summary:
        return None

    for key in ("lane_width_m", "lane_width", "width_m"):
        value = road_summary.get(key)

        try:
            number = float(value)
        except (TypeError, ValueError):
            continue

        if 1.0 <= number <= 10.0:
            return round(number, 3)

    # Сводка есть, но метрики нет: берём типовую полосу.
    if any(
        key in road_summary
        for key in ("width_label", "width_ratio", "episodes")
    ):
        return DEFAULT_LANE_WIDTH_M

    return None
