"""Метрики кадра для консолидированной стадии visual_analysis.

Здесь живут чистые функции без файловой системы: яркость, контраст,
насыщенность, доли неба/зелени/воды/снега/асфальта, плотность краёв
и текстуры. Раньше эти функции были в visual_profile.py; новый
модуль не зависит от старых сервисов, чтобы их можно было удалить
без поломки visual_analysis.

Модуль не импортирует torch и transformers: это быстрые расчёты на
numpy и Pillow.
"""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

import numpy as np


METRIC_KEYS = (
    "brightness",
    "contrast",
    "saturation",
    "colorfulness",
    "warmth",
    "sky",
    "vegetation",
    "water",
    "snow",
    "gray",
    "asphalt",
    "sand",
    "shadow",
    "edge_density",
    "upper_texture",
    "lower_texture",
    "smooth_lower",
    "vertical_edges",
    "horizontal_edges",
    "horizon_ratio",
)


def analyze_frame(path: Path) -> dict:
    """Посчитать визуальные метрики одного кадра.

    Кадр уменьшается до 256 пикселей по большей стороне: метрики
    описывают сцену, а не мелкие детали. Возвращает словарь чисел
    и палитру доминирующих цветов.
    """

    from PIL import Image

    with Image.open(path) as source:
        image = source.convert("RGB")
        image.thumbnail((256, 256))

        rgb = np.asarray(image, dtype=np.float32)
        hsv = np.asarray(
            image.convert("HSV"),
            dtype=np.float32,
        )

    height, width = rgb.shape[:2]

    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    rows = np.arange(height).reshape(-1, 1)
    top = rows < height * 0.55
    bottom = rows >= height * 0.35

    gray = rgb.mean(axis=2)

    gradient_y = np.abs(np.diff(gray, axis=0))
    gradient_x = np.abs(np.diff(gray, axis=1))

    common_h = min(
        gradient_y.shape[0],
        gradient_x.shape[0],
    )
    common_w = min(
        gradient_y.shape[1],
        gradient_x.shape[1],
    )

    magnitude = np.hypot(
        gradient_y[:common_h, :common_w],
        gradient_x[:common_h, :common_w],
    )

    edge_density = float(
        (magnitude > 18).mean() * 100
    )

    upper = magnitude[: common_h // 2]
    lower = magnitude[common_h // 2:]

    upper_texture = float(
        (upper > 18).mean() * 100
    ) if upper.size else 0.0

    lower_texture = float(
        (lower > 18).mean() * 100
    ) if lower.size else 0.0

    smooth_lower = float(
        (lower <= 8).mean() * 100
    ) if lower.size else 0.0

    vertical_edges = float(
        gradient_x.mean()
    )
    horizontal_edges = float(
        gradient_y.mean()
    )

    sky = (
        (hue >= 135)
        & (hue <= 190)
        & (saturation > 35)
        & (value > 80)
    )

    vegetation = (
        (hue >= 45)
        & (hue <= 115)
        & (saturation > 40)
        & (value > 30)
    )

    water = (
        (hue >= 120)
        & (hue <= 195)
        & (saturation > 30)
        & (value > 25)
    )

    snow = (value > 195) & (saturation < 30)

    gray_mask = saturation < 32
    asphalt = gray_mask & (value >= 25) & (value <= 135)

    sand = (
        (hue >= 10)
        & (hue <= 45)
        & (saturation > 55)
        & (value > 70)
    )

    shadow = value < 80

    warm = (
        (rgb[:, :, 0] - rgb[:, :, 2]) > 18
    ) & (saturation > 25)

    colorfulness = float(
        (
            np.abs(rgb[:, :, 0] - rgb[:, :, 1])
            + np.abs(rgb[:, :, 1] - rgb[:, :, 2])
        ).mean()
    )

    row_energy = gradient_y.mean(axis=1)
    start = int(height * 0.08)
    finish = max(start + 1, int(height * 0.9))
    horizon_ratio = (
        start + int(np.argmax(row_energy[start:finish]))
    ) / height

    metrics = {
        "brightness": round(float(value.mean()), 1),
        "contrast": round(float(gray.std()), 1),
        "saturation": round(float(saturation.mean()), 1),
        "colorfulness": round(colorfulness, 1),
        "warmth": round(float(warm.mean() * 100), 1),
        "sky": round(float((sky & top).mean() * 100), 1),
        "vegetation": round(float(vegetation.mean() * 100), 1),
        "water": round(float(water.mean() * 100), 1),
        "snow": round(float(snow.mean() * 100), 1),
        "gray": round(float(gray_mask.mean() * 100), 1),
        "asphalt": round(float(asphalt.mean() * 100), 1),
        "sand": round(float(sand.mean() * 100), 1),
        "shadow": round(float(shadow.mean() * 100), 1),
        "edge_density": round(edge_density, 1),
        "upper_texture": round(upper_texture, 1),
        "lower_texture": round(lower_texture, 1),
        "smooth_lower": round(smooth_lower, 1),
        "vertical_edges": round(vertical_edges, 2),
        "horizontal_edges": round(horizontal_edges, 2),
        "horizon_ratio": round(float(horizon_ratio), 3),
    }

    metrics["palette"] = _palette(
        hue,
        saturation,
        value,
    )
    metrics["gray_lower"] = round(
        float((gray_mask & bottom).mean() * 100),
        1,
    )

    return metrics


def describe_metrics(metrics: dict) -> dict:
    """Перевести числа метрик в словесное описание сцены.

    Возвращает освещённость, погоду, сезон, список признаков
    ландшафта, сложность сцены и палитру. Формулировки намеренно
    осторожные: это гипотезы по цвету и текстуре.
    """

    brightness = metrics["brightness"]
    contrast = metrics["contrast"]
    saturation = metrics["saturation"]
    colorfulness = metrics["colorfulness"]

    if brightness < 50:
        lighting = "ночь или сильное затемнение"
    elif brightness < 95:
        lighting = "сумерки или пасмурная тень"
    else:
        lighting = "дневной свет"

    if contrast < 35 and saturation < 25:
        weather = "пасмурно или облачно"
    elif brightness > 145 and colorfulness > 28:
        weather = "солнечно, вероятно"
    else:
        weather = "умеренная облачность, не определено"

    if metrics["snow"] > 12:
        season = "зима или снежный покров, вероятно"
    elif metrics["vegetation"] > 15:
        season = "вегетация, вероятно лето"
    elif (
        metrics.get("sand", 0) > 15
        and metrics["vegetation"] < 5
    ):
        season = "осень или ранняя весна, возможно"
    else:
        season = "не определяется"

    landscape = []

    if metrics["water"] > 12:
        landscape.append("водная поверхность")

    if (
        metrics.get("gray_lower", 0) > 40
        and metrics["smooth_lower"] > 25
    ):
        landscape.append(
            "крупная ровная поверхность "
            "(вода, асфальт или снег)"
        )

    if metrics["vegetation"] > 15:
        landscape.append("растительность")

    if metrics["sky"] > 8:
        landscape.append("открытое небо")

    if metrics["snow"] > 12:
        landscape.append("яркая светлая поверхность")

    if metrics["asphalt"] > 15:
        landscape.append("дорога или асфальт, возможно")

    if (
        metrics["upper_texture"] > 22
        and metrics["gray"] > 25
        and metrics["horizontal_edges"]
        > metrics["vertical_edges"] * 1.1
    ):
        landscape.append(
            "скалы или плотная застройка, возможно"
        )

    if not landscape:
        landscape.append("выраженные признаки не найдены")

    if metrics["edge_density"] > 25:
        complexity = "высокая"
    elif metrics["edge_density"] > 10:
        complexity = "средняя"
    else:
        complexity = "низкая"

    return {
        "lighting": lighting,
        "weather": weather,
        "season": season,
        "landscape": landscape,
        "complexity": complexity,
        "palette": metrics.get("palette", []),
        "horizon_ratio": metrics["horizon_ratio"],
    }


def aggregate_profile(frames: list[dict]) -> dict:
    """Свести метрики всех кадров в один профиль.

    Числовые метрики берутся как медиана по кадрам, словесные —
    как самое частое значение. Пустой список даёт пустой словарь.
    """

    if not frames:
        return {}

    metrics = {
        key: round(
            float(
                statistics.median(
                    frame["metrics"][key]
                    for frame in frames
                )
            ),
            2,
        )
        for key in METRIC_KEYS
        if all(key in frame["metrics"] for frame in frames)
    }

    def most_common(key: str) -> str:
        values = [
            frame["descriptors"].get(key)
            for frame in frames
            if frame["descriptors"].get(key)
        ]

        if not values:
            return "не определено"

        return Counter(values).most_common(1)[0][0]

    landscape_counts = Counter(
        item
        for frame in frames
        for item in frame["descriptors"].get(
            "landscape",
            [],
        )
    )

    palette_counts = Counter(
        item
        for frame in frames
        for item in frame["descriptors"].get(
            "palette",
            [],
        )
    )

    return {
        "lighting": most_common("lighting"),
        "weather": most_common("weather"),
        "season": most_common("season"),
        "complexity": most_common("complexity"),
        "landscape": [
            item
            for item, _ in landscape_counts.most_common(6)
        ],
        "palette": [
            item
            for item, _ in palette_counts.most_common(5)
        ],
        "metrics": metrics,
        "sampled_frames": len(frames),
    }


def observation_text(descriptors: dict) -> str:
    """Собрать короткую фразу о визуальном профиле кадра."""

    landscape = ", ".join(
        descriptors.get("landscape", [])
    )

    return (
        f"Визуальный профиль: "
        f"{descriptors.get('lighting', 'не определено')}; "
        f"{descriptors.get('weather', 'не определено')}; "
        f"{descriptors.get('season', 'не определено')}; "
        f"сцена: {landscape or 'не определена'}."
    )


def _palette(hue, saturation, value) -> list[str]:
    """Выбрать до четырёх доминирующих цветовых групп кадра."""

    masks = (
        ("белый или снег", (value > 195) & (saturation < 30)),
        ("зелёный", (hue >= 45) & (hue <= 115) & (saturation >= 30)),
        ("синий", (hue > 115) & (hue <= 195) & (saturation >= 30)),
        ("коричневый или земля", (hue > 5) & (hue < 45) & (saturation >= 30)),
        ("светло-серый", (saturation < 25) & (value > 130)),
        ("тёмно-серый или тень", saturation < 30),
    )

    total = hue.size
    result = []

    for name, mask in masks:
        percent = float(mask.mean() * 100)

        if percent >= 5:
            result.append(f"{name} {percent:.0f}%")

    return result[:4]
