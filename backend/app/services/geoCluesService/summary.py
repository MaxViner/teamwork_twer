"""Описания улик и краткий вывод по кадру.

Модель даёт рамку и метку, но для геопривязки нужен человеческий
вывод: это сильный ориентир или шум, что искать дальше. Здесь
собираются description, match_priority и frame_summary.
"""

from __future__ import annotations

from collections import Counter

from app.services.geoCluesService import dictionary


TERRAIN_LABELS = {
    "overgrown_settlement": "заросший посёлок / исчезнувшая деревня",
    "industrial_site": "промышленная площадка",
    "water_edge": "берег водоёма",
    "forest_edge": "лесная опушка",
    "roadside": "придорожная территория",
    "rural_landscape": "сельский ландшафт",
    "unknown": "не определён",
}


def priority_for(
    label: str,
    confidence: float,
    visibility: float | None,
) -> str:
    """Скорректировать базовый приоритет по уверенности и видимости."""

    base = dictionary.base_priority(label)

    if base == "high":
        if confidence < 0.35:
            return "medium"

        if visibility is not None and visibility < 0.12:
            return "medium"

        return "high"

    if base == "medium":
        if confidence < 0.30:
            return "low"

        return "medium"

    return "low"


def describe_clue(
    label: str,
    confidence: float,
    visibility: float,
    complexity: float,
    segmented: bool,
) -> str:
    """Собрать описание, объясняющее ценность улики."""

    parts = [dictionary.base_description(label)]

    if not segmented:
        parts.append(
            "Маска не построена: полигон совпадает с рамкой, "
            "видимость принята за 100%."
        )

    elif visibility < 0.2:
        parts.append(
            f"Виден небольшой фрагмент (≈{visibility * 100:.0f}% рамки): "
            "объект может быть сильно скрыт, но сам факт его наличия важен."
        )

    elif visibility <= 0.45:
        parts.append(
            f"Объект виден примерно на {visibility * 100:.0f}% рамки — "
            "это признак существующего, но частично скрытого объекта, "
            "а не ошибка детекции."
        )

    elif visibility < 0.75:
        parts.append(
            f"Объект виден примерно на {visibility * 100:.0f}% рамки."
        )

    else:
        parts.append(
            f"Объект виден почти полностью (≈{visibility * 100:.0f}%)."
        )

    if complexity >= 2.2:
        parts.append(
            "Контур сложный и угловатый: проверьте форму постройки "
            "на старых снимках."
        )

    if confidence < 0.4:
        parts.append(
            "Уверенность детекции низкая — улику нужно проверить вручную."
        )

    return " ".join(
        part.strip()
        for part in parts
        if part and part.strip()
    )


def dominant_terrain(clues: list[dict]) -> str:
    """Определить доминирующий тип места по найденным уликам."""

    if not clues:
        return "unknown"

    counts = Counter(
        dictionary.clue_type(item.get("label", ""))
        for item in clues
    )

    buildings = counts.get("building_ruin", 0)
    terrain = counts.get("terrain_trace", 0)
    industrial = counts.get("industrial", 0)
    water = counts.get("water", 0)
    natural = counts.get("natural_landmark", 0)
    roadside = counts.get("signage", 0) + counts.get("infrastructure", 0)
    bridge = counts.get("bridge", 0)

    if industrial and industrial >= max(buildings, natural):
        return "industrial_site"

    if buildings or bridge:
        return "overgrown_settlement"

    if water:
        return "water_edge"

    if natural and natural >= terrain:
        return "forest_edge"

    if roadside:
        return "roadside"

    if terrain:
        return "rural_landscape"

    return "unknown"


def suggested_next_step(terrain: str, clues: list[dict]) -> str:
    """Подсказать следующий шаг поиска по картам."""

    top = _top_labels(clues)

    if terrain == "overgrown_settlement":
        return (
            "Сопоставить контур дома или фундамента с картами Генштаба "
            "и спутниковыми снимками 2005–2010 годов; проверить "
            "ориентацию фасада и направление тени."
            + (f" Главные улики: {top}." if top else "")
        )

    if terrain == "industrial_site":
        return (
            "Искать трубу или башню на исторических снимках и в "
            "Wikimapia; проверить дым, тень и соседние подъездные пути."
            + (f" Главные улики: {top}." if top else "")
        )

    if terrain == "water_edge":
        return (
            "Сопоставить изгиб береговой линии с OSM и старыми картами; "
            "проверить мост, брод и направление течения."
            + (f" Главные улики: {top}." if top else "")
        )

    if terrain == "forest_edge":
        return (
            "Сравнить группу деревьев, просеки и опушку на спутнике; "
            "использовать длину теней для оценки высоты ориентира."
            + (f" Главные улики: {top}." if top else "")
        )

    if terrain == "roadside":
        return (
            "Прочитать знак или номер дороги, проверить километровые "
            "столбы, придорожную застройку и поворот дороги."
            + (f" Главные улики: {top}." if top else "")
        )

    if terrain == "rural_landscape":
        return (
            "Проверить старую дорожку, канаву и границы полей на картах "
            "и снимках с низким солнцем."
            + (f" Главные улики: {top}." if top else "")
        )

    return (
        "Собрать больше кадров: нужны выраженные объекты, текст или "
        "ориентиры на горизонте, иначе круг поиска слишком широк."
    )


def _top_labels(clues: list[dict], limit: int = 3) -> str:
    ordered = sorted(
        clues,
        key=lambda item: (
            dictionary.priority_rank(
                item.get("match_priority", "low")
            ),
            -float(item.get("confidence") or 0.0),
        ),
    )

    labels = [
        item.get("label_ru") or item.get("label")
        for item in ordered[:limit]
        if item.get("label_ru") or item.get("label")
    ]

    return ", ".join(labels)


def frame_summary(clues: list[dict]) -> dict:
    """Краткий вывод: есть ли сильные улики и что делать дальше."""

    strong = [
        item
        for item in clues
        if item.get("match_priority") == "high"
    ]
    weak = [
        item
        for item in clues
        if item.get("match_priority") != "high"
    ]

    terrain = dominant_terrain(clues)
    step = suggested_next_step(terrain, clues)

    if strong:
        summary_text = (
            f"В кадре {len(strong)} сильн. улик"
            f"{'а' if len(strong) == 1 else 'и'}; "
            f"доминирующий ландшафт — "
            f"{TERRAIN_LABELS.get(terrain, terrain)}. "
            f"Следующий шаг: {step}"
        )
    elif weak:
        summary_text = (
            "Сильных улик нет, только слабые признаки. "
            f"Ландшафт — {TERRAIN_LABELS.get(terrain, terrain)}. "
            f"Следующий шаг: {step}"
        )
    else:
        summary_text = (
            "Улик не найдено. " + step
        )

    return {
        "has_strong_clues": bool(strong),
        "strong_clue_count": len(strong),
        "weak_clue_count": len(weak),
        "dominant_terrain": terrain,
        "dominant_terrain_ru": TERRAIN_LABELS.get(
            terrain,
            terrain,
        ),
        "suggested_next_step": step,
        "summary_text": summary_text,
        "top_clue": (
            strong[0].get("label_ru")
            if strong
            else None
        ),
    }
