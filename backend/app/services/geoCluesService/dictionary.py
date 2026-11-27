"""Словарь географических улик для zero-shot детекции.

Grounding DINO получает не «все объекты», а только те, по которым
можно опознать место. Поэтому словарь короткий и сформулирован как
промпт геопривязки: дом с мезонином, характерная группа деревьев,
фрагмент знака, остатки фундамента и т. п.

Для каждой улики хранится русское название, тип и базовый приоритет.
Приоритет — это не уверенность модели, а ценность признака для
поиска координат: «дом с мезонином» важнее «столба ЛЭП».
"""

from __future__ import annotations

import re


# Порядок совпадает с промптом из ТЗ. Менять его можно, но тогда
# изменится и текст, который уходит в Grounding DINO.
CLUE_DICTIONARY: tuple[dict, ...] = (
    {
        "label": "old wooden house with mezzanine",
        "label_ru": "Старый деревянный дом с мезонином",
        "type": "building_ruin",
        "match_priority": "high",
        "description": (
            "Деревянный дом с мезонином: характерный силуэт крыши, "
            "окна и балкон помогают найти это место на старых картах "
            "и спутниковых снимках."
        ),
    },
    {
        "label": "exposed brickwork",
        "label_ru": "Открытая кирпичная кладка",
        "type": "building_ruin",
        "match_priority": "high",
        "description": (
            "Фрагмент открытой кирпичной кладки: цвет и перевязка "
            "могут указать на старую постройку или фундамент."
        ),
    },
    {
        "label": "wooden balcony with columns",
        "label_ru": "Деревянный балкон с колоннами",
        "type": "building_ruin",
        "match_priority": "high",
        "description": (
            "Деревянный балкон с колоннами — редкая архитектурная "
            "деталь, удобная для визуального сопоставления."
        ),
    },
    {
        "label": "boarded-up windows",
        "label_ru": "Забитые окна",
        "type": "building_ruin",
        "match_priority": "high",
        "description": (
            "Забитые окна указывают на заброшенное или законсервированное "
            "строение; рисунок досок может быть уникальным."
        ),
    },
    {
        "label": "wooden shutters",
        "label_ru": "Деревянные ставни",
        "type": "building_ruin",
        "match_priority": "medium",
        "description": (
            "Деревянные ставни помогают отличить жилой дом от сарая "
            "и уточнить ориентацию фасада."
        ),
    },
    {
        "label": "distinctive tree group",
        "label_ru": "Характерная группа деревьев",
        "type": "natural_landmark",
        "match_priority": "high",
        "description": (
            "Группа деревьев с запоминающимся расположением или наклоном "
            "стволов — естественный ориентир, который виден на снимках "
            "разных лет."
        ),
    },
    {
        "label": "isolated tall tree with bent trunk",
        "label_ru": "Одинокое высокое дерево с изогнутым стволом",
        "type": "natural_landmark",
        "match_priority": "high",
        "description": (
            "Одинокое дерево с изогнутым стволом — сильный точечный "
            "ориентир; проверьте его тень и соседние просеки."
        ),
    },
    {
        "label": "road sign or post",
        "label_ru": "Дорожный знак или столб",
        "type": "signage",
        "match_priority": "medium",
        "description": (
            "Дорожный знак или столб может нести текст, номер дороги "
            "или указатель направления; полезен для сужения района."
        ),
    },
    {
        "label": "metal utility pole",
        "label_ru": "Металлическая опора ЛЭП",
        "type": "infrastructure",
        "match_priority": "low",
        "description": (
            "Металлическая опора ЛЭП — слабая улика: такие опоры "
            "типовые и редко позволяют опознать конкретное место."
        ),
    },
    {
        "label": "collapsed fence post",
        "label_ru": "Упавший столб ограды",
        "type": "infrastructure",
        "match_priority": "low",
        "description": (
            "Упавший столб ограды — слабая улика; полезен только "
            "вместе с линией забора или дорогой."
        ),
    },
    {
        "label": "remnants of foundation in grass",
        "label_ru": "Остатки фундамента в траве",
        "type": "building_ruin",
        "match_priority": "high",
        "description": (
            "Остатки фундамента в траве — прямой признак исчезнувшего "
            "строения; сравните контур с историческими картами."
        ),
    },
    {
        "label": "old stone path",
        "label_ru": "Старая каменная дорожка",
        "type": "terrain_trace",
        "match_priority": "medium",
        "description": (
            "Старая каменная дорожка может сохраниться на местности "
            "и читаться на спутнике как светлая линия."
        ),
    },
    {
        "label": "overgrown ditch",
        "label_ru": "Зарастающая канава",
        "type": "terrain_trace",
        "match_priority": "medium",
        "description": (
            "Зарастающая канава — след мелиорации или старой дороги; "
            "хорошо видна на снимках с низким солнцем."
        ),
    },
    {
        "label": "industrial chimney or tower",
        "label_ru": "Промышленная труба или башня",
        "type": "industrial",
        "match_priority": "high",
        "description": (
            "Промышленная труба или башня — заметный вертикальный "
            "ориентир, который часто есть на старых снимках."
        ),
    },
    {
        "label": "unique rock formation",
        "label_ru": "Необычное скальное образование",
        "type": "natural_landmark",
        "match_priority": "high",
        "description": (
            "Необычное скальное образование — уникальный природный "
            "ориентир; проверьте его форму и тень на карте."
        ),
    },
    {
        "label": "water body edge",
        "label_ru": "Берег водоёма",
        "type": "water",
        "match_priority": "medium",
        "description": (
            "Берег водоёма помогает привязать кадр к реке, озеру "
            "или пруду; важен изгиб береговой линии."
        ),
    },
    {
        "label": "bridge abutment",
        "label_ru": "Устой моста",
        "type": "bridge",
        "match_priority": "high",
        "description": (
            "Устой моста — прочная конструкция, которая переживает "
            "сам мост; удобна для сопоставления с картами."
        ),
    },
    {
        "label": "kilometer post",
        "label_ru": "Километровый столб",
        "type": "infrastructure",
        "match_priority": "high",
        "description": (
            "Километровый столб с номером дороги и километром — "
            "самая сильная инфраструктурная улика: OCR номера "
            "сужает поиск до нескольких дорожных кандидатов."
        ),
    },
    {
        "label": "utility pole",
        "label_ru": "Опора ЛЭП или связи",
        "type": "infrastructure",
        "match_priority": "low",
        "description": (
            "Опора ЛЭП или связи: деревянная или железобетонная "
            "(СВ-95, СВ-105). Плотность опор помогает калибровать "
            "одометрию, но сама по себе место не определяет."
        ),
    },
    {
        "label": "culvert",
        "label_ru": "Водопропускная труба",
        "type": "infrastructure",
        "match_priority": "medium",
        "description": (
            "Водопропускная труба под дорогой — типовой элемент, "
            "но её расположение и оголовок помогают привязать "
            "участок дороги."
        ),
    },
    {
        "label": "guardrail",
        "label_ru": "Дорожное ограждение",
        "type": "infrastructure",
        "match_priority": "medium",
        "description": (
            "Барьерное ограждение и его стойки — признак класса "
            "дороги и опасного участка; полезно вместе с километровым "
            "столбом."
        ),
    },
)


PROMPT_LABELS: tuple[str, ...] = tuple(
    item["label"] for item in CLUE_DICTIONARY
)

# Grounding DINO ожидает фразы, разделённые точками.
PROMPT_TEXT = " . ".join(PROMPT_LABELS) + " ."

BY_LABEL = {
    item["label"]: item
    for item in CLUE_DICTIONARY
}

PRIORITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}

STRONG_TYPES = {
    "building_ruin",
    "natural_landmark",
    "industrial",
    "bridge",
}


_ARTICLES = {"a", "an", "the"}
_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_label(value: str) -> str:
    """Привести подпись модели к виду словаря."""

    text = str(value or "").lower().strip()
    text = text.replace("_", " ")
    text = _NON_WORD.sub(" ", text)
    words = [
        word
        for word in text.split()
        if word not in _ARTICLES
    ]

    return " ".join(words)


def canonical_label(value: str) -> str | None:
    """Найти ближайшую улику словаря.

    Grounding DINO иногда возвращает фразу с лишними словами или
    обрезанный хвост. Точное совпадение — лучший случай; иначе
    выбирается словарная фраза с максимальным пересечением слов.
    Неуверенные совпадения отбрасываются, чтобы не выдавать шум
    за географическую улику.
    """

    normalized = normalize_label(value)

    if not normalized:
        return None

    if normalized in BY_LABEL:
        return normalized

    words = set(normalized.split())
    best_label = None
    best_score = 0.0

    for label in PROMPT_LABELS:
        label_words = set(label.split())
        overlap = len(words & label_words)

        if not overlap:
            continue

        # Доля слов словаря, найденных в ответе модели. Этого
        # достаточно, чтобы принять «wooden balcony with columns»
        # и отбросить «wooden fence».
        score = overlap / len(label_words)

        if score > best_score:
            best_score = score
            best_label = label

    if best_score >= 0.6:
        return best_label

    return None


def label_ru(label: str) -> str:
    item = BY_LABEL.get(label)
    return item["label_ru"] if item else label


def clue_type(label: str) -> str:
    item = BY_LABEL.get(label)
    return item["type"] if item else "other"


def base_priority(label: str) -> str:
    item = BY_LABEL.get(label)
    return item["match_priority"] if item else "low"


def base_description(label: str) -> str:
    item = BY_LABEL.get(label)
    return item["description"] if item else ""


def is_strong_type(label: str) -> bool:
    return clue_type(label) in STRONG_TYPES


def priority_rank(value: str) -> int:
    return PRIORITY_ORDER.get(value, len(PRIORITY_ORDER))
